from pydantic import BaseModel


class ReservationResponse(BaseModel):
    reserved: int
    owner_user_id: str
