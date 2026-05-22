# ticket-load-test

A research prototype for stress-testing a **centralized, strongly-consistent PostgreSQL** ticketing system under high concurrent write load.

The project supports a master's thesis: it pushes a single Postgres instance to its maximum sustainable write throughput on fixed hardware (8 cores / 16 GB), and quantifies how design choices — the CPU split between database and write service, connection pool sizing, horizontal replication of the write service, and a Redis availability cache — shift that ceiling.

The full experimental protocol (hypotheses, run matrix, per-run procedure, analysis plan) lives in **[TEST-PLAN.md](TEST-PLAN.md)**.

---

## What it studies

Tickets start `available` and must transition to `reserved` exactly once — no double-booking — while thousands of clients race for them. The questions:

- **RQ1** — optimal CPU split between Postgres and cart at a fixed total compute budget.
- **RQ2** — optimal DB connections per cart pod (pool sizing) before coordination overhead dominates.
- **RQ3** — does a Redis availability cache offload Postgres?
- **RQ4** — how far does a single centralized Postgres scale as the write tier scales out (1 → 3 → 5 replicas)?

---

## Architecture

```
load generator (external, 2000 clients)
        │
        ▼
   cart (FastAPI + asyncpg)      ← the only service under load
        │
        ▼
   PgBouncer (pool_mode=transaction)
        │
        ▼
   PostgreSQL 16  (single node, synchronous_commit=off)

   Redis ───────── availability cache (Redis path only)
```

| Service | Port | Role |
|---|---|---|
| **cart** | 8003 | Write service under test — performs reservations. |
| ticket-manager | 8001 | Seeds / deletes ticket inventory (and warms Redis). Used out-of-band, not under load. |
| ticket-info | 8002 | Read service. Not under load (not part of the SUT). |
| postgres | 5432 | Centralized strongly-consistent store. |
| pgbouncer | 5432 | Connection multiplexer in front of Postgres. |
| redis | 6379 | Availability-id cache for the Redis reservation path. |

### Reservation strategies (cart endpoints)

| Endpoint | Strategy | Consistency |
|---|---|---|
| `POST /cart/reserve-batch` | `SELECT … FOR UPDATE SKIP LOCKED` + `UPDATE` in one transaction | Safe (no double-booking) |
| `POST /cart/reserve-batch-redis` | `LPOP` an available id from Redis, then targeted single-row `UPDATE` | Safe; offloads the availability scan + lock contention, not the durable write |
| `POST /cart/reserve-batch-unsafe` | `LIMIT` without row locking | Unsafe — demonstrates double-booking under contention |

---

## Observability

Prometheus scrapes the cart app metrics plus exporters for Postgres, PgBouncer, Redis, and node/container CPU (cadvisor). Metrics flow cart → OpenTelemetry Collector → Prometheus → Grafana. A single combined Grafana dashboard surfaces throughput, latency percentiles, outcome breakdown, and per-pod saturation. Screenshot it at run end (time range = steady-state window).

---

## Running

```sh
./start-cluster.zsh                       # bring up the full stack on minikube
./set-resource-split.zsh <pg_m> <cart_m>  # Phase 1: sweep the postgres↔cart CPU split (1 replica)
./set-cart-profile.zsh <1|3|5>            # Phases 2–4: select replica profile + pin SUT resources
./set-pool.zsh <n>                        # Phase 2: set cart DB_POOL_SIZE
./set-redis.zsh <on|off>                  # Phase 3: toggle the Redis path (cart + ticket-info)
./reset-cluster.zsh                       # restore clean inventory + connection state between runs
```

All reconfig scripts apply changes **live** — no cluster restart between runs. The node sits at ~100% CPU requests, so any change that grows postgres or adds cart pods would otherwise leave a pod Pending. `set-resource-split.zsh` and `set-cart-profile.zsh` avoid this by scaling cart to 0 first (freeing its CPU), resizing postgres into the freed space, then bringing cart back up last (shared logic in `lib-cluster.zsh`). The env-only scripts (`set-pool.zsh`, `set-redis.zsh`) roll cart in place (`maxSurge: 0`), no scale-down needed.

**Each script is self-contained and leaves a ready state:**

| Script | Sets | Leaves unchanged | End state |
|---|---|---|---|
| `set-resource-split.zsh` | postgres+cart CPU split, 1 replica | `DB_POOL_SIZE`, `REDIS_ENABLED`, `WORKERS` | cart Ready, postgres rolled |
| `set-cart-profile.zsh` | replica count + per-pod size (from `PG_CPU_M`) | `DB_POOL_SIZE`, `REDIS_ENABLED`, `WORKERS` | cart Ready, postgres rolled |
| `set-pool.zsh` | `DB_POOL_SIZE` | resources, replicas, Redis | cart Ready |
| `set-redis.zsh` | `REDIS_ENABLED` (cart + ticket-info) | resources, replicas, pool | cart + ticket-info Ready |

No two scripts write the same setting, so order within a phase doesn't matter for correctness — the resource scripts never reset pool/Redis, and the env scripts never touch resources. The Grafana resource-ceiling panels read live pod limits from kube-state-metrics, so they auto-track whatever the resource scripts apply — no script edits the dashboard.

**Port-forwards & tunnel:** the two resource scripts re-establish the Grafana port-forward (3000) after restarting Grafana; the env scripts don't restart Grafana so its forward survives. `minikube tunnel` and the ingress route to cart survive pod restarts (the Service is stable) — external load is unaffected. Seeding goes through ticket-manager, which no script restarts.

Uvicorn `WORKERS` is fixed at 2 for all runs (`kubectl set env deployment/cart -n ticket-system WORKERS=2`) — it is not a swept factor (request handling is CPU-bound at this budget).

Seed inventory manually via the ticket-manager Swagger UI (`http://localhost:8001/docs` → `POST /generate?count=1000000`); this also warms the Redis cache when `REDIS_URL` is set.

Resource allocation, QoS pinning, and the cart replica profiles are documented in **[RESOURCE-ALLOCATION.md](RESOURCE-ALLOCATION.md)**.
