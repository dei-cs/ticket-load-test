# Systematic Load-Test Plan

Stress-testing a centralized PostgreSQL ticketing system under high write load. The aim is to push a single, strongly-consistent Postgres instance to its maximum sustainable write throughput on fixed hardware (8 CPU cores / 16 GB RAM), and to quantify how application-side design choices — connection pooling, worker concurrency, horizontal replication of the write service, and a Redis availability cache — shift that ceiling.

This document is the experimental protocol for a master's thesis in computer science. It defines the hypotheses, the controlled and measured variables, the run matrix, the per-run procedure, and the analysis plan needed to produce reproducible, defensible results.

---

## 1. Research questions and hypotheses

| ID | Research question | Hypothesis |
|----|-------------------|------------|
| **RQ1** | What is the optimal number of Uvicorn workers per cart replica for each replica profile (1, 3, 5)? | Throughput rises with workers until CPU saturation or pool contention, then plateaus/declines. Optimal workers per replica decreases as replica count rises (fixed total CPU budget). |
| **RQ2** | How many DB connections per worker (and thus total PgBouncer client connections) maximize Postgres throughput before coordination overhead and idle-connection cost dominate? | Throughput increases with pool size up to the point where active Postgres backends ≈ effective CPU parallelism; beyond that, lock/latch and context-switch overhead flatten or reduce throughput. |
| **RQ3** | Does Redis offload the database? | The Redis path (`/cart/reserve-batch-redis`) reduces per-request Postgres work (no `SELECT … FOR UPDATE SKIP LOCKED` scan), lowering Postgres CPU per reservation and raising end-to-end throughput vs. the SQL-only path at equal load. |
| **RQ4** | Can a single centralized, strongly-consistent Postgres scale to serve a modern cloud application when the write service scales horizontally (1 → 3 → 5 cart replicas)? | Throughput scales sub-linearly with cart replicas and saturates at a Postgres-bound ceiling; the database, not the app tier, is the limiting resource. |

**Thesis framing.** RQ1 and RQ2 are *prerequisite calibration* experiments — they fix the tuning knobs so that RQ3 and RQ4 compare like-for-like. RQ3 isolates the caching lever. RQ4 isolates the horizontal-scaling lever.

---

## 2. System under test (SUT)

- **Write service:** `cart` (FastAPI + asyncpg), the only service exercised by the load test.
- **Endpoints under test:**
  - **No-Redis path:** `POST /cart/reserve-batch` → `reserve_ticket_batch_atomic_with_locking` (single `SELECT … FOR UPDATE SKIP LOCKED` + `UPDATE` in one transaction). Run with `REDIS_ENABLED=false` everywhere.
  - **Redis path:** `POST /cart/reserve-batch-redis` → `reserve_ticket_batch_redis` (one `LPOP` from Redis per ticket, then a targeted single-row `UPDATE`). Run with `REDIS_ENABLED=true` everywhere; cache pre-warmed.
- **Data path:** cart → PgBouncer (`pool_mode=transaction`) → Postgres.
- **Hardware:** single node, 8 cores / 16 GB. ~1.5 GB reserved for k8s; ~14.5 GB usable.
- **Load generator:** external machine, **3000 concurrent clients**, hitting the node over the network. Leftover in-repo test scripts are ignored.

### 2.1 Fixed parameters (held constant across ALL runs unless that run varies them)

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| Concurrent clients | 3000 | Fixed load level for all comparisons. |
| Batch size `count` | **Fixed at 2** (not random 1–5) | Comparability — random batch size adds variance that confounds throughput deltas. Choose one value and hold it. |
| Postgres `max_connections` | 250 | Server-side cap. |
| Postgres `shared_buffers` | 2048MB | Hot data resident in RAM. |
| Postgres `synchronous_commit` | off | Write-throughput lever; keep constant. |
| PgBouncer `pool_mode` | transaction | Multiplexes client conns onto ≤ `default_pool_size` server conns. |
| PgBouncer `max_client_conn` | 2000 | App-side accept cap. |
| Cart total CPU budget | ~3.0 cores across all replicas (req==lim, Guaranteed) | Each profile targets the same total, so RQ1/RQ4 reflect topology, not raw resource advantage. |
| Cart total memory limit | ~2 Gi across all replicas | Same intent as CPU. |
| Tickets seeded per run | 300,000 available | Enough inventory so runs do not deplete inventory before the steady-state window ends. |

> **Note on inventory depletion.** 3000 clients × batch 2 reserves ~6000 tickets per concurrency wave. Confirm the steady-state measurement window does not exhaust the 300k seeded tickets; if it does, raise the seed count or shorten the window. Inventory exhaustion turns the run into a `503 NO_TICKETS_AVAILABLE` benchmark, not a write-throughput benchmark.

---

## 3. Metrics captured (per run)

Captured from Prometheus / Grafana + the load tool's own client-side stats. Screenshot the Grafana dashboard manually at run end (set the time range to the steady-state window).

**Primary (throughput & latency):**
- Sustained throughput — successful reservations/sec (steady-state mean).
- Request rate — total HTTP requests/sec.
- Latency percentiles — p50 / p95 / p99 end-to-end (client-side, from load tool) and server-side (`reservation_duration` histogram).

**Outcome breakdown (correctness under load):**
- Success rate (HTTP 200).
- `NO_TICKETS_AVAILABLE` (503) rate.
- `DOUBLE_BOOKING_DETECTED` (409) rate — must stay **0** on the safe paths; any non-zero is a correctness failure to report.
- Client-side errors / timeouts / connection resets.

**Resource & saturation (the "why"):**
- Postgres CPU % (primary bottleneck signal).
- Postgres active vs. idle connections (% of `max_connections=250`).
- PgBouncer pool utilization (active server conns / `default_pool_size`), waiting-client count, `cl_waiting`.
- Cart CPU % per replica and aggregate (vs. profile denominator).
- Cart memory per replica.
- Redis ops/sec and CPU (Redis path only).

**Derived (for analysis):**
- **Postgres CPU per successful reservation** = Postgres CPU-seconds / successful reservations — the core RQ3 offload metric.
- Throughput per cart CPU core — scaling efficiency for RQ4.

---

## 4. Required code/config change before starting

`cart/main.py:48` hardcodes `uvicorn.run(…, workers=4)`. RQ1 requires sweeping worker count, so make it env-driven:

```python
WORKERS = int(os.getenv("WORKERS", "4"))
uvicorn.run("main:app", host="0.0.0.0", port=8003, workers=WORKERS)
```

Then add a `WORKERS` env var to `k8s/apps/cart/cart-deployment.yaml` and set it per run (`kubectl set env deployment/cart -n ticket-system WORKERS=<n>`). Without this, RQ1 cannot vary workers.

> **Connection-count identity used throughout:**
> `total PgBouncer client conns = replicas × workers × DB_POOL_SIZE`.
> PgBouncer multiplexes these onto at most `default_pool_size` (200) Postgres server connections. Keep total client conns ≤ `max_client_conn` (2000) and design `default_pool_size` ≤ `max_connections` (250).

---

## 5. Standard per-run procedure

Every run follows the same protocol so runs are comparable and reproducible.

**Setup (once per configuration):**
1. `./set-cart-profile.zsh <1|3|5>` — sets replicas, per-pod resources, and baseline `DB_POOL_SIZE`.
2. Set the run's `WORKERS` and (if varied) `DB_POOL_SIZE` via `kubectl set env`.
3. Set Redis flag for the arm: `kubectl set env deployment/cart -n ticket-system REDIS_ENABLED=<true|false>` (and ticket-info if relevant).
4. `kubectl get pods -n ticket-system` — confirm all Ready.
5. `stern -n ticket-system -l app=cart` — live log tail.
6. Port-forward Grafana; start `minikube tunnel`.
7. Seed 300,000 available tickets into the DB.
8. **Redis arm only:** warm the cache (`tickets:available_ids` populated with the seeded IDs). Verify list length matches inventory.

**Execute:**
9. Record wall-clock start timestamp.
10. Start the external load tool: 3000 concurrent clients, fixed `count=2`, target the arm's endpoint, fixed run duration (see §6.1).
11. Let the system reach steady state (discard the first **30 s** warmup), then measure over a fixed **steady-state window** (e.g. 120 s).

**Capture & reset:**
12. Screenshot the Grafana dashboard panels (time range = steady-state window).
13. Record all §3 metrics into the results table for this run.
14. `./reset-cluster.zsh` (or re-seed) to restore a clean inventory + connection state before the next run.

**Repetition:** run each configuration **≥ 3 times**. Report mean ± standard deviation. Discard any run with an infrastructure anomaly (node throttle, port-forward drop) and note it.

### 5.1 Steady-state definition
A run is in steady state when throughput and Postgres CPU are stationary (no trend over a 30 s sliding window) and inventory is not exhausted. Only the steady-state window feeds the reported numbers.

---

## 6. Experiment phases and run matrices

### Phase 0 — Smoke / calibration (not reported)
One short run per replica profile to validate seeding, cache warming, dashboards, the 3000-client load tool, and that `count=2` does not deplete inventory within the window. Tune seed count / window length here.

### 6.1 Determining run duration
Pick run duration in Phase 0 such that the steady-state window (≥120 s recommended) fits before inventory exhaustion. If 300k tickets deplete too fast at peak throughput, increase the seed or reduce concurrency-per-wave — but keep it identical across all reported runs.

---

### Phase 1 — RQ1: Workers per replica (prerequisite calibration)

**Goal:** for each replica profile, find the worker count that maximizes throughput. Keep DB_POOL_SIZE generous to avoid connection starvation affecting the worker sweep.
**Held constant:** Redis OFF (`/cart/reserve-batch`), `DB_POOL_SIZE=8` (provisional), 3000 clients, batch 2.
**Varied:** `WORKERS` ∈ {1, 2, 4, 6, 8} per replica.

| Profile (replicas) | Workers swept | Total client conns (workers×repl×3) range | Output |
|---|---|---|---|
| 1 | 1, 2, 4, 6, 8 | 3 → 24 | Optimal W₁ |
| 3 | 1, 2, 4, 6, 8 | 9 → 72 | Optimal W₃ |
| 5 | 1, 2, 4, 6, 8 | 15 → 120 | Optimal W₅ |

**Stop rule:** stop increasing workers once throughput plateaus or drops for two consecutive steps, OR cart CPU saturates (≈100% of profile budget).
**Deliverable:** throughput-vs-workers curve per profile; pick W₁/W₃/W₅ for use in later phases. Note where the bottleneck shifts from cart CPU to Postgres.

---

### Phase 2 — RQ2: Connections per worker / pool sizing (prerequisite calibration)

**Goal:** find `DB_POOL_SIZE` per worker that maximizes Postgres throughput without coordination overhead or idle-connection waste.
**Held constant:** Redis OFF, optimal workers from Phase 1 per profile, 3000 clients, batch 2.
**Varied:** `DB_POOL_SIZE` ∈ {1, 2, 3, 5, 8} per worker.

Track the connection cascade explicitly:

| Knob | Where | What to watch |
|---|---|---|
| `DB_POOL_SIZE` (per worker) | cart env | total client conns = repl × W × pool |
| `default_pool_size=200` | PgBouncer | server-conn cap, pool utilization, `cl_waiting` |
| `max_connections=250` | Postgres | active vs idle backends |

| Profile | Workers (from P1) | DB_POOL_SIZE swept | Total client conns range | Output |
|---|---|---|---|---|
| 1 | W₁ | 1,2,3,5,8 | — | Optimal pool₁ |
| 3 | W₃ | 1,2,3,5,8 | — | Optimal pool₃ |
| 5 | W₅ | 1,2,3,5,8 | — | Optimal pool₅ |

**Analysis:** plot throughput and p99 latency vs. total client connections. Identify the knee — the point past which more connections add idle backends and coordination overhead at Postgres without throughput gain. Cross-check whether PgBouncer (`cl_waiting` > 0, pool 100%) or Postgres (CPU bound, idle conns growing) is the limiter. This directly addresses the brainstorming hypothesis that connection pooling is the dominant bottleneck.
**Deliverable:** optimal pool size per profile + a clear statement of which hop saturates first.

> **Optional sub-study (strong thesis material):** at the best app-side config, sweep PgBouncer `default_pool_size` ∈ {50, 100, 150, 200, 250} to characterize the multiplexer's effect on a centralized DB independently of app-side pool size.

---

### Phase 3 — RQ3: Redis vs. no-Redis (the offload claim)

**Goal:** prove (or refute) that Redis offloads Postgres.
**Held constant:** the **best** config from Phases 1+2 (optimal workers + pool per profile), 3000 clients, batch 2. Use the **3-replica profile** as the headline comparison (representative cloud topology); optionally repeat for 1 and 5.
**Varied:** two arms only.

| Arm | Endpoint | `REDIS_ENABLED` | Cache |
|---|---|---|---|
| A — SQL only | `/cart/reserve-batch` | false | n/a |
| B — Redis | `/cart/reserve-batch-redis` | true | pre-warmed |

**Headline metric:** **Postgres CPU per successful reservation** (Arm B should be lower) and sustained throughput (Arm B should be higher at equal Postgres CPU).
**Secondary:** p99 latency, Postgres connection utilization, Redis CPU/ops/sec (to show the cost moved, not vanished).

> **Caveat to report honestly:** the Redis path still issues one single-row `UPDATE` to Postgres per ticket (via PgBouncer), and does one `LPOP` per ticket. It removes the `FOR UPDATE SKIP LOCKED` scan and contention, not the write. State this in the analysis so the offload claim is precise: Redis offloads *availability lookup and lock contention*, not the durable write. Brainstorming notes this advantage is largest when inventory changes dynamically.

---

### Phase 4 — RQ4: Horizontal scaling of the write service

**Goal:** determine whether a centralized strongly-consistent Postgres scales as the cart tier scales out.
**Held constant:** best per-profile config from Phases 1+2, 3000 clients, batch 2. Run both Redis OFF and Redis ON as two series.
**Varied:** replica profile ∈ {1, 3, 5} (total cart CPU budget held ~constant by design).

| Profile | Replicas | Series | Output |
|---|---|---|---|
| 1 | 1 | Redis off + on | baseline throughput |
| 3 | 3 | Redis off + on | scaling factor vs. 1 |
| 5 | 5 | Redis off + on | scaling factor vs. 1 and 3 |

**Analysis:** plot throughput vs. replica count for both series. Compute scaling efficiency (throughput(N) / throughput(1)). Expect sub-linear scaling converging on a Postgres-bound ceiling — evidence for/against "centralized DB can serve a modern cloud app." Identify the saturating resource at the ceiling (Postgres CPU, PgBouncer pool, or WAL/checkpoint). HPA stays **disabled** for constant replica counts.

---

## 7. Analysis and presentation plan

For each RQ, the thesis should present:

1. **A figure** — throughput (and where relevant p99 latency) vs. the swept variable, with error bars (±1 stddev over the ≥3 repeats).
2. **The bottleneck attribution** — which resource saturated (Postgres CPU / PgBouncer pool / cart CPU), evidenced by the §3 saturation metrics.
3. **The decision** — chosen optimum and why, carried forward into later phases.
4. **Correctness statement** — double-booking count (must be 0 on safe paths) under peak load, demonstrating strong consistency held while scaling.

**Cross-cutting narrative for the thesis:**
- RQ1+RQ2 → "how we tuned the app to stop wasting the database."
- RQ3 → "what caching buys a centralized DB, and what it does not."
- RQ4 → "how far a single strongly-consistent Postgres scales under a horizontally-scaled write tier on fixed hardware, and what stops it."

---

## 8. Threats to validity

- **Single-node co-location:** load generator is external (good), but Postgres, cart, PgBouncer, Redis, and observability share 8 cores. Observability overhead competes for CPU — keep its allocation fixed and account for it. Report the resource split.
- **Inventory exhaustion** confounds throughput with `503` rate — guard with §2.1 note and §6.1.
- **`synchronous_commit=off`** trades durability for throughput; results describe this configuration, not a fully-durable one. State explicitly.
- **PgBouncer `transaction` mode** means no session-level features; valid here since reservations are single transactions.
- **Warmup / steady-state windowing** must be identical across runs or comparisons are invalid.
- **Network variance** from the external load generator — run on a quiet network; report client-side timeout/error rates.
- **`statement_cache_size=0`** on the asyncpg pool (required for PgBouncer transaction mode) disables prepared-statement caching — a fixed cost present in all runs; note it.

---

## 9. Run log template

Record one row per run.

| Run ID | Phase | Profile (repl) | Workers | DB_POOL_SIZE | Total client conns | Redis | Endpoint | Repeat # | Throughput (rsv/s) | p50/p95/p99 (ms) | 200 / 503 / 409 | PG CPU % | PG conn % | PgB pool % / cl_waiting | Cart CPU % | PG CPU per rsv | Notes |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| | | | | | | | | | | | | | | | | | |
