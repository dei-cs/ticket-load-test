import asyncpg


class TicketInfoService:
    def __init__(self, pool: asyncpg.Pool):
        self._pool = pool
        self._available: set[int] = set()

    async def initialize_cache(self):
        async with self._pool.acquire() as conn:
            rows = await conn.fetch("SELECT id FROM tickets WHERE state='available'")
        self._available = {row["id"] for row in rows}

    def remove_ticket(self, ticket_id: int):
        self._available.discard(ticket_id)

    def get_cached_tickets(self) -> list[int]:
        return sorted(self._available)

    async def get_available_tickets(self) -> list[int]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch("SELECT id FROM tickets WHERE state='available'")
        return [row["id"] for row in rows]
