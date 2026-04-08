import asyncio
import os
import socket
from contextlib import asynccontextmanager

import httpx
import redis.asyncio as aioredis
from fastapi import FastAPI, HTTPException
import uvicorn

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
TICKET_MANAGER_URL = os.getenv("TICKET_MANAGER_URL", "http://localhost:8001")
STREAM = "ticket-availability"
GROUP = "ticket-info-service"
CONSUMER = socket.gethostname()
AVAILABLE_KEY = "ticket:available"

# Lua script: atomically check membership and remove in one operation
CLAIM_SCRIPT = """
local in_set = redis.call('SISMEMBER', KEYS[1], ARGV[1])
if in_set == 0 then return 0 end
redis.call('SREM', KEYS[1], ARGV[1])
return 1
"""

redis_client: aioredis.Redis = None
http_client: httpx.AsyncClient = None


async def load_available_tickets():
    """Seed the Redis SET from ticket-manager on startup."""
    page_size = 1000
    starting_index = 0
    ticket_ids = []

    while True:
        resp = await http_client.get(
            f"{TICKET_MANAGER_URL}/tickets/get",
            params={"count": page_size, "starting_index": starting_index},
        )
        resp.raise_for_status()
        batch = resp.json()
        if not batch:
            break
        available = [str(t["id"]) for t in batch if t["state"] == "available"]
        ticket_ids.extend(available)
        if len(batch) < page_size:
            break
        starting_index = batch[-1]["id"]

    if ticket_ids:
        await redis_client.sadd(AVAILABLE_KEY, *ticket_ids)

    print(f"Seeded {len(ticket_ids)} available tickets into Redis SET")


async def setup_consumer_group():
    try:
        await redis_client.xgroup_create(STREAM, GROUP, id="0", mkstream=True)
    except Exception as e:
        if "BUSYGROUP" not in str(e):
            raise


async def stream_consumer():
    """Background task: consume reservation events and keep the SET in sync."""
    # Drain any pending (unacked) messages first
    pending = await redis_client.xreadgroup(
        GROUP, CONSUMER, streams={STREAM: "0"}, count=100
    )
    for _, entries in (pending or []):
        for entry_id, data in entries:
            if data.get("state") == "available":
                await redis_client.sadd(AVAILABLE_KEY, data["ticket_id"])
            else:
                await redis_client.srem(AVAILABLE_KEY, data["ticket_id"])
            await redis_client.xack(STREAM, GROUP, entry_id)

    print(f"Stream consumer listening on '{STREAM}' as '{CONSUMER}'...")
    while True:
        try:
            messages = await redis_client.xreadgroup(
                GROUP, CONSUMER,
                streams={STREAM: ">"},
                count=50,
                block=2000,
            )
            for _, entries in (messages or []):
                for entry_id, data in entries:
                    if data.get("state") == "available":
                        await redis_client.sadd(AVAILABLE_KEY, data["ticket_id"])
                    else:
                        await redis_client.srem(AVAILABLE_KEY, data["ticket_id"])
                    await redis_client.xack(STREAM, GROUP, entry_id)
        except asyncio.CancelledError:
            break
        except Exception as e:
            print(f"Stream consumer error: {e}")
            await asyncio.sleep(1)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global redis_client, http_client

    redis_client = aioredis.from_url(REDIS_URL, decode_responses=True)
    http_client = httpx.AsyncClient(
        timeout=10.0,
        limits=httpx.Limits(max_connections=100, max_keepalive_connections=20),
    )

    await setup_consumer_group()
    await load_available_tickets()

    consumer_task = asyncio.create_task(stream_consumer())

    yield

    consumer_task.cancel()
    await asyncio.gather(consumer_task, return_exceptions=True)
    await redis_client.aclose()
    await http_client.aclose()


app = FastAPI(title="Ticket Info Service", lifespan=lifespan)

claim_script = None


@app.get("/tickets/available")
async def get_available_tickets():
    members = await redis_client.smembers(AVAILABLE_KEY)
    return [int(m) for m in members]


@app.post("/reserve/{ticket_id}")
async def reserve_ticket(ticket_id: int, owner: str):
    global claim_script
    if claim_script is None:
        claim_script = redis_client.register_script(CLAIM_SCRIPT)

    claimed = await claim_script(keys=[AVAILABLE_KEY], args=[str(ticket_id)])
    if not claimed:
        raise HTTPException(status_code=409, detail="Conflict: Ticket Unavailable")

    resp = await http_client.post(
        f"{TICKET_MANAGER_URL}/tickets/reserve/{ticket_id}",
        params={"owner": owner},
    )

    if resp.status_code == 409:
        # DB says it's gone — roll back the Redis claim
        await redis_client.sadd(AVAILABLE_KEY, str(ticket_id))
        raise HTTPException(status_code=409, detail="Conflict: Ticket Unavailable")

    if resp.status_code != 200:
        await redis_client.sadd(AVAILABLE_KEY, str(ticket_id))
        raise HTTPException(status_code=502, detail="Upstream error from ticket-manager")

    return resp.json()


def main():
    uvicorn.run(app, host="0.0.0.0", port=8002)


if __name__ == "__main__":
    main()
