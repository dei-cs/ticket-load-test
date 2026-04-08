import redis.asyncio as aioredis

AVAILABLE_KEY = "ticket:available"
RESERVATIONS_STREAM = "ticket-reservations"

CLAIM_SCRIPT = """
local in_set = redis.call('SISMEMBER', KEYS[1], ARGV[1])
if in_set == 0 then return 0 end
redis.call('SREM', KEYS[1], ARGV[1])
return 1
"""


class TicketUnavailableError(Exception):
    pass


class CartService:
    def __init__(self, redis_client: aioredis.Redis):
        self._redis = redis_client
        self._claim_script = None

    async def reserve_ticket(self, ticket_id: int, owner: str) -> dict:
        if self._claim_script is None:
            self._claim_script = self._redis.register_script(CLAIM_SCRIPT)

        claimed = await self._claim_script(keys=[AVAILABLE_KEY], args=[str(ticket_id)])
        if not claimed:
            raise TicketUnavailableError

        await self._redis.xadd(RESERVATIONS_STREAM, {"ticket_id": str(ticket_id), "owner": owner})
        return {"reserved": ticket_id, "owner": owner}
