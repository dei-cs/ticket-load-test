import os
from contextlib import asynccontextmanager

import asyncpg
import uvicorn
from fastapi import FastAPI, Request
from redis.asyncio import ConnectionPool, Redis

from api.ticket_info_router import router
from services.ticket_info_service import TicketInfoService

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://devuser:devpassword123@localhost:5432/ticketmanagerdb")
REDIS_ENABLED = os.getenv("REDIS_ENABLED", "false").lower() == "true"
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
REDIS_TTL = int(os.getenv("REDIS_TTL_SECONDS", "5"))


@asynccontextmanager
async def lifespan(app: FastAPI):
    pool = await asyncpg.create_pool(DATABASE_URL, min_size=2, max_size=10, statement_cache_size=0)

    redis = None
    if REDIS_ENABLED:
        redis_pool = ConnectionPool.from_url(REDIS_URL)
        redis = Redis(connection_pool=redis_pool)

    app.state.ticket_info_service = TicketInfoService(pool, redis=redis, ttl=REDIS_TTL)

    yield

    await pool.close()
    if redis:
        await redis.aclose()


app = FastAPI(title="Ticket Info Service", lifespan=lifespan)


@app.get("/healthz")
async def healthz():
    return {"status": "ok"}


app.include_router(router)


if REDIS_ENABLED:
    @app.post("/cache/warm")
    async def warm_cache(request: Request):
        service: TicketInfoService = request.app.state.ticket_info_service
        tickets = await service.get_available_tickets()
        return {"cached_tickets": len(tickets)}


def main():
    uvicorn.run(app, host="0.0.0.0", port=8002)


if __name__ == "__main__":
    main()
