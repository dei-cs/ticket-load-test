from contextlib import asynccontextmanager
import os

import asyncpg
import uvicorn
from fastapi import FastAPI

from api.cart_router import router
from services.cart_service import CartService
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from utils.telemetry import setup_telemetry

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://devuser:devpassword123@localhost:5432/ticketmanagerdb")
DB_POOL_SIZE = int(os.getenv("DB_POOL_SIZE", "50"))
WORKERS = int(os.getenv("WORKERS", "4"))
REDIS_ENABLED = os.getenv("REDIS_ENABLED", "false").lower() == "true"
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379")


@asynccontextmanager
async def lifespan(app: FastAPI):
    pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=DB_POOL_SIZE, statement_cache_size=0)

    redis = None
    if REDIS_ENABLED:
        from redis.asyncio import Redis, ConnectionPool
        redis = Redis(connection_pool=ConnectionPool.from_url(REDIS_URL))

    app.state.cart_service = CartService(pool, redis=redis)

    yield

    await pool.close()
    if redis:
        await redis.aclose()

setup_telemetry("cart")
app = FastAPI(title="Cart Service", lifespan=lifespan)
FastAPIInstrumentor.instrument_app(app)

@app.get("/healthz")
async def healthz():
    return {"status": "ok"}


app.include_router(router)


def main():
    uvicorn.run("main:app", host="0.0.0.0", port=8003, workers=WORKERS)


if __name__ == "__main__":
    main()
