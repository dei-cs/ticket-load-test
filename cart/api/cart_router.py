from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from services.cart_service import CartService, NoTicketsAvailableError, TicketDoubleBookingError

router = APIRouter()

class ReserveBatchRequest(BaseModel):
    count: int
    owner: str

@router.post("/cart/reserve-batch", status_code=200)
async def reserve_ticket_batch(request: Request, body: ReserveBatchRequest):
    service: CartService = request.app.state.cart_service
    try:
        reserved_tickets = await service.reserve_ticket_batch_atomic_with_locking(body.count, body.owner)
        return JSONResponse(status_code=200, content={"reserved": reserved_tickets, "owner": body.owner})
    except NoTicketsAvailableError as e:
        return JSONResponse(status_code=503, content={
            "error": "NO_TICKETS_AVAILABLE",
            "requested": e.requested,
            "last_checked": e.last_checked.isoformat()
            })


@router.post("/cart/reserve-batch-unsafe", status_code=200)
async def reserve_ticket_batch_unsafe(request: Request, body: ReserveBatchRequest):
    service: CartService = request.app.state.cart_service
    try:
        reserved_tickets = await service.reserve_ticket_batch_no_locking(body.count, body.owner)
        return JSONResponse(status_code=200, content={"reserved": reserved_tickets, "owner": body.owner})
    except NoTicketsAvailableError as e:
        return JSONResponse(status_code=503, content={
            "error": "NO_TICKETS_AVAILABLE",
            "requested": e.requested,
            "last_checked": e.last_checked.isoformat()
        })
    except TicketDoubleBookingError as e:
        return JSONResponse(status_code=409, content={
            "error": "DOUBLE_BOOKING_DETECTED",
            "requested": e.requested,
            "actually_reserved": e.actually_reserved
        })