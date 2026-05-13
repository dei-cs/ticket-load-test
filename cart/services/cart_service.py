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
    def __init__(self, pool: asyncpg.Pool):
        self._pool = pool

    async def reserve_ticket(self, ticket_id: int, owner: str) -> dict:
        async with self._pool.acquire() as conn:
            await conn.execute(
                """UPDATE tickets SET state='reserved', owner=$1, reserved_at=$2
                   WHERE id=$3""",
                owner, utcnow(), ticket_id,
            )
            await conn.execute("SELECT pg_notify('ticket_state_change', $1)", str(ticket_id))

        return {"reserved": ticket_id, "owner": owner}


    async def reserve_ticket_batch_atomic_with_locking(self, count: int, owner: str) -> [int]:
        async with self._pool.acquire() as conn:
            # conn.transaction = atomic transaction (all operations finish or none do)
            async with conn.transaction():
                rows = await conn.fetch(
                    """
                    WITH grabbed AS (
                        SELECT id FROM tickets
                        WHERE state = 'available'
                        ORDER BY id
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

                reserved_tickets = [row["id"] for row in rows]

                for ticket_id in reserved_tickets:
                    await conn.execute("SELECT pg_notify('ticket_state_change', $1)", str(ticket_id))

            return reserved_tickets
    
    
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

                for ticket_id in reserved_tickets:
                    await conn.execute("SELECT pg_notify('ticket_state_change', $1)", str(ticket_id))

                if len(reserved_tickets) == 0:
                    raise NoTicketsAvailableError(requested=count, last_checked=utcnow())

                if len(reserved_tickets) < count:
                    raise TicketDoubleBookingError(requested=count, actually_reserved=len(reserved_tickets))

                return reserved_tickets