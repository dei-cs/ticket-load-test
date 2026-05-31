import json
from datetime import datetime

import asyncpg


def utcnow():
    return datetime.utcnow()


class NoTicketsAvailableError(Exception):
    def __init__(self, requested: int, last_checked: datetime):
        self.requested = requested
        self.last_checked = last_checked
        super().__init__(f"No tickets available, requested {requested}")


class TicketDoubleBookingError(Exception):
    def __init__(self, requested: int, actually_reserved: int):
        self.requested = requested
        self.actually_reserved = actually_reserved
        super().__init__(f"Double booking detected: requested {requested}, got {actually_reserved}")


class CartService:
    REDIS_KEY = "tickets:available_ids"
    _MAX_RETRIES = 3

    def __init__(self, pool: asyncpg.Pool, redis=None):
        self._pool = pool
        self._redis = redis


    async def reserve_ticket_batch_atomic_with_locking(self, count: int, owner: str) -> [int]:
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                rows = await conn.fetch(
                    """
                    WITH grabbed AS (
                        SELECT id FROM tickets
                        WHERE state = 'available'
                        LIMIT $1
                        FOR UPDATE SKIP LOCKED
                    )
                    UPDATE tickets
                    SET state = 'reserved', owner = $2, reserved_at = $3
                    WHERE id IN (SELECT id FROM grabbed)
                    RETURNING id
                    """,
                    count, owner, utcnow(),
                )

                if not rows:
                    raise NoTicketsAvailableError(requested=count, last_checked=utcnow())

                return [row["id"] for row in rows]


    async def _repopulate_from_cache(self) -> int:
        cached = await self._redis.get("tickets:available")
        if not cached:
            return 0
        ids = json.loads(cached)
        if ids:
            await self._redis.delete(self.REDIS_KEY)
            for i in range(0, len(ids), 1000):
                await self._redis.rpush(self.REDIS_KEY, *ids[i:i+1000])
        return len(ids)

    async def reserve_ticket_batch_redis(self, count: int, owner: str) -> list[int]:
        reserved = []
        retries = 0

        while len(reserved) < count:
            raw = await self._redis.lpop(self.REDIS_KEY)
            if raw is None:
                refilled = await self._repopulate_from_cache()
                if refilled == 0:
                    raise NoTicketsAvailableError(requested=count, last_checked=utcnow())
                continue

            async with self._pool.acquire() as conn:
                rows = await conn.fetch(
                    """
                    UPDATE tickets
                    SET state = 'reserved', owner = $2, reserved_at = $3
                    WHERE id = $1 AND state = 'available'
                    RETURNING id
                    """,
                    int(raw), owner, utcnow(),
                )
                if rows:
                    reserved.extend(row["id"] for row in rows)
                else:
                    retries += 1
                    if retries >= self._MAX_RETRIES:
                        raise NoTicketsAvailableError(requested=count, last_checked=utcnow())

        return reserved

    async def reserve_ticket_batch_no_locking(self, count: int, owner: str) -> [int]:
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                rows = await conn.fetch(
                    """
                    WITH grabbed AS (
                        SELECT id FROM tickets
                        WHERE state = 'available'
                        ORDER BY id
                        LIMIT $1
                    )
                    UPDATE tickets
                    SET state = 'reserved', owner = $2, reserved_at = $3
                    WHERE id IN (SELECT id FROM grabbed)
                    AND state = 'available'
                    RETURNING id
                    """,
                    count, owner, utcnow(),
                )

                reserved_tickets = [row["id"] for row in rows]

                if len(reserved_tickets) == 0:
                    raise NoTicketsAvailableError(requested=count, last_checked=utcnow())

                if len(reserved_tickets) < count:
                    raise TicketDoubleBookingError(requested=count, actually_reserved=len(reserved_tickets))

                return reserved_tickets
