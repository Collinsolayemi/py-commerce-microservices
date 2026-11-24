"""Unit tests verifying serialization and validation of domain event models."""

import json
from common.events import (
    OrderItem,
    OrderCreatedEvent,
    InventoryReservedEvent,
    InventoryFailedEvent,
    PaymentSucceededEvent,
    PaymentFailedEvent,
    CouponCreatedEvent,
    CouponRedeemedEvent,
    CouponReleasedEvent,
)


def test_order_created_event_serialization():
    item1 = OrderItem(product_id="prod_101", quantity=2, unit_price=49.99)
    item2 = OrderItem(product_id="prod_102", quantity=1, unit_price=19.99)

    event = OrderCreatedEvent(
        order_id="ord_abc123",
        user_id="usr_999",
        items=[item1, item2],
        total_amount=119.97,
    )

    # Serialize
    json_str = event.model_dump_json() if hasattr(event, "model_dump_json") else event.json()
    assert "ord_abc123" in json_str
    assert "event_id" in json_str
    assert "timestamp" in json_str

    # Deserialize
    parsed = json.loads(json_str)
    reconstructed = OrderCreatedEvent(**parsed)
    assert reconstructed.order_id == "ord_abc123"
    assert len(reconstructed.items) == 2
    assert reconstructed.items[0].quantity == 2


def test_payment_events():
    succeed_event = PaymentSucceededEvent(
        payment_id="pay_001",
        order_id="ord_abc123",
        user_id="usr_999",
        amount=119.97,
    )
    assert succeed_event.amount == 119.97
    assert succeed_event.event_id is not None

    fail_event = PaymentFailedEvent(
        order_id="ord_abc123",
        user_id="usr_999",
        amount=119.97,
        reason="Insufficient funds",
    )
    assert fail_event.reason == "Insufficient funds"


def test_coupon_events():
    created = CouponCreatedEvent(
        coupon_id="cpn_001",
        code="WELCOME20",
        discount_type="PERCENTAGE",
        discount_value=20.0,
    )
    redeemed = CouponRedeemedEvent(
        redemption_id="rdm_001",
        coupon_id="cpn_001",
        code="WELCOME20",
        order_id="ord_abc123",
        user_id="usr_999",
        discount_amount=20.0,
        final_amount=80.0,
    )
    released = CouponReleasedEvent(
        redemption_id="rdm_001",
        code="WELCOME20",
        order_id="ord_abc123",
        user_id="usr_999",
        reason="Order cancelled",
    )
    assert created.code == "WELCOME20"
    assert redeemed.final_amount == 80.0
    assert released.reason == "Order cancelled"


if __name__ == "__main__":
    test_order_created_event_serialization()
    test_payment_events()
    test_coupon_events()
    print("✅ All event schema tests passed successfully!")

