from dotenv import load_dotenv
load_dotenv()

from contextlib import asynccontextmanager
from fastapi import FastAPI
import uvicorn
from api.ticket_router import router
from data.db import db, Ticket
from services.reservation_consumer import ReservationConsumer
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from utils.telemetry import setup_telemetry

# Create DB on startup if it doesn't exist
@asynccontextmanager
async def lifespan(app: FastAPI):
    db.connect(reuse_if_open=True)
    db.create_tables([Ticket], safe=True)
    db.close()

    consumer = ReservationConsumer()
    await consumer.start()

    yield

    await consumer.stop()


app = FastAPI(title="Ticket Manager Tool", lifespan=lifespan)

app.include_router(router)
setup_telemetry("ticket-manager")
FastAPIInstrumentor.instrument_app(app)

def main():
    uvicorn.run(app, host="0.0.0.0", port=8001)


if __name__ == "__main__":
    main()
