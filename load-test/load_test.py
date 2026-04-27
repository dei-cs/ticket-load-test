#!/usr/bin/env python3
"""
Ticket reservation load test.

Generates N users and M tickets, then fires N concurrent reservation requests
against the cart service. Measures throughput and correctness — specifically
whether the async Lua-lock + Redis stream flow produces any double bookings
or lost writes.

Usage:
    python load_test.py [--users N] [--tickets M] [--concurrency C]

Parameters:
    --users N         Total number of simulated users. Each user makes exactly
                      one reservation attempt against a randomly chosen ticket
                      from the available pool. Default: 100.

    --tickets M       Number of tickets to generate. Keep M < N to create
                      contention: multiple users will target the same tickets,
                      which is the condition that exposes race conditions.
                      Default: 50.

    --concurrency C   Maximum number of HTTP requests in-flight at once.
                      All N requests are launched together, but only C can
                      be actively waiting on the cart service simultaneously
                      (enforced via asyncio.Semaphore). Set C >= N to fire
                      everything at once with no throttling — maximum stress.
                      Lower C to simulate a slower, steadier stream of traffic.
                      Default: 100.

Correctness metrics:
    Double bookings   The cart returned 202 to two or more users for the same
                      ticket. Indicates the Redis Lua atomic lock failed.

    Lost writes       The cart returned 202 but the ticket is still "available"
                      in the DB after the stream settles. Indicates the
                      ticket-manager stream consumer dropped a message.
"""

import argparse
import asyncio
import random
import time
from collections import defaultdict

import httpx

USER_GEN = "http://localhost:8000"
TICKET_MGR = "http://localhost:8001"
TICKET_INFO = "http://localhost:8002"
CART = "http://localhost:8003"


async def setup(
    client: httpx.AsyncClient, n_users: int, n_tickets: int
) -> tuple[list[str], list[int]]:
    print("--- Phase 1: Setup ---")

    print("  Resetting state...")
    await client.delete(f"{USER_GEN}/users/delete")
    await client.delete(f"{TICKET_MGR}/tickets/delete")

    print(f"  Generating {n_users} users and {n_tickets} tickets...")
    await client.post(f"{USER_GEN}/users/generate", params={"count": n_users})
    await client.post(f"{TICKET_MGR}/tickets/generate", params={"count": n_tickets})

    resp = await client.get(f"{USER_GEN}/users/get", params={"count": n_users})
    user_ids = [u["user_id"] for u in resp.json()]

    # Wait for ticket-info Redis SET to sync before firing load
    print(f"  Waiting for ticket-info to sync {n_tickets} tickets...", end="", flush=True)
    available: list[int] = []
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        resp = await client.get(f"{TICKET_INFO}/tickets/available")
        available = resp.json()
        if len(available) >= n_tickets:
            break
        print(".", end="", flush=True)
        await asyncio.sleep(0.5)
    else:
        print(f" WARNING: only {len(available)}/{n_tickets} synced after 30s")

    print(f" {len(available)} ready")
    return user_ids, available


async def run_reservations(
    client: httpx.AsyncClient,
    user_ids: list[str],
    ticket_pool: list[int],
    concurrency: int,
) -> dict:
    n = len(user_ids)
    print(
        f"\n--- Phase 2: Load ({n} users, pool of {len(ticket_pool)} tickets,"
        f" concurrency={concurrency}) ---"
    )

    sem = asyncio.Semaphore(concurrency)
    # ticket_id -> list of user_ids that received 202 for it
    claimed: dict[int, list[str]] = defaultdict(list)
    counts = {"accepted": 0, "rejected": 0, "errors": 0, "completed": 0}

    async def reserve(user_id: str, ticket_id: int) -> None:
        async with sem:
            try:
                resp = await client.post(
                    f"{CART}/cart/reserve/{ticket_id}",
                    params={"owner": user_id},
                )
                if resp.status_code == 202:
                    counts["accepted"] += 1
                    claimed[ticket_id].append(user_id)
                elif resp.status_code == 409:
                    counts["rejected"] += 1
                else:
                    counts["errors"] += 1
            except Exception as exc:
                counts["errors"] += 1
            finally:
                counts["completed"] += 1
                done = counts["completed"]
                if done % max(1, n // 4) == 0 or done == n:
                    print(f"  {done}/{n} requests done", flush=True)

    tasks = [reserve(uid, random.choice(ticket_pool)) for uid in user_ids]

    start = time.monotonic()
    await asyncio.gather(*tasks)
    duration = time.monotonic() - start

    return {
        "accepted": counts["accepted"],
        "rejected": counts["rejected"],
        "errors": counts["errors"],
        "duration": duration,
        "throughput": n / duration,
        "claimed": dict(claimed),
    }


async def settle(
    client: httpx.AsyncClient, n_tickets: int, timeout: int = 30
) -> list[dict]:
    print("\n--- Phase 3: Waiting for stream settlement ---")
    prev_reserved = -1
    stable_streak = 0
    deadline = time.monotonic() + timeout

    while time.monotonic() < deadline:
        resp = await client.get(
            f"{TICKET_MGR}/tickets/get", params={"count": n_tickets}
        )
        tickets = resp.json()
        reserved_count = sum(1 for t in tickets if t["state"] == "reserved")

        if reserved_count == prev_reserved:
            stable_streak += 1
            if stable_streak >= 3:
                print(f"  Settled: {reserved_count} reserved in DB.")
                return tickets
        else:
            stable_streak = 0
            prev_reserved = reserved_count

        await asyncio.sleep(1)

    print(f"  WARNING: timed out after {timeout}s. Last count: {prev_reserved} reserved.")
    resp = await client.get(f"{TICKET_MGR}/tickets/get", params={"count": n_tickets})
    return resp.json()


def report(
    load_results: dict, tickets: list[dict], n_users: int, n_tickets: int
) -> None:
    print("\n--- Phase 4: Results ---")

    claimed: dict[int, list[str]] = load_results["claimed"]
    accepted: int = load_results["accepted"]
    rejected: int = load_results["rejected"]
    errors: int = load_results["errors"]
    duration: float = load_results["duration"]
    throughput: float = load_results["throughput"]

    db_reserved_ids = {t["id"] for t in tickets if t["state"] == "reserved"}
    db_available_count = sum(1 for t in tickets if t["state"] == "available")

    # A double booking is any ticket where cart returned 202 to 2+ different users.
    double_bookings = {tid: owners for tid, owners in claimed.items() if len(owners) > 1}

    # A lost write is a ticket the cart claimed (202) that the DB still shows as available.
    lost_writes = [tid for tid in claimed if tid not in db_reserved_ids]

    print()
    print(f"  Users:              {n_users}")
    print(f"  Tickets:            {n_tickets}")
    print(f"  Duration:           {duration:.2f}s")
    print(f"  Throughput:         {throughput:.1f} req/s")
    print()
    print(f"  Accepted (202):     {accepted}")
    print(f"  Rejected (409):     {rejected}")
    print(f"  Errors:             {errors}")
    print()
    print(f"  DB reserved:        {len(db_reserved_ids)}")
    print(f"  DB available:       {db_available_count}")
    print()
    print(f"  Double bookings:    {len(double_bookings)}", end="")
    print("  ✓" if len(double_bookings) == 0 else "  ✗ FAIL")
    print(f"  Lost writes:        {len(lost_writes)}", end="")
    print("  ✓" if len(lost_writes) == 0 else "  ✗ FAIL")

    if double_bookings:
        print("\n  Double booking details:")
        for tid, owners in double_bookings.items():
            print(f"    ticket {tid} claimed by: {owners}")

    if lost_writes:
        sample = lost_writes[:10]
        suffix = "..." if len(lost_writes) > 10 else ""
        print(f"\n  Lost write ticket IDs: {sample}{suffix}")

    passed = not double_bookings and not lost_writes
    print(f"\n  Correctness: {'PASS' if passed else 'FAIL'}")


async def main() -> None:
    parser = argparse.ArgumentParser(description="Ticket reservation load test")
    parser.add_argument("--users", type=int, default=100, help="Number of users (default: 100)")
    parser.add_argument("--tickets", type=int, default=50, help="Number of tickets (default: 50)")
    parser.add_argument(
        "--concurrency", type=int, default=100, help="Max concurrent requests (default: 100)"
    )
    args = parser.parse_args()

    async with httpx.AsyncClient(timeout=30.0) as client:
        user_ids, ticket_pool = await setup(client, args.users, args.tickets)
        load_results = await run_reservations(client, user_ids, ticket_pool, args.concurrency)
        tickets = await settle(client, args.tickets)
        report(load_results, tickets, args.users, args.tickets)


if __name__ == "__main__":
    asyncio.run(main())
