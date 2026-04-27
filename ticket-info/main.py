import os
from contextlib import asynccontextmanager

import asyncpg
import uvicorn
from fastapi import FastAPI

from api.ticket_info_router import router
from services.ticket_info_service import TicketInfoService

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://devuser:devpassword123@localhost:5432/ticketmanagerdb")


@asynccontextmanager
async def lifespan(app: FastAPI):
    pool = await asyncpg.create_pool(DATABASE_URL)
    app.state.ticket_info_service = TicketInfoService(pool)

    yield

    await pool.close()


app = FastAPI(title="Ticket Info Service", lifespan=lifespan)
app.include_router(router)


def main():
    uvicorn.run(app, host="0.0.0.0", port=8002)


if __name__ == "__main__":
    main()
