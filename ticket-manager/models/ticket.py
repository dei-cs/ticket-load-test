from pydantic import BaseModel
from datetime import datetime

class Ticket(BaseModel):
    id: int
    event_type: str
    owner: str | None # Nullable field, ticket will intially have no owner
    state: str
    reserved_at: datetime | None # Nullable field, ticket will initially have no reserved_at timestamp