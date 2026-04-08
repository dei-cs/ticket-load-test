import asyncio
import socket

import httpx
import redis.asyncio as aioredis

STREAM = "ticket-availability"
GROUP = "ticket-info-service"
CONSUMER = socket.gethostname()
AVAILABLE_KEY = "ticket:available"


class TicketInfoError(Exception):
    pass


class TicketInfoService:
    def __init__(self, redis_client: aioredis.Redis, http_client: httpx.AsyncClient, ticket_manager_url: str):
        self._redis = redis_client
        self._http = http_client
        self._ticket_manager_url = ticket_manager_url
        self._consumer_task: asyncio.Task | None = None

    async def initialize(self):
        await self._setup_consumer_group()
        await self._load_available_tickets()

    def start_consumer(self):
        self._consumer_task = asyncio.create_task(self._stream_consumer())

    async def stop_consumer(self):
        if self._consumer_task:
            self._consumer_task.cancel()
            await asyncio.gather(self._consumer_task, return_exceptions=True)

    async def get_available_tickets(self) -> list[int]:
        members = await self._redis.smembers(AVAILABLE_KEY)
        return [int(m) for m in members]

    async def _setup_consumer_group(self):
        try:
            await self._redis.xgroup_create(STREAM, GROUP, id="0", mkstream=True)
        except Exception as e:
            if "BUSYGROUP" not in str(e):
                raise

    async def _load_available_tickets(self):
        """Seed the Redis SET from ticket-manager on startup."""
        page_size = 1000
        starting_index = 0
        ticket_ids = []

        while True:
            try:
                resp = await self._http.get(
                    f"{self._ticket_manager_url}/tickets/get",
                    params={"count": page_size, "starting_index": starting_index},
                )
                resp.raise_for_status()
            except httpx.HTTPError as e:
                raise TicketInfoError(f"Failed to load tickets from ticket-manager: {e}") from e

            batch = resp.json()
            if not batch:
                break
            available = [str(t["id"]) for t in batch if t["state"] == "available"]
            ticket_ids.extend(available)
            if len(batch) < page_size:
                break
            starting_index = batch[-1]["id"]

        if ticket_ids:
            await self._redis.sadd(AVAILABLE_KEY, *ticket_ids)

        print(f"Seeded {len(ticket_ids)} available tickets into Redis SET")

    async def _stream_consumer(self):
        """Background task: consume reservation events and keep the SET in sync."""
        pending = await self._redis.xreadgroup(
            GROUP, CONSUMER, streams={STREAM: "0"}, count=100
        )
        for _, entries in (pending or []):
            for entry_id, data in entries:
                if data.get("state") == "available":
                    await self._redis.sadd(AVAILABLE_KEY, data["ticket_id"])
                else:
                    await self._redis.srem(AVAILABLE_KEY, data["ticket_id"])
                await self._redis.xack(STREAM, GROUP, entry_id)

        print(f"Stream consumer listening on '{STREAM}' as '{CONSUMER}'...")
        while True:
            try:
                messages = await self._redis.xreadgroup(
                    GROUP, CONSUMER,
                    streams={STREAM: ">"},
                    count=50,
                    block=2000,
                )
                for _, entries in (messages or []):
                    for entry_id, data in entries:
                        if data.get("state") == "available":
                            await self._redis.sadd(AVAILABLE_KEY, data["ticket_id"])
                        else:
                            await self._redis.srem(AVAILABLE_KEY, data["ticket_id"])
                        await self._redis.xack(STREAM, GROUP, entry_id)
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"Stream consumer error: {e}")
                await asyncio.sleep(1)
