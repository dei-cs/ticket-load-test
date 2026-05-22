# Resource Allocation

Single node: **8 cores / 16 GB** (~14.5 GB usable after k8s overhead).

SUT-critical pods (cart, postgres, pgbouncer, redis) run **Guaranteed QoS** (requests == limits)
so observability (Burstable) cannot steal CPU from the measured path during a run.
`set-cart-profile.zsh` pins these on every profile switch (idempotent).

> **\* postgres/cart CPU is the RQ1 lever.** postgres + cart share a fixed **5000m** budget
> (pgbouncer 500m + redis 500m held constant). Phase 1 sweeps the split with
> `./set-resource-split.zsh <pg_m> <cart_m>` (single replica) — the 3000/2000 values above are
> the current default, not a tuned optimum. Once RQ1 picks the optimal split, set `PG_CPU_M` in
> `set-cart-profile.zsh` (one knob) for Phases 2–4 — cart total auto-derives as `5000 − PG_CPU_M`,
> so the budget can't drift. Uvicorn `WORKERS` is fixed at 2 (not swept).
>
> **Pool & Redis are owned by their own scripts.** `set-cart-profile.zsh` deliberately does **not**
> touch `DB_POOL_SIZE` or `REDIS_ENABLED` — set those with `./set-pool.zsh` / `./set-redis.zsh` so
> switching profiles never resets a swept value.

## Per-pod allocation

| Pod | QoS | CPU req→lim | Mem req→lim | Note |
|---|---|---|---|---|
| postgres | **Guaranteed** | 3000m* | 6Gi | SUT ceiling; extra RAM = page cache headroom |
| cart (total) | **Guaranteed** | 2000m* | 2Gi | held constant across profiles (see below) |
| pgbouncer | **Guaranteed** | 500m | 256Mi | single-threaded — watch CPU/`cl_waiting` (see caveat) |
| redis | **Guaranteed** | 500m | 512Mi | Redis-arm only |
| prometheus | Burstable | 100m → 500m | 256Mi → 1.5Gi | scrapes during window (5s) |
| grafana | Burstable | 200m → 1000m | 512Mi → 1Gi | idle during window; view/screenshot at run end |
| otel-collector | Burstable | 50m → 200m | 64Mi → 512Mi | |
| cadvisor | Burstable | 50m → 200m | 64Mi → 256Mi | |
| postgres-exporter | Burstable | 50m → 200m | 64Mi → 128Mi | |
| pgbouncer-exporter | Burstable | 50m → 100m | 32Mi → 64Mi | |
| redis-exporter | Burstable | 50m → 100m | 32Mi → 64Mi | |
| ticket-manager | Burstable | 250m → 250m | 128Mi → 256Mi | stays up; seeds inventory + warms cache |
| ticket-info | Burstable | 150m → 150m | 256Mi → 512Mi | read service; not under load |
| _control plane_ | _system_ | ~850m | — | apiserver/etcd/ctrl-mgr/sched/coredns/metrics-server (on-node, minikube) |
| _ingress-nginx_ | _system_ | ~100m | — | routes external load to cart |

## Budget check

Node allocatable = **8000m** (minikube `--cpus=8`). All pods run concurrently — no scale-to-0 needed:

| Group | CPU requests |
|---|---|
| SUT: postgres 3000 + cart 2000 + pgbouncer 500 + redis 500 | 6000m |
| ticket-manager 250 + ticket-info 150 | 400m |
| observability (prom/grafana/otel/cadvisor + 3 exporters) | 550m |
| control plane + ingress | 950m |
| **total** | **7900m / 8000m**  (~100m slack) |

- ~100m scheduling slack; everything (including the ticket services) stays running, no scaling dance.
- cart deploy starts at `replicas: 1`; `set-cart-profile.zsh` sets the per-profile replica count.
- cart uses `maxSurge: 0` so profile/worker changes **recreate** in place rather than needing a 2nd cart pod the packed node can't schedule.
- pgbouncer runs at 500m. **It is single-threaded** — if it pegs 500m and `cl_waiting` climbs, pgbouncer (not Postgres) is the limiter. Watch it; report it.
- **Mem:** Guaranteed pods reserve ~8.75 Gi (postgres 6 + cart 2 + pgbouncer 0.25 + redis 0.5). Remaining RAM is intentionally free → kernel page cache for Postgres data files. Dataset (300k rows) is small, so this is safe headroom, not a tuned cache target.

## Cart profiles

Cart total budget held constant (at the RQ1-optimal cart share) across all profiles so RQ4
reflects **topology**, not raw resource. Set via `./set-cart-profile.zsh <1|3|5>`.

| Profile | replicas | cpu/pod | mem/pod | DB_POOL_SIZE |
|---|---|---|---|---|
| 1 | 1 | 2000m | 2048Mi | 5 |
| 3 | 3 | 667m | 683Mi | 5 |
| 5 | 5 | 400m | 410Mi | 5 |
