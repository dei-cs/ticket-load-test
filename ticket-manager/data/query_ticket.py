from data.db import Ticket, db
from utils.ticket_gen import generate_ticket
from peewee import chunked, fn
from datetime import datetime
import time
from utils.telemetry import tracer, reservation_attempts, reservation_results, reservation_duration


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
    start = time.perf_counter()
    reservation_attempts.add(1)

    with tracer.start_as_current_span("reserve_ticket_query") as span:
        span.set_attribute("ticket.id", ticket_id)
        span.set_attribute("ticket.owner", owner)
        db.connect(reuse_if_open=True)
        with db.atomic():
            Ticket.update(
                state="reserved",
                owner=owner,
                reserved_at=datetime.utcnow()
            ).where(Ticket.id == ticket_id).execute()
        db.close()

        duration = time.perf_counter() - start

        span.set_attribute("reservation.result", "success")
        reservation_results.add(1, {"result": "success"})
        reservation_duration.record(duration, {"result": "success"})
        return {"reserved": ticket_id, "owner_user_id": owner}
