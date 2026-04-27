from datetime import datetime, timezone

import asyncpg


class CartService:
    def __init__(self, pool: asyncpg.Pool):
        self._pool = pool

    async def reserve_ticket(self, ticket_id: int, owner: str) -> dict:
        async with self._pool.acquire() as conn:
            await conn.execute(
                """UPDATE tickets SET state='reserved', owner=$1, reserved_at=$2
                   WHERE id=$3""",
                owner, datetime.now(timezone.utc), ticket_id,
            )
        return {"reserved": ticket_id, "owner": owner}
