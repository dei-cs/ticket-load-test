import os

import httpx
import redis.asyncio as aioredis

TICKET_MANAGER_URL = os.getenv("TICKET_MANAGER_URL", "http://localhost:8001")
AVAILABLE_KEY = "ticket:available"

CLAIM_SCRIPT = """
local in_set = redis.call('SISMEMBER', KEYS[1], ARGV[1])
if in_set == 0 then return 0 end
redis.call('SREM', KEYS[1], ARGV[1])
return 1
"""


class TicketUnavailableError(Exception):
    pass


class UpstreamError(Exception):
    pass


class CartService:
    def __init__(self, redis_client: aioredis.Redis, http_client: httpx.AsyncClient):
        self._redis = redis_client
        self._http = http_client
        self._claim_script = None

    async def reserve_ticket(self, ticket_id: int, owner: str) -> dict:
        if self._claim_script is None:
            self._claim_script = self._redis.register_script(CLAIM_SCRIPT)

        claimed = await self._claim_script(keys=[AVAILABLE_KEY], args=[str(ticket_id)])
        if not claimed:
            raise TicketUnavailableError

        resp = await self._http.post(
            f"{TICKET_MANAGER_URL}/tickets/reserve/{ticket_id}",
            params={"owner": owner},
        )

        if resp.status_code == 409:
            await self._redis.sadd(AVAILABLE_KEY, str(ticket_id))
            raise TicketUnavailableError

        if resp.status_code != 200:
            await self._redis.sadd(AVAILABLE_KEY, str(ticket_id))
            raise UpstreamError

        return resp.json()
