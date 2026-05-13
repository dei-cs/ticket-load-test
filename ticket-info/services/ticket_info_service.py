import asyncpg


class TicketInfoService:
    def __init__(self, pool: asyncpg.Pool):
        self._pool = pool

    async def get_available_tickets(self) -> list[int]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch("SELECT id FROM tickets WHERE state='available'")
        return [row["id"] for row in rows]
