# ticket-load-test

A research prototype simulating a concurrent concert ticketing system. This serves as a **baseline** for studying correctness and performance trade-offs in distributed reservation workflows under high load.

The system is built as a set of microservices using an asynchronous, event-driven architecture backed by Redis Streams and PostgreSQL.

---

## Architecture

```
Client (load test)
    │
    ▼
┌─────────┐   Lua atomic lock    ┌───────┐
│  Cart   │ ──────────────────>  │ Redis │
│ :8003   │   XADD reservation   │       │
└─────────┘                      └───────┘
                                     │
                              XREADGROUP │
                                     ▼
                            ┌──────────────────┐   UPDATE tickets   ┌──────────┐
                            │  Ticket Manager  │ ─────────────────> │Postgres  │
                            │     :8001        │  XADD availability │          │
                            └──────────────────┘                    └──────────┘
                                     │
                              XREADGROUP │
                                     ▼
                            ┌──────────────────┐
                            │   Ticket Info    │  Redis SET cache
                            │     :8002        │  of available IDs
                            └──────────────────┘
```

| Service | Port | Role |
|---|---|---|
| **cart** | 8003 | Fast reservation broker — claims tickets atomically via a Redis Lua script, then publishes to a Redis Stream |
| **ticket-manager** | 8001 | Persistence layer — consumes the reservations stream and writes to PostgreSQL; emits availability events |
| **ticket-info** | 8002 | Read cache — maintains a Redis SET of available ticket IDs, synced from PostgreSQL on startup and kept live via the availability stream |
| **user-generator** | 8000 | Test data helper — generates fake users stored in a local SQLite database |
| **postgres** | 5432 | Source of truth for ticket and reservation state |
| **redis** | 6379 | Async event streaming, distributed locks, and the availability cache |

### Key design decisions

- **Atomic Lua lock on cart**: A single Lua script performs `SISMEMBER` + `SREM` in one atomic operation, ensuring at most one client claims a given ticket from the Redis SET. This is the first line of defence against double bookings.
- **Redis Streams with consumer groups**: Two streams (`ticket-reservations`, `ticket-availability`) decouple the fast reservation path from the slower database write, while consumer groups provide durability and replay on restart.
- **Async persistence**: The cart returns `202 Accepted` immediately after claiming the Redis lock; the ticket-manager consumer persists the reservation to PostgreSQL asynchronously.
- **Dual-write cache**: Ticket Info seeds its Redis SET from PostgreSQL on startup and then tails the availability stream, keeping reads off the database entirely.

---

## Running the stack

```bash
docker compose up -d
```

All services wait for their dependencies to be healthy before starting (Redis, then Postgres, then the application services in order).
