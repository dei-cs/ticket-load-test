from fastapi import APIRouter, Request

from services.ticket_info_service import TicketInfoService

router = APIRouter()


@router.get("/tickets/available")
async def get_available_tickets(request: Request):
    service: TicketInfoService = request.app.state.ticket_info_service
    return await service.get_available_tickets()
