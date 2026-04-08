import os
from contextlib import asynccontextmanager

import httpx
import redis.asyncio as aioredis
import uvicorn
from fastapi import FastAPI

from api.ticket_info_router import router
from services.ticket_info_service import TicketInfoService

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
TICKET_MANAGER_URL = os.getenv("TICKET_MANAGER_URL", "http://localhost:8001")


@asynccontextmanager
async def lifespan(app: FastAPI):
    redis_client = aioredis.from_url(REDIS_URL, decode_responses=True)
    http_client = httpx.AsyncClient(
        timeout=10.0,
        limits=httpx.Limits(max_connections=100, max_keepalive_connections=20),
    )

    service = TicketInfoService(redis_client, http_client, TICKET_MANAGER_URL)
    await service.initialize()
    service.start_consumer()
    app.state.ticket_info_service = service

    yield

    await service.stop_consumer()
    await redis_client.aclose()
    await http_client.aclose()


app = FastAPI(title="Ticket Info Service", lifespan=lifespan)
app.include_router(router)


def main():
    uvicorn.run(app, host="0.0.0.0", port=8002)


if __name__ == "__main__":
    main()
