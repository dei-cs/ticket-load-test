from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect

from services.connection_manager import ConnectionManager
from services.ticket_info_service import TicketInfoService

router = APIRouter()


@router.get("/tickets/available")
async def get_available_tickets(request: Request):
    service: TicketInfoService = request.app.state.ticket_info_service
    return await service.get_available_tickets()


@router.websocket("/ws/tickets")
async def ws_tickets(websocket: WebSocket, request: Request):
    manager: ConnectionManager = request.app.state.connection_manager
    service: TicketInfoService = request.app.state.ticket_info_service
    await manager.connect(websocket)
    try:
        snapshot = service.get_cached_tickets()
        await websocket.send_json({"ticket_ids": snapshot})
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)
