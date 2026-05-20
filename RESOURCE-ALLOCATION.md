# Resource Allocation

Single node: **8 cores / 16 GB** (~14.5 GB usable after k8s overhead).

SUT-critical pods (cart, postgres, pgbouncer, redis) run **Guaranteed QoS** (requests == limits)
so observability (Burstable) cannot steal CPU from the measured path during a run.
`set-cart-profile.zsh` pins these on every profile switch (idempotent).

## Per-pod allocation

| Pod | QoS | CPU req→lim | Mem req→lim | Note |
|---|---|---|---|---|
| postgres | **Guaranteed** | 2500m | 6Gi | SUT ceiling; extra RAM = page cache headroom |
| cart (total) | **Guaranteed** | 3000m | 2Gi | held constant across profiles (see below) |
| pgbouncer | **Guaranteed** | 1000m | 256Mi | full core — never the secret limiter |
| redis | **Guaranteed** | 500m | 512Mi | Redis-arm only |
| prometheus | Burstable | 100m → 500m | 256Mi → 1.5Gi | scrapes during window (5s) |
| grafana | Burstable | 200m → 1000m | 512Mi → 1Gi | idle during window; view/screenshot at run end |
| otel-collector | Burstable | 50m → 200m | 64Mi → 512Mi | |
| cadvisor | Burstable | 50m → 200m | 64Mi → 256Mi | |
| postgres-exporter | Burstable | 50m → 200m | 64Mi → 128Mi | |
| pgbouncer-exporter | Burstable | 50m → 100m | 32Mi → 64Mi | |
| redis-exporter | Burstable | 50m → 100m | 32Mi → 64Mi | |
| ticket-manager | Burstable | 100m → 500m | 128Mi → 256Mi | idle during window; up only for re-seeding via Swagger |
| ticket-info | — | scaled to 0 | — | not SUT |

## Budget check

- **CPU requests** (what the scheduler reserves) ≈ **7.65 cores** → fits 8c.
- **CPU limits** burst above 8c, but only Burstable pods, and only if CPU is free. Guaranteed pods (7.0c) always get their share.
- **Mem requests** ≈ 9.9 Gi → fits. **Mem worst-case (all limits)** ≈ 12.5 Gi of ~14.5 usable.
- Remaining RAM is intentionally free → kernel page cache for Postgres data files. Dataset (300k rows) is small, so this is safe headroom rather than a tuned cache target.

## Cart profiles

Cart total budget held constant (~3.0c / 2Gi) across all profiles so RQ1/RQ4 reflect
**topology**, not raw resource. Set via `./set-cart-profile.zsh <1|3|5>`.

| Profile | replicas | cpu/pod | mem/pod | DB_POOL_SIZE |
|---|---|---|---|---|
| 1 | 1 | 3000m | 2048Mi | 8 |
| 3 | 3 | 1000m | 683Mi | 3 |
| 5 | 5 | 600m | 410Mi | 2 |
