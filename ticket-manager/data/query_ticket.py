from fastapi import HTTPException
from data.db import Ticket, db
from utils.ticket_gen import generate_ticket
from peewee import chunked
from data.redis_client import redis_client
from datetime import datetime

def populate_tickets_table(count: int):
    db.connect(reuse_if_open=True)
    db.create_tables([Ticket], safe=True)
    add_tickets = [generate_ticket() for _ in range(count)]
    with db.atomic():
        for batch in chunked(add_tickets, 100):
            Ticket.insert_many(batch).execute()
            
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

def reserve_ticket_query(ticket_id: int, owner: str):
    db.connect(reuse_if_open=True)
    with db.atomic():
        updated = (
            Ticket.update(
                state="reserved",
                owner=owner,
                reserved_at=datetime.utcnow()
            )
            .where(Ticket.id == ticket_id, Ticket.state == "available")
            .execute()
        )
    
    db.close()
    if updated == 0:
        raise HTTPException(status_code=409, detail="Conflict: Ticket Unavailable")
    
    redis_client.xadd("ticket-availability", {
        "ticket_id": str(ticket_id),
        "state": "reserved",
        "owner": owner,
    })
    
    return {"reserved": ticket_id, "owner_user_id": owner}