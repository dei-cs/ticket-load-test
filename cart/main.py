from contextlib import asynccontextmanager
import os

import httpx
import redis.asyncio as aioredis
import uvicorn
from fastapi import FastAPI

from api.cart_router import router
from services.cart_service import CartService

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")


@asynccontextmanager
async def lifespan(app: FastAPI):
    redis_client = aioredis.from_url(REDIS_URL, decode_responses=True)
    http_client = httpx.AsyncClient(
        timeout=10.0,
        limits=httpx.Limits(max_connections=100, max_keepalive_connections=20),
    )

    app.state.cart_service = CartService(redis_client, http_client)

    yield

    await redis_client.aclose()
    await http_client.aclose()


app = FastAPI(title="Cart Service", lifespan=lifespan)
app.include_router(router)


def main():
    uvicorn.run(app, host="0.0.0.0", port=8003)


if __name__ == "__main__":
    main()
