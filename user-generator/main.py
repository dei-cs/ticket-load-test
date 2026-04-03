from fastapi import FastAPI
import uvicorn
from api.user_router import router

app = FastAPI(title="User Generator Tool")

app.include_router(router)


def main():
    uvicorn.run(app, host="0.0.0.0", port=8000)


if __name__ == "__main__":
    main()
