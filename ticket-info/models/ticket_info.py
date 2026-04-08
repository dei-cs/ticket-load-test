from pydantic import BaseModel


class AvailableTicketsResponse(BaseModel):
    ticket_ids: list[int]
