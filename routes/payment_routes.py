import os
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import PlainTextResponse
from dotenv import load_dotenv

from services.payment_service import PaymentService
from models.payment_models import ORDERS, SUBSCRIPTIONS, Order, SubscriptionState, SessionReq

load_dotenv()

router = APIRouter(prefix="/api/payment", tags=["Payments"])
PK = os.getenv("STRIPE_PUBLISHABLE_KEY")
WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET")  # set via Stripe CLI or dashboard

@router.get("/config")
async def config():
    if not PK:
        raise HTTPException(500, "Publishable key missing")
    return {"publishable_key": PK}

@router.post("/payg/checkout-session")
async def payg_checkout(req: SessionReq):
    # 1) make a pending order
    order_id = PaymentService.new_order_id()
    order = Order(id=order_id, user_id=req.user_id, mode="payment")
    ORDERS[order_id] = order

    # 2) create checkout session
    session = PaymentService.create_payg_checkout_session(
        quantity=req.quantity or 1,
        metadata={"order_id": order_id, "user_id": req.user_id, "plan": "payg"},
    )
    # 3) store refs
    order.stripe_session_id = session.id
    order.stripe_payment_intent = session.payment_intent
    return {"order_id": order_id, "url": session.url, "session_id": session.id}

@router.post("/subscription/checkout-session")
async def subscription_checkout(req: SessionReq):
    order_id = PaymentService.new_order_id()
    order = Order(id=order_id, user_id=req.user_id, mode="subscription")
    ORDERS[order_id] = order

    session = PaymentService.create_subscription_checkout_session(
        metadata={"order_id": order_id, "user_id": req.user_id, "plan": "subscription"},
    )
    order.stripe_session_id = session.id
    order.stripe_payment_intent = session.payment_intent
    return {"order_id": order_id, "url": session.url, "session_id": session.id}

@router.get("/orders/{order_id}")
async def read_order(order_id: str):
    order = ORDERS.get(order_id)
    if not order:
        raise HTTPException(404, "Order not found")
    return {
        "id": order.id,
        "user_id": order.user_id,
        "mode": order.mode,
        "status": order.status,
        "session_id": order.stripe_session_id,
        "payment_intent": order.stripe_payment_intent,
        "amount_total": order.amount_total,
    }

@router.post("/webhook", include_in_schema=False)
async def webhook(request: Request):
    if not WEBHOOK_SECRET:
        return PlainTextResponse("Webhook not configured", status_code=500)

    payload = await request.body()
    sig = request.headers.get("Stripe-Signature", "")

    try:
        event = PaymentService.construct_event(payload, sig, WEBHOOK_SECRET)
    except Exception as e:
        return PlainTextResponse(f"Invalid signature: {e}", status_code=400)

    etype = event["type"]
    obj = event["data"]["object"]

    # one handler to understand both flows via Checkout
    if etype == "checkout.session.completed":
        meta = obj.get("metadata") or {}
        order_id = meta.get("order_id")
        user_id = meta.get("user_id")
        plan = meta.get("plan")
        amount = obj.get("amount_total")
        pi_id = obj.get("payment_intent")

        if order_id in ORDERS:
            order = ORDERS[order_id]
            order.status = "paid"
            order.amount_total = amount
            order.stripe_payment_intent = pi_id

            if plan == "subscription":
                # store basic subscription state so you can check access later
                sub_id = obj.get("subscription")
                if sub_id:
                    sub = PaymentService.retrieve_subscription(sub_id)
                    SUBSCRIPTIONS[user_id] = SubscriptionState(
                        user_id=user_id,
                        stripe_customer_id=sub.customer,
                        stripe_subscription_id=sub.id,
                        status=sub.status,
                        current_period_end=sub.current_period_end,
                    )

    # keep sub status in sync over time (optional but good practice)
    elif etype in (
        "customer.subscription.created",
        "customer.subscription.updated",
        "customer.subscription.deleted",
    ):
        sub = obj
        # You’d map sub.customer -> your user_id in a real DB.
        # Omitted here because this is a tiny demo.

    return PlainTextResponse("ok", status_code=200)
