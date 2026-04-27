from contextlib import asynccontextmanager
import os

import asyncpg
import uvicorn
from fastapi import FastAPI

from api.cart_router import router
from services.cart_service import CartService

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://devuser:devpassword123@localhost:5432/ticketmanagerdb")


@asynccontextmanager
async def lifespan(app: FastAPI):
    pool = await asyncpg.create_pool(DATABASE_URL)
    app.state.cart_service = CartService(pool)

    yield

    await pool.close()


app = FastAPI(title="Cart Service", lifespan=lifespan)
app.include_router(router)


def main():
    uvicorn.run(app, host="0.0.0.0", port=8003)


if __name__ == "__main__":
    main()
