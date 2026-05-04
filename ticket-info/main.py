import os
from contextlib import asynccontextmanager

import asyncpg
import uvicorn
from fastapi import FastAPI

from api.ticket_info_router import router
from services.connection_manager import ConnectionManager
from services.ticket_info_service import TicketInfoService
from services.ticket_listener import TicketListener

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://devuser:devpassword123@localhost:5432/ticketmanagerdb")


@asynccontextmanager
async def lifespan(app: FastAPI):
    pool = await asyncpg.create_pool(DATABASE_URL, min_size=2, max_size=10, statement_cache_size=0)
    service = TicketInfoService(pool)
    manager = ConnectionManager()
    listener = TicketListener(DATABASE_URL, service, manager)

    app.state.ticket_info_service = service
    app.state.connection_manager = manager

    await service.initialize_cache()
    await listener.start()

    yield

    await listener.stop()
    await pool.close()


app = FastAPI(title="Ticket Info Service", lifespan=lifespan)


@app.get("/healthz")
async def healthz():
    return {"status": "ok"}


app.include_router(router)


def main():
    uvicorn.run(app, host="0.0.0.0", port=8002)


if __name__ == "__main__":
    main()
