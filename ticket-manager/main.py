from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI
import uvicorn
from api.ticket_router import router

app = FastAPI(title="Ticket Manager Tool")

app.include_router(router)


def main():
    uvicorn.run(app, host="0.0.0.0", port=8001)


if __name__ == "__main__":
    main()
