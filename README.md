# ticket-load-test

A research prototype for stress-testing a **centralized, strongly-consistent PostgreSQL** ticketing system under high concurrent write load.

The project supports a master's thesis: it pushes a single Postgres instance to its maximum sustainable write throughput on fixed hardware (8 cores / 16 GB), and quantifies how application-side design choices — Uvicorn worker concurrency, connection pool sizing, horizontal replication of the write service, and a Redis availability cache — shift that ceiling.

The full experimental protocol (hypotheses, run matrix, per-run procedure, analysis plan) lives in **[TEST-PLAN.md](TEST-PLAN.md)**.

---

## What it studies

Tickets start `available` and must transition to `reserved` exactly once — no double-booking — while thousands of clients race for them. The questions:

- **RQ1** — optimal Uvicorn workers per cart replica.
- **RQ2** — optimal DB connections per worker (pool sizing) before coordination overhead dominates.
- **RQ3** — does a Redis availability cache offload Postgres?
- **RQ4** — how far does a single centralized Postgres scale as the write tier scales out (1 → 3 → 5 replicas)?

---

## Architecture

```
load generator (external, 3000 clients)
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
| ticket-info | 8002 | Read service. Scaled to 0 during runs (not part of the SUT). |
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
./start-cluster.zsh            # bring up the full stack on minikube
./set-cart-profile.zsh <1|3|5> # select replica profile + pin SUT resources
./reset-cluster.zsh            # restore clean inventory + connection state between runs
```

Seed inventory manually via the ticket-manager Swagger UI (`http://localhost:8001/docs` → `POST /generate?count=300000`); this also warms the Redis cache when `REDIS_URL` is set.

Resource allocation, QoS pinning, and the cart replica profiles are documented in **[RESOURCE-ALLOCATION.md](RESOURCE-ALLOCATION.md)**.
