import os

import redis as sync_redis
from data.db import Ticket, db
from utils.ticket_gen import generate_ticket
from peewee import chunked

REDIS_URL = os.getenv("REDIS_URL")
REDIS_KEY = "tickets:available_ids"

def populate_tickets_table(count: int):
    db.connect(reuse_if_open=True)
    db.create_tables([Ticket], safe=True)
    db.execute_sql("""
        CREATE INDEX IF NOT EXISTS idx_tickets_available
        ON tickets (id)
        WHERE state = 'available'
    """)

    add_tickets = [generate_ticket() for _ in range(count)]
    with db.atomic():
        for batch in chunked(add_tickets, 100):
            Ticket.insert_many(batch).execute()

    if REDIS_URL:
        ids = [row[0] for row in Ticket.select(Ticket.id).where(Ticket.state == "available").tuples()]
        r = sync_redis.Redis.from_url(REDIS_URL)
        r.delete(REDIS_KEY)
        for i in range(0, len(ids), 1000):
            r.rpush(REDIS_KEY, *ids[i:i+1000])
        r.close()

    db.close()

def get_tickets(count: int, starting_index: int):
    db.connect(reuse_if_open=True)
    tickets = list(
        Ticket.select()
              .where(Ticket.id > starting_index)
              .order_by(Ticket.id)
              .limit(count)
              .dicts()
    )
    db.close()
    return tickets

def delete_all_tickets_query():
    db.connect(reuse_if_open=True)
    delete_count = Ticket.delete().execute()
    db.close()
    return delete_count

