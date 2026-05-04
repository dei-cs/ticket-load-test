import asyncpg

from services.connection_manager import ConnectionManager
from services.ticket_info_service import TicketInfoService


class TicketListener:
    def __init__(self, db_url: str, service: TicketInfoService, manager: ConnectionManager):
        self._db_url = db_url
        self._service = service
        self._manager = manager
        self._conn: asyncpg.Connection | None = None

    async def start(self):
        self._conn = await asyncpg.connect(self._db_url)
        await self._conn.add_listener("ticket_state_change", self._on_notify)

    async def stop(self):
        if self._conn:
            await self._conn.remove_listener("ticket_state_change", self._on_notify)
            await self._conn.close()

    async def _on_notify(self, conn, pid, channel, payload):
        self._service.remove_ticket(int(payload))
        await self._manager.broadcast({"ticket_ids": self._service.get_cached_tickets()})
