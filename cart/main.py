from contextlib import asynccontextmanager
import os

import asyncpg
import uvicorn
from fastapi import FastAPI
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

from api.cart_router import router
from services.cart_service import CartService
from utils.telemetry import setup_telemetry

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://devuser:devpassword123@localhost:5432/ticketmanagerdb")


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_telemetry("cart")
    pool = await asyncpg.create_pool(DATABASE_URL, min_size=2, max_size=10, statement_cache_size=0)
    app.state.cart_service = CartService(pool)

    yield

    await pool.close()


app = FastAPI(title="Cart Service", lifespan=lifespan)


@app.get("/healthz")
async def healthz():
    return {"status": "ok"}


app.include_router(router)
FastAPIInstrumentor.instrument_app(app)


def main():
    uvicorn.run(app, host="0.0.0.0", port=8003)


if __name__ == "__main__":
    main()
