import asyncio
import socket

import redis.asyncio as aioredis

from data.query_ticket import reserve_ticket_query
from data.redis_client import async_redis_client

STREAM = "ticket-reservations"
GROUP = "ticket-manager-service"
CONSUMER = socket.gethostname()


class ReservationConsumer:
    def __init__(self):
        self._redis: aioredis.Redis = async_redis_client
        self._task: asyncio.Task | None = None

    async def start(self):
        await self._setup_consumer_group()
        self._task = asyncio.create_task(self._consume())

    async def stop(self):
        if self._task:
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)

    async def _setup_consumer_group(self):
        try:
            await self._redis.xgroup_create(STREAM, GROUP, id="0", mkstream=True)
        except Exception as e:
            if "BUSYGROUP" not in str(e):
                raise

    async def _consume(self):
        # Replay any pending (unacknowledged) messages first
        pending = await self._redis.xreadgroup(GROUP, CONSUMER, streams={STREAM: "0"}, count=100)
        for _, entries in (pending or []):
            for entry_id, data in entries:
                await self._process(entry_id, data)

        print(f"Reservation consumer listening on '{STREAM}' as '{CONSUMER}'...")
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
                        await self._process(entry_id, data)
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"Reservation consumer error: {e}")
                await asyncio.sleep(1)

    async def _process(self, entry_id: str, data: dict):
        ticket_id = int(data["ticket_id"])
        owner = data["owner"]
        try:
            await asyncio.to_thread(reserve_ticket_query, ticket_id, owner)
        except Exception as e:
            print(f"Failed to persist reservation ticket_id={ticket_id}: {e}")
        await self._redis.xack(STREAM, GROUP, entry_id)
