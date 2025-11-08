from typing import Dict, Literal, Optional
from pydantic import BaseModel

# super simple in-memory store
ORDERS: Dict[str, "Order"] = {}
SUBSCRIPTIONS: Dict[str, "SubscriptionState"] = {}  # keyed by user_id

OrderStatus = Literal["pending", "paid", "canceled"]

class Order(BaseModel):
    id: str
    user_id: str
    mode: Literal["payment", "subscription"]
    status: OrderStatus = "pending"
    stripe_session_id: Optional[str] = None
    stripe_payment_intent: Optional[str] = None
    amount_total: Optional[int] = None

class SubscriptionState(BaseModel):
    user_id: str
    stripe_customer_id: Optional[str] = None
    stripe_subscription_id: Optional[str] = None
    status: Optional[str] = None           # active/trialing/past_due/canceled
    current_period_end: Optional[int] = None

class SessionReq(BaseModel):
    user_id: str
    quantity: int | None = 1 