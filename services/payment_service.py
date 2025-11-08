import os
import uuid
from typing import Dict
from dotenv import load_dotenv
import stripe

load_dotenv()

stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
stripe.api_version = os.getenv("STRIPE_API_VERSION", "2024-12-18.acacia")

APP_URL = os.getenv("APP_URL", "http://localhost:5173")
PRICE_PAYG = os.getenv("PRICE_PAYG")               # can be price_... or prod_...
PRICE_SUB  = os.getenv("PRICE_SUB_MONTHLY")        # can be price_... or prod_... (must be recurring!)

class PaymentService:
    @staticmethod
    def new_order_id() -> str:
        return f"ord_{uuid.uuid4().hex}"

    # ---------------- internal helpers ----------------
    @staticmethod
    def _ensure_env(value: str | None, name: str) -> str:
        if not value:
            raise RuntimeError(f"{name} not set in environment")
        return value

    @staticmethod
    def _resolve_price_id(value: str, label: str) -> str:
        """
        Accepts a price ID (price_...) or product ID (prod_...).
        If product, resolve the product's default_price.
        """
        if value.startswith("price_"):
            return value

        if value.startswith("prod_"):
            product = stripe.Product.retrieve(value)
            price_id = product.get("default_price")
            if not price_id:
                raise RuntimeError(
                    f"{label}: Product '{value}' has no default price. "
                    "Create a Price in the dashboard and set it as the product’s default, "
                    "or put a price_ ID in your env."
                )
            return price_id

        raise RuntimeError(
            f"{label}: expected a price_ or prod_ ID, got '{value}'."
        )

    # ---------------- public API ----------------
    @staticmethod
    def create_payg_checkout_session(quantity: int, metadata: Dict[str, str]):
        env_val = PaymentService._ensure_env(PRICE_PAYG, "PRICE_PAYG")
        price_id = PaymentService._resolve_price_id(env_val, "PRICE_PAYG")
        print("[Price_id]: ", price_id)

        q = int(quantity or 1)
        if q < 1:
            q = 1

        session = stripe.checkout.Session.create(
            mode="payment",
            line_items=[{"price": price_id, "quantity": q}],
            success_url=f"{APP_URL}/success?order_id={metadata.get('order_id')}"
                        f"&session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{APP_URL}/cancel?order_id={metadata.get('order_id')}",
            metadata=metadata,
        )
        return session

    @staticmethod
    def create_subscription_checkout_session(metadata: Dict[str, str]):
        env_val = PaymentService._ensure_env(PRICE_SUB, "PRICE_SUB_MONTHLY")
        price_id = PaymentService._resolve_price_id(env_val, "PRICE_SUB_MONTHLY")

        # sanity check: ensure the resolved price is actually recurring
        price = stripe.Price.retrieve(price_id)
        if price.get("type") != "recurring":
            raise RuntimeError(
                f"PRICE_SUB_MONTHLY must be a recurring price. '{price_id}' is type='{price.get('type')}'."
            )

        session = stripe.checkout.Session.create(
            mode="subscription",
            line_items=[{"price": price_id, "quantity": 1}],
            success_url=f"{APP_URL}/success?order_id={metadata.get('order_id')}"
                        f"&session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{APP_URL}/cancel?order_id={metadata.get('order_id')}",
            metadata=metadata,
        )
        return session

    @staticmethod
    def retrieve_subscription(sub_id: str):
        return stripe.Subscription.retrieve(sub_id)

    @staticmethod
    def construct_event(payload: bytes, sig_header: str, webhook_secret: str):
        return stripe.Webhook.construct_event(payload, sig_header, webhook_secret)
