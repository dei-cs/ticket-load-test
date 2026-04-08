from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from services.cart_service import CartService, TicketUnavailableError

router = APIRouter()


@router.post("/cart/reserve/{ticket_id}", status_code=202)
async def reserve_ticket(request: Request, ticket_id: int, owner: str):
    service: CartService = request.app.state.cart_service
    try:
        result = await service.reserve_ticket(ticket_id, owner)
        return JSONResponse(status_code=202, content=result)
    except TicketUnavailableError:
        raise HTTPException(status_code=409, detail="Conflict: Ticket Unavailable")
