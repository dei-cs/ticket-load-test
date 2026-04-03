from pydantic import BaseModel

class Ticket(BaseModel):
    id: int
    event_type: str