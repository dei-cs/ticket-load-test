import time
from datetime import datetime, timezone

import asyncpg

from utils.telemetry import tracer, reservation_attempts, reservation_results, reservation_duration


class CartService:
    def __init__(self, pool: asyncpg.Pool):
        self._pool = pool

    async def reserve_ticket(self, ticket_id: int, owner: str) -> dict:
        start = time.perf_counter()
        reservation_attempts.add(1)

        with tracer.start_as_current_span("reserve_ticket") as span:
            span.set_attribute("ticket.id", ticket_id)
            span.set_attribute("ticket.owner", owner)

            async with self._pool.acquire() as conn:
                await conn.execute(
                    """UPDATE tickets SET state='reserved', owner=$1, reserved_at=$2
                       WHERE id=$3""",
                    owner, datetime.now(timezone.utc), ticket_id,
                )

            duration = time.perf_counter() - start
            reservation_results.add(1, {"result": "success"})
            reservation_duration.record(duration, {"result": "success"})

        return {"reserved": ticket_id, "owner": owner}
