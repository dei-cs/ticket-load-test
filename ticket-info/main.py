import redis
import os
import socket

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
STREAM = "ticket-availability"
GROUP = "ticket-info-service"
CONSUMER = socket.gethostname()

client = redis.Redis.from_url(REDIS_URL, decode_responses=True)


def setup_group():
    try:
        client.xgroup_create(STREAM, GROUP, id="0", mkstream=True)
    except redis.exceptions.ResponseError as e:
        if "BUSYGROUP" not in str(e):
            raise


def handle_message(entry_id: str, data: dict):
    ticket_id = data["ticket_id"]
    state = data["state"]
    owner = data["owner"]

    print(f"[{entry_id}] Ticket {ticket_id} → {state}, owner: {owner}")

    client.xack(STREAM, GROUP, entry_id)


def consume():
    setup_group()

    pending = client.xreadgroup(GROUP, CONSUMER, streams={STREAM: "0"}, count=100)
    for _, entries in (pending or []):
        for entry_id, data in entries:
            handle_message(entry_id, data)

    print(f"Listening on stream '{STREAM}' as '{CONSUMER}'...")
    while True:
        messages = client.xreadgroup(
            GROUP, CONSUMER,
            streams={STREAM: ">"},
            count=10,
            block=5000
        )
        for _, entries in (messages or []):
            for entry_id, data in entries:
                handle_message(entry_id, data)


def main():
    consume()


if __name__ == "__main__":
    main()
