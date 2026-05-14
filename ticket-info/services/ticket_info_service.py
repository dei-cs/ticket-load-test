import json

import asyncpg
from redis.asyncio import Redis


class TicketInfoService:
    CACHE_KEY = "tickets:available"

    def __init__(self, pool: asyncpg.Pool, redis: Redis | None = None, ttl: int = 5):
        self._pool = pool
        self._redis = redis
        self._ttl = ttl

    async def get_available_tickets(self) -> list[int]:
        if self._redis:
            cached = await self._redis.get(self.CACHE_KEY)
            if cached:
                return json.loads(cached)

        async with self._pool.acquire() as conn:
            rows = await conn.fetch("SELECT id FROM tickets WHERE state='available'")
        ids = [row["id"] for row in rows]

        if self._redis:
            await self._redis.setex(self.CACHE_KEY, self._ttl, json.dumps(ids))

        return ids
