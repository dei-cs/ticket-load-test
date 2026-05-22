# Load-Test Results

Results companion to `TEST-PLAN.md`. One section per phase. Each section lists the Grafana panels to screenshot and a results table scoped to that phase's RQ.

> Capture protocol: set Grafana time range to the 60 s steady-state window (discard first 30 s warmup), screenshot the listed panels, then fill the table.

---

## Dashboard reference

| TEST-PLAN §3 metric | Dashboard status | Source |
|---|---|---|
| p50 / p95 latency | ✅ panels id 3, id 4 | Read from dashboard. p95 is the reported tail metric. |
| Postgres CPU % | ✅ panel id 7 (KSM limit denominator) | Read from dashboard. |
| Cart CPU % | ✅ panel id 6 (KSM limit denominator) | Read from dashboard. |
| Cart memory % | ✅ panel id 9 | Read from dashboard. |
| PG active vs idle conns | ✅ id 16 (by state), id 17 (usage %) | Read from dashboard. |
| PgBouncer pool util / cl_waiting | ✅ id 24 (pool util %), id 26 (pool conns — `client waiting` series) | Read from dashboard. |
| Redis ops/sec | ✅ LPOP rate id 38 | Read from dashboard. |
| Redis CPU | ✅ id 36 | Read from dashboard. |
| WAL / checkpoint pressure | ✅ Checkpoint & write pressure id 40 | Read from dashboard. |
| CPU cores by pod | ✅ id 13 | Needed for PG-CPU/rsv derived metric. |
| PG transactions/sec | ✅ id 18 | Read from dashboard. |
| Total deadlocks | ✅ id 20 | Must stay 0 on all paths. |
| PG CPU per reservation (derived) | ❌ no panel | Compute: PG cores (id 13) ÷ throughput (rsv/s). |
| Throughput per cart core (derived) | ❌ no panel | Compute: throughput ÷ cart cores (id 13). |

---

## Phase 1 — RQ1: Resource allocation (Postgres ↔ cart CPU split)

**Question:** which CPU split maximizes throughput, and which side saturates.
**Held constant:** Redis OFF, 1 replica, provisional pool (50 conns/pod), 2500 clients, batch 1.
**Varied:** Postgres/cart split of the 5000m budget.

**Panels to screenshot per run:**
- p95 (id 4) — primary outcome
- Postgres CPU % (id 7) + Cart CPU % (id 6) — which side saturates
- CPU cores by pod (id 13) — absolute cores, also needed for PG-CPU/rsv calc
- Connections by state (id 16) — is PG backend-bound
- Pool utilization % (id 24) + pool connections (id 26, `client waiting` series) — is PgBouncer the limiter
- Total deadlocks (id 20)

| Postgres (m) | Cart (m) | Throughput rsv/s `client` | p95 ms `id4` | PG CPU % `id7` | PG cores `id13` | Cart CPU % `id6` | Cart cores `id13` | PgB pool % `id24` | cl_waiting `id26` | PG active conns `id16` | PG CPU/rsv `calc` | deadlocks `id20` | Bottleneck |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 4000 | 1000 | 719.4 | 5220 | 60% | 2.4 | 100% | 1.0 | 81.8% | 125 | 10–15 | 0.0033 | 0 | Cart CPU |
| 3500 | 1500 | 1001.7 | 2270 | 80% | 3.0 | 100% | 1.5 | 75% | 150 | 15–20 | 0.0030 | 0 | Cart CPU |
| 3000 | 2000 | 1023.6 | 3100 | 95% | 2.8 | 80% | 1.75 | 75% | 150 | 15–20 | 0.0027 | 0 | Postgres CPU |
| 2500 | 2500 | 1016.6 | 1500 | 100% | 2.5 | 80% | 2.0 | 78.1% | 160 | 10–20 | 0.0025 | 0 | Postgres CPU |

**Chosen optimal split:** 3000m / 2000m

> **Note — noisy p95.** p95 does not track throughput across the sweep (5220 → 2270 → 3100 → 1500 ms while throughput stays flat ~720→1020). Latency is decoupled from server saturation: throughput plateaus ~1020 rsv/s and PG CPU climbs to 100%, yet p95 *falls* at the most PG-bound point. Likely client-side queueing / connection-wait variance, not server work. cl_waiting holds ~150–160 every run → requests wait at the PgBouncer queue regardless of split, so measured p95 reflects queue depth, not DB service time. Treat p95 here as indicative only; report throughput + saturation as the RQ1 result and revisit latency under controlled pool size in Phase 2.

---

## Phase 2 — RQ2: Connection pool sizing

**Question:** which connections-per-pod maximizes throughput, and which hop saturates first.
**Held constant:** Redis OFF, 1 replica, 3000m postgres / 2000m cart (optimal P1 carried forward) split, 2500 clients, batch 1.
**Varied:** connections per pod ∈ {20, 35, 50, 65}.

**Panels to screenshot per run:**
- p95 (id 4) — primary outcome
- Pool utilization % (id 24), PgBouncer pool connections (id 26, `client waiting` series) — RQ2 core
- Connections by state (id 16) + Connection usage % (id 17) — PG active vs idle
- CPU cores by pod (id 13) — for PG-CPU/rsv derived metric
- Postgres CPU % (id 7)
- Total deadlocks (id 20)

| Conns/pod | Throughput rsv/s `client` | p95 ms `id4` | PG CPU % `id7` | PG cores `id13` | PG active conns `id16` | PG conn % `id17` | PgB pool % `id24` | cl_waiting `id26` | PG CPU/rsv `calc` | deadlocks `id20` |
|---|---|---|---|---|---|---|---|---|---|---|
| 20 | 973.1 | 5430 | 90% | 2.5 | 10 | 27.2% | 66.7% | 50 | 0.0026 | 0 |
| 35 | 1127.5 | 1820 | 90% | 2.6 | 15 | 28.3% | 70% | 100 | 0.0023 | 0 |
| 50 | 1023.6 | 3100 | 95% | 2.8 | 15–20 | 28.4% | 75% | 150 | 0.0027 | 0 |
| 65 | 992.2 | 3890 | 80% | 2.5 | 17 | 28.9% | 87.5% | 225 | 0.0025 | 0 |

**Chosen optimum:** 35 conns/pod

---

## Phase 3 — RQ3: Redis vs. no-Redis

**Question:** does Redis lower Postgres CPU per reservation and raise throughput.
**Held constant:** RQ1-optimal split (4000m/1000m), RQ2-optimal pool size, 1 replica, 2500 clients, batch 1.
**Varied:** Arm A SQL-only vs Arm B Redis.

**Panels to screenshot per arm:**
- p95 (id 4)
- CPU cores by pod (id 13) — for PG-CPU/rsv headline
- Transactions/sec (id 18) — PG write load
- Connection usage % (id 17), Connections by state (id 16)
- Redis: LPOP rate (id 38), Redis CPU % (id 36) — Arm B only (shows cost moved, not vanished)
- Buffer cache hit ratio (id 32)
- Total deadlocks (id 20)

| Arm | Endpoint | Throughput rsv/s `client` | PG CPU/rsv `calc` | PG cores `id13` | PG TPS `id18` | p95 ms `id4` | PG conn % `id17` | Redis LPOP/s `id38` | Redis CPU % `id36` | deadlocks `id20` |
|---|---|---|---|---|---|---|---|---|---|---|---|
| A — SQL only | /cart/reserve-batch | | | | | | | n/a | n/a | |
| B — Redis | /cart/reserve-batch-redis | | | | | | | | | |

**Offload verdict:** Arm B PG-CPU/rsv ____ vs Arm A ____  →  ☐ offload confirmed  ☐ refuted
**Where the cost moved:** Redis LPOP/s ____, Redis CPU % ____ (lookup + lock contention removed; durable UPDATE remains)

---

## Phase 4 — RQ4: Horizontal scaling of the write service

**Question:** does centralized PG scale as cart scales out; what stops it.
**Held constant:** RQ1-optimal split (4000m/1000m), RQ2-optimal pool, 2500 clients, batch 1. HPA disabled.
**Varied:** replicas ∈ {1, 3, 5} × Redis {off, on} = 6 runs.

**Panels to screenshot per run:**
- p95 (id 4)
- CPU cores by pod (id 13) — per-replica cart + PG cores
- Connection usage % (id 17), Connections by state (id 16) — PG ceiling
- Pool utilization % (id 24), pool connections (id 26, `client waiting` series) — PgBouncer ceiling
- Transactions/sec (id 18) — PG write ceiling
- Checkpoint & write pressure (id 40) — WAL/checkpoint ceiling
- Redis LPOP/s (id 38), Redis CPU % (id 36) — Redis-on series only
- Total deadlocks (id 20)

### Redis OFF series
| Replicas | Throughput rsv/s `client` | Scaling vs 1× `calc` | p95 ms `id4` | PG CPU % `id7` | PG cores `id13` | Thrpt/cart-core `calc` | PG conn % `id17` | PgB pool % `id24` | cl_waiting `id26` | PG TPS `id18` | ckpt req/s `id40` | deadlocks `id20` |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | | 1.00 | | | | | | | | | | |
| 3 | | | | | | | | | | | | |
| 5 | | | | | | | | | | | | |

### Redis ON series
| Replicas | Throughput rsv/s `client` | Scaling vs 1× `calc` | p95 ms `id4` | PG CPU % `id7` | PG cores `id13` | Thrpt/cart-core `calc` | PG conn % `id17` | PgB pool % `id24` | Redis LPOP/s `id38` | Redis CPU % `id36` | ckpt req/s `id40` | deadlocks `id20` |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | | 1.00 | | | | | | | | | | |
| 3 | | | | | | | | | | | | |
| 5 | | | | | | | | | | | | |

**Saturating resource at ceiling:** ☐ Postgres CPU (id 7)  ☐ PgBouncer pool (id 24/26)  ☐ WAL/checkpoint (id 40)  ☐ Redis CPU (id 36)
**Scaling verdict:** ☐ near-linear  ☐ sub-linear, PG-bound ceiling at ____ rsv/s

---

## Cross-cutting correctness ledger

Deadlocks MUST be 0. Rollback % near 0. No sustained idle-in-txn or lock waiters. Any deadlock = a contention/correctness event to report.

| Run ID | Phase | deadlocks `id20` | rollback % `id19` | idle-in-txn `id28` | lock waiters `id29` | Notes |
|---|---|---|---|---|---|---|
| | | | | | | |

---

## Run log

| Run ID | Phase | Replicas | PG/cart split (m) | Conns/pod | Redis | Endpoint | Throughput rsv/s | p50/p95 ms | PG CPU % | PG conn % | PgB pool % / cl_waiting | Cart CPU % | PG CPU/rsv | deadlocks | Notes |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| | | | | | | | | | | | | | | | |
