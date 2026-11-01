"""REST API endpoints for inspecting dispatched notifications."""

from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Query, status

from services.notification_service.app.consumer import NotificationStore

router = APIRouter(prefix="/notifications", tags=["Notifications"])


@router.get(
    "",
    response_model=List[Dict[str, Any]],
    summary="List sent notifications",
    description="Retrieve all sent email, SMS, and push notification audit logs with optional order filter.",
)
async def list_notifications(
    order_id: Optional[str] = Query(None, description="Filter notifications by Order ID")
) -> List[Dict[str, Any]]:
    return NotificationStore.list(order_id=order_id)


@router.get(
    "/{order_id}",
    response_model=List[Dict[str, Any]],
    summary="Get notifications for order",
    description="Retrieve all notifications dispatched for a specific order.",
)
async def get_order_notifications(order_id: str) -> List[Dict[str, Any]]:
    return NotificationStore.list(order_id=order_id)


@router.delete(
    "",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Clear notification logs",
    description="Purge in-memory notification audit log (helpful for testing cycles).",
)
async def clear_notifications() -> None:
    NotificationStore.clear()

