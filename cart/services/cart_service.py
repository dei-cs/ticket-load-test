from datetime import datetime
from time import perf_counter

import asyncpg

from utils.telemetry import (
    reservation_attempts,
    reservation_duration,
    reservation_results,
)


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


    async def reserve_ticket_batch_atomic_with_locking(self, count: int, owner: str) -> [int]:
        attributes = {"strategy": "locked"}
        reservation_attempts.add(1, attributes)
        started_at = perf_counter()
        result = "error"

        try:
            async with self._pool.acquire() as conn:
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
                        result = "no_tickets_available"
                        raise NoTicketsAvailableError(requested=count, last_checked=utcnow())

                    reserved_tickets = [row["id"] for row in rows]

                result = "success"
                return reserved_tickets
        finally:
            result_attributes = attributes | {"result": result}
            reservation_results.add(1, result_attributes)
            reservation_duration.record(perf_counter() - started_at, result_attributes)


    async def reserve_ticket_batch_no_locking(self, count: int, owner: str) -> [int]:
        attributes = {"strategy": "unsafe"}
        reservation_attempts.add(1, attributes)
        started_at = perf_counter()
        result = "error"

        try:
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
                        result = "no_tickets_available"
                        raise NoTicketsAvailableError(requested=count, last_checked=utcnow())

                    if len(reserved_tickets) < count:
                        result = "double_booking_detected"
                        raise TicketDoubleBookingError(requested=count, actually_reserved=len(reserved_tickets))

                    result = "success"
                    return reserved_tickets
        finally:
            result_attributes = attributes | {"result": result}
            reservation_results.add(1, result_attributes)
            reservation_duration.record(perf_counter() - started_at, result_attributes)
