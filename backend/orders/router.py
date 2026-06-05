"""
backend/orders/router.py

Order history endpoints.
POST /api/orders is called by the order_agent after a real order is placed.
GET  /api/orders returns the user's order history for the frontend.
"""

from fastapi import APIRouter, Depends

from backend.auth.middleware import get_current_user
from backend.db.crud import save_order, get_orders, get_chat_sessions, upsert_chat_session
from backend.db.models import OrderIn

router = APIRouter(prefix="/api", tags=["orders"])


@router.post("/orders", status_code=201)
def create_order(body: OrderIn, user=Depends(get_current_user)):
    return save_order(user["id"], body)


@router.get("/orders")
def list_orders(user=Depends(get_current_user)):
    return get_orders(user["id"])


@router.get("/sessions")
def list_sessions(user=Depends(get_current_user)):
    return get_chat_sessions(user["id"])


@router.post("/sessions")
def create_session(thread_id: str, title: str = "", user=Depends(get_current_user)):
    return upsert_chat_session(user["id"], thread_id, title)
