# ticket-load-test

A research prototype simulating a concurrent concert ticketing system. This serves as a **baseline** for studying correctness and performance trade-offs in distributed reservation workflows under high load.

The system is built as a set of microservices using an asynchronous, event-driven architecture backed by Redis Streams and PostgreSQL.

---

## Resource Allocation

Designed for a single node with **8 CPU cores / 16 GB RAM**. ~1.5 GB reserved for Kubernetes system components, leaving ~14.5 GB usable.

### Base Workloads

SUT-critical pods (cart, postgres, pgbouncer, redis) run **Guaranteed QoS** (requests == limits). Cart values shown are the **profile 3** baseline; `set-cart-profile.zsh` rewrites them per profile. See `RESOURCE-ALLOCATION.md` for the full breakdown.

| Service | CPU Request | CPU Limit | Memory Request | Memory Limit |
|---|---|---|---|---|
| **cart** (×3, Guaranteed) | 1000m | 1000m | 683Mi | 683Mi |
| **postgres** (Guaranteed) | 2500m | 2500m | 6Gi | 6Gi |
| **pgbouncer** (Guaranteed) | 1000m | 1000m | 256Mi | 256Mi |
| **redis** (Guaranteed) | 500m | 500m | 512Mi | 512Mi |
| ticket-manager | 100m | 500m | 128Mi | 256Mi |
| ticket-info | scaled to 0 during runs | — | — | — |
| prometheus | 100m | 500m | 256Mi | 1536Mi |
| grafana | 200m | 1000m | 512Mi | 1Gi |
| otel-collector | 50m | 200m | 64Mi | 512Mi |
| cadvisor | 50m | 200m | 64Mi | 256Mi |
| postgres-exporter | 50m | 200m | 64Mi | 128Mi |
| pgbouncer-exporter | 50m | 100m | 32Mi | 64Mi |
| redis-exporter | 50m | 100m | 32Mi | 64Mi |

**Totals (profile 3):** ~7.65 cores requested · ~9.9 Gi requested / ~12.5 Gi limited (of ~14.5 Gi usable).

Postgres receives the largest allocation by design — `shared_buffers=2048MB` keeps hot data in memory and minimizes disk I/O, making it the primary performance lever. Remaining RAM is left free for kernel page cache.

### Cart Replica Profiles (`set-cart-profile.zsh`)

Used to isolate the cart bottleneck across different horizontal scaling configurations while keeping total node resource usage within budget. Run `./set-cart-profile.zsh <1|3|5>`.

| Profile | Replicas | CPU per pod | Memory per pod | Total cart memory limit |
|---|---|---|---|---|
| `1` | 1 | 4000m req / 5000m lim | 3Gi req / 4Gi lim | 4Gi |
| `3` | 3 | 1500m req / 1700m lim | 1Gi req / 1300Mi lim | ~3.8Gi |
| `5` | 5 | 900m req / 1000m lim | 512Mi req / 800Mi lim | 4Gi |

All three profiles target ~4 Gi total cart memory limit, so comparisons reflect replica count and per-pod headroom — not raw resource advantage. PGBouncer is configured with `pool_mode=transaction`, `max_client_conn=1000`, and `default_pool_size=150` to absorb connection spikes across all profiles.
