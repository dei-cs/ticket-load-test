# Load-Test Plan

Stress-testing a centralized PostgreSQL ticketing system under high write load on fixed hardware (8 CPU cores / 16 GB RAM). This document defines the hypotheses, controlled variables, run matrices, and per-run procedure for a master's thesis in computer science.

---

## 1. Research questions and hypotheses

| ID | Research question | Hypothesis |
|----|-------------------|------------|
| **RQ1** | Given a fixed total compute budget, what split of CPU between Postgres and the cart write service maximizes throughput? | Throughput is maximized where Postgres gets the majority of the budget. Starving Postgres makes the DB the bottleneck; on this hardware, DB is the dominant consumer so the optimum skews DB-heavy. |
| **RQ2** | How many DB connections per cart pod maximize Postgres throughput before coordination overhead and idle-connection cost dominate? | Throughput rises with pool size up to ~50 connections/pod, where active Postgres backends ≈ effective CPU parallelism. Beyond that, lock/latch contention and context-switch overhead flatten or reduce throughput. |
| **RQ3** | Does Redis offload the database? | The Redis path reduces per-request Postgres work — no `SELECT … FOR UPDATE SKIP LOCKED` scan — lowering Postgres CPU per reservation and raising throughput at equal load. |
| **RQ4** | Can a centralized, strongly-consistent Postgres scale as the write service scales horizontally (1 → 3 → 5 cart replicas)? | Throughput scales sub-linearly with cart replicas and saturates at a Postgres-bound ceiling. The database, not the app tier, is the limiting resource. |

**Thesis framing.** RQ1 and RQ2 are *prerequisite calibration* — they fix the compute split and connection knob so RQ3 and RQ4 compare like-for-like. RQ3 isolates the caching lever. RQ4 isolates the horizontal-scaling lever.

---

## 2. System under test

- **Write service:** `cart` (FastAPI + asyncpg), the only service exercised by the load test.
- **Endpoints under test:**
  - **No-Redis path:** `POST /cart/reserve-batch` — single `SELECT … FOR UPDATE SKIP LOCKED` + `UPDATE` in one transaction. Run with `REDIS_ENABLED=false`.
  - **Redis path:** `POST /cart/reserve-batch-redis` — one `LPOP` from Redis per ticket, then a targeted single-row `UPDATE`. Run with `REDIS_ENABLED=true`; cache pre-warmed.
- **Data path:** cart → PgBouncer (`pool_mode=transaction`) → Postgres.
- **Hardware:** single node, 8 cores / 16 GB. ~1.5 GB reserved for k8s; ~14.5 GB usable.
- **Load generator:** external machine, **2500 concurrent clients**.

### 2.1 Fixed parameters (held constant across all runs unless that run varies them)

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| Postgres + cart CPU budget | 5000m total (req=lim, Guaranteed) | Split between them is the RQ1 lever. pgbouncer (500m) + redis (500m) held constant. |
| Concurrent clients | 2500 | Fixed load level. |
| Batch size `count` | 1 | Eliminates batch-size variance from throughput deltas. |
| Postgres `max_connections` | 250 | Server-side cap. |
| Postgres `shared_buffers` | 2048MB | Hot data resident in RAM. |
| Postgres `synchronous_commit` | off | Write-throughput lever; held constant. |
| PgBouncer `pool_mode` | transaction | Multiplexes client conns onto ≤ `default_pool_size` server conns. |
| PgBouncer `max_client_conn` | 2000 | App-side accept cap. |
| Tickets seeded per run | 1,000,000 available | Prevents inventory depletion within the measurement window. |

> **Connection identity:** `total PgBouncer client conns = replicas × connections_per_pod`. PgBouncer multiplexes these onto at most `default_pool_size` Postgres server connections. Keep total client conns ≤ `max_client_conn` (2000).

> **For Phases 2–4:** CPU split is pinned at the RQ1-optimal result. Pool size is pinned at the RQ2-optimal result from Phase 2 onward.

> **On inventory depletion.** At sustained throughput, 60 s can consume hundreds of thousands of tickets. Seed 1M each time unless the prior run confirmed headroom remaining — check inventory count before reusing.

---

## 3. Metrics captured (per run)

Captured from Prometheus / Grafana + load tool client-side stats. Screenshot the Grafana dashboard at run end (time range = steady-state window).

**Primary (throughput & latency):**
- Sustained throughput — successful reservations/sec (steady-state mean).
- Request rate — total HTTP requests/sec.
- Latency percentiles — p50 / p95 end-to-end (client-side) and server-side HTTP duration.

**Outcome breakdown:**
- Success rate (HTTP 200).
- `NO_TICKETS_AVAILABLE` (503) rate.
- `DOUBLE_BOOKING_DETECTED` (409) rate — must stay **0** on all paths; any non-zero is a correctness failure.
- Client-side errors / timeouts / connection resets.

**Resource & saturation:**
- Postgres CPU % (primary bottleneck signal).
- Postgres active vs. idle connections.
- PgBouncer pool utilization (active server conns / `default_pool_size`), `cl_waiting` count.
- Cart CPU % per replica and aggregate.
- Cart memory per replica.
- Redis ops/sec and CPU (Redis path only).

**Derived:**
- **Postgres CPU per successful reservation** = PG CPU-seconds ÷ successful reservations — core RQ3 offload metric.
- Throughput per cart CPU core — scaling efficiency for RQ4.

---

## 4. Standard per-run procedure

**Setup (once per configuration):**
1. Apply the configuration for the phase manually (CPU split, pool size, replica count, Redis toggle).
2. `kubectl get pods -n ticket-system` — confirm all pods Ready.
3. Port-forward Grafana; start `minikube tunnel`.
4. Seed 1,000,000 available tickets into the DB (or verify sufficient inventory remains from prior run).
5. **Redis arm only:** warm the cache (`tickets:available_ids` populated with seeded IDs). Verify list length matches inventory.

**Execute:**
6. Record wall-clock start timestamp.
7. Start the external load tool: 2500 concurrent clients, `count=1`, target endpoint, fixed duration.
8. Discard the first **30 s** warmup. Measure over a fixed **60 s steady-state window**.

**Capture & reset:**
9. Screenshot Grafana panels (time range = steady-state window).
10. Record all §3 metrics in the results table.
11. Reset only what the next run requires. Re-seed if inventory depleted.

**Repetition:** one run per configuration. Discard and re-run only if an infrastructure anomaly occurs (node throttle, port-forward drop); note it.

### 4.1 Steady-state definition
A run is in steady state when throughput and Postgres CPU are stationary (no trend over a 30 s sliding window) and inventory is not exhausted. Only the steady-state window feeds the reported numbers.

---

## 5. Experiment phases

**Run budget:**

| Phase | Configs | Runs |
|---|---|---|
| 1 — resource allocation (CPU split) | 4 | 4 |
| 2 — connection pool sizing | 5 | 5 |
| 3 — Redis vs no-Redis | 2 | 2 |
| 4 — horizontal scaling | 6 | 6 |
| **Total** | | **17 runs** |

---

### Phase 1 — RQ1: Resource allocation (Postgres ↔ cart CPU split)

**Goal:** find the CPU split that maximizes throughput at a fixed total compute budget (postgres + cart = 5000m).

**Held constant:** Redis OFF (`/cart/reserve-batch`), 1 cart replica, provisional pool (50 conns/pod — Phase 2 expected optimum, chosen to keep pool from being the bottleneck), 2500 clients, batch 1.

**Varied:** the split between Postgres and cart.

| Postgres (m) | Cart (m) | Note |
|---|---|---|
| 4000 | 1000 | DB-heavy |
| 3500 | 1500 | |
| 3000 | 2000 | current default |
| 2500 | 2500 | balanced |

**Stop rule:** if throughput is still monotonically tracking Postgres CPU toward one extreme, add the adjacent point (e.g. 4500/500) rather than sweeping finer in the middle. Stop when the trend is clear.

**Analysis:** plot throughput vs. split. Identify which side saturates at each point (Postgres CPU vs. cart CPU). The optimal split is the highest-throughput point where Postgres CPU is the ceiling.

**Deliverable:** optimal CPU split, carried into Phases 2–4.

#### Results
| Postgres (m) | Cart (m) | Throughput rsv/s | p95 ms | PG CPU % | Cart CPU % | PgB pool % | cl_waiting | Bottleneck | deadlocks |
|---|---|---|---|---|---|---|---|---|---|
| 4000 | 1000 | | | | | | | | |
| 3500 | 1500 | | | | | | | | |
| 3000 | 2000 | | | | | | | | |
| 2500 | 2500 | | | | | | | | |

**Chosen optimal split:** ______m / ______m
**Saturating side at optimum:** ☐ Postgres CPU  ☐ Cart CPU  ☐ PgBouncer pool

---

### Phase 2 — RQ2: Connection pool sizing

**Goal:** find the connections-per-pod that maximize Postgres throughput without coordination overhead or idle-connection waste dominating.

**Held constant:** Redis OFF (`/cart/reserve-batch`), 1 cart replica, RQ1-optimal CPU split, 2500 clients, batch 1.

**Varied:** connections per pod. Expected optimum ~50; sweep below and above.

| Connections per pod | Note |
|---|---|
| 20 | well under |
| 35 | under |
| 50 | expected optimum |
| 65 | over |
| 80 | well over |

**Stop rule:** if throughput is still trending at either extreme, add the adjacent data point rather than sweeping finer in the middle.

**Analysis:** plot throughput and p95 latency vs. connections per pod. Identify the knee — the point past which more connections add coordination overhead without throughput gain. Cross-check whether PgBouncer (`cl_waiting` > 0, pool 100%) or Postgres (CPU bound, idle conns growing) is the limiter.

**Deliverable:** optimal pool size + a clear statement of which hop saturates first. Carried into Phases 3–4.

#### Results
| Conns/pod | Throughput rsv/s | p95 ms | PG CPU % | PG active conns | PgB pool % | cl_waiting | Limiter | deadlocks |
|---|---|---|---|---|---|---|---|---|
| 20 | | | | | | | | |
| 35 | | | | | | | | |
| 50 | | | | | | | | |
| 65 | | | | | | | | |
| 80 | | | | | | | | |

**Chosen optimum:** ______   **First hop to saturate:** ☐ PgBouncer  ☐ Postgres

---

### Phase 3 — RQ3: Redis vs. no-Redis

**Goal:** prove or refute that Redis offloads Postgres.

**Held constant:** RQ1-optimal CPU split, RQ2-optimal pool size, **1 cart replica**, 2500 clients, batch 1.

**Varied:** two arms.

| Arm | Endpoint | REDIS_ENABLED | Cache |
|---|---|---|---|
| A — SQL only | `/cart/reserve-batch` | false | n/a |
| B — Redis | `/cart/reserve-batch-redis` | true | pre-warmed |

**Headline metric:** Postgres CPU per successful reservation (Arm B should be lower) and sustained throughput (Arm B should be higher at equal Postgres CPU).

**Secondary:** p95 latency, Postgres connection utilization, Redis CPU/ops/sec (to show the cost moved, not vanished).

> **Caveat to report honestly:** the Redis path still issues one single-row `UPDATE` to Postgres per ticket. It removes the `FOR UPDATE SKIP LOCKED` scan and lock contention, not the durable write. The offload claim is precise: Redis offloads availability lookup and lock contention, not the write itself.

#### Results
| Arm | Throughput rsv/s | p95 ms | PG CPU/rsv (calc) | PG cores | PG TPS | PG conn % | Redis LPOP/s | Redis CPU % | deadlocks |
|---|---|---|---|---|---|---|---|---|---|
| A — SQL only | | | | | | | n/a | n/a | |
| B — Redis | | | | | | | | | |

**Offload verdict:** Arm B PG-CPU/rsv ____ vs Arm A ____  →  ☐ offload confirmed  ☐ refuted

---

### Phase 4 — RQ4: Horizontal scaling of the write service

**Goal:** determine whether a centralized, strongly-consistent Postgres scales as the cart tier scales out.

**Held constant:** RQ1-optimal CPU split, RQ2-optimal pool size, 2500 clients, batch 1. Postgres CPU allocation stays fixed across profiles. HPA disabled.

**Varied:** replica count ∈ {1, 3, 5}. Run both Redis OFF and Redis ON as two series (6 runs total).

| Profile | Replicas | Series |
|---|---|---|
| 1 | 1 | Redis off + on |
| 3 | 3 | Redis off + on |
| 5 | 5 | Redis off + on |

**Analysis:** plot throughput vs. replica count for both series. Compute scaling efficiency (throughput(N) / throughput(1)). Expect sub-linear scaling converging on a Postgres-bound ceiling. Identify the saturating resource (Postgres CPU, PgBouncer pool, or WAL/checkpoint).

#### Results — Redis OFF
| Replicas | Throughput rsv/s | Scaling vs 1× | p95 ms | PG CPU % | PG conn % | PgB pool % | cl_waiting | ckpt req/s | deadlocks |
|---|---|---|---|---|---|---|---|---|---|
| 1 | | 1.00 | | | | | | | |
| 3 | | | | | | | | | |
| 5 | | | | | | | | | |

#### Results — Redis ON
| Replicas | Throughput rsv/s | Scaling vs 1× | p95 ms | PG CPU % | PG conn % | PgB pool % | Redis LPOP/s | Redis CPU % | deadlocks |
|---|---|---|---|---|---|---|---|---|---|
| 1 | | 1.00 | | | | | | | |
| 3 | | | | | | | | | |
| 5 | | | | | | | | | |

**Saturating resource at ceiling:** ☐ Postgres CPU  ☐ PgBouncer pool  ☐ WAL/checkpoint  ☐ Redis CPU

**Scaling verdict:** ☐ near-linear  ☐ sub-linear, PG-bound ceiling at ____ rsv/s

---

## 6. Analysis and presentation plan

For each RQ, the thesis presents:

1. **A figure** — throughput (and p95 latency) vs. the swept variable. One run per point; the trend across the sweep carries the result.
2. **Bottleneck attribution** — which resource saturated, evidenced by the §3 saturation metrics.
3. **The decision** — chosen optimum and why, carried forward into later phases.
4. **Correctness statement** — double-booking count (must be 0) under peak load, demonstrating strong consistency held while scaling.

**Cross-cutting narrative:**
- RQ1 → "where to put the compute on fixed hardware."
- RQ2 → "how many connections feed the database efficiently without overwhelming it."
- RQ3 → "what caching buys a centralized DB, and what it does not."
- RQ4 → "how far a single strongly-consistent Postgres scales under a horizontally-scaled write tier on fixed hardware, and what stops it."

---

## 7. Threats to validity

- **Single-node co-location:** Postgres, cart, PgBouncer, Redis, and observability share 8 cores. Observability overhead competes for CPU — keep its allocation fixed and account for it.
- **Inventory exhaustion** confounds throughput with 503 rate — guard with the 1M seed and verify before each run.
- **`synchronous_commit=off`** trades durability for throughput; results describe this configuration, not a fully-durable one.
- **PgBouncer `transaction` mode** means no session-level features; valid here since reservations are single transactions.
- **`statement_cache_size=0`** on the asyncpg pool (required for PgBouncer transaction mode) disables prepared-statement caching — a fixed cost present in all runs.
- **Warmup / steady-state windowing** must be identical across runs or comparisons are invalid.
- **Network variance** from the external load generator — run on a quiet network; report client-side timeout/error rates.

---

## 8. Run log template

| Run ID | Phase | Replicas | PG/cart split (m) | Conns/pod | Redis | Endpoint | Throughput rsv/s | p50/p95 ms | PG CPU % | PG conn % | PgB pool % / cl_waiting | Cart CPU % | PG CPU/rsv | deadlocks | Notes |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| | | | | | | | | | | | | | | | |
