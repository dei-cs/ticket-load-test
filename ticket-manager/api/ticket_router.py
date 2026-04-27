from fastapi import APIRouter
from models.ticket import Ticket
from data.query_ticket import populate_tickets_table, get_tickets, delete_all_tickets_query

router = APIRouter(prefix="/tickets", tags=["tickets"])

@router.post("/generate")
def generate_ticket_batch(count: int):
    populate_tickets_table(count)
    return {"inserted": count}

@router.get("/get", response_model=list[Ticket])
def get_ticket_batch(count: int, starting_index: int = 0):
    return get_tickets(count, starting_index)

@router.delete("/delete")
def delete_all_tickets():
    delete_count = delete_all_tickets_query()
    return {"deleted": delete_count}
