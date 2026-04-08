from fastapi import APIRouter, HTTPException, Request

from services.cart_service import CartService, TicketUnavailableError, UpstreamError

router = APIRouter()


@router.post("/cart/reserve/{ticket_id}")
async def reserve_ticket(request: Request, ticket_id: int, owner: str):
    service: CartService = request.app.state.cart_service
    try:
        return await service.reserve_ticket(ticket_id, owner)
    except TicketUnavailableError:
        raise HTTPException(status_code=409, detail="Conflict: Ticket Unavailable")
    except UpstreamError:
        raise HTTPException(status_code=502, detail="Upstream error from ticket-manager")
