from sqlalchemy.orm import Session

from app.exceptions import (
    CustomerNotFoundError,
    InsufficientStockError,
    InvalidOrderStateError,
    OrderAlreadyCancelledError,
    OrderNotFoundError,
    ProductNotFoundError,
)
from app.models import Customer, Order, OrderItem, Product
from app.schemas import OrderCreate


def place_order(payload: OrderCreate, db: Session) -> Order:
    # 1. Verify that the customer exists.
    customer = db.get(Customer, payload.customer_id)

    if customer is None:
        raise CustomerNotFoundError("Customer not found")

    # 2. Aggregate quantities in case a product appears
    # more than once in the request.
    quantities = {}
    for item in payload.items:
        quantities[item.product_id] = (
            quantities.get(item.product_id, 0) + item.quantity
        )

    # 3. Validate every product and its available stock.
    products = {}
    for product_id, quantity in sorted(quantities.items()):
        product = (
            db.query(Product)
            .filter(Product.id == product_id)
            .with_for_update()
            .first()
            )

        if product is None:
            raise ProductNotFoundError(
                f"Product {product_id} not found"
            )

        if product.stock < quantity:
            raise InsufficientStockError()

        products[product_id] = product

    # 4. Create the order and snapshot each product's current price.
    order = Order(
        customer_id=payload.customer_id,
        status="PLACED",
    )

    for item in payload.items:
        product = products[item.product_id]

        order.items.append(
            OrderItem(
                product_id=product.id,
                quantity=item.quantity,
                unit_price=product.price,
            )
        )

    # 5. Reduce stock and persist everything.
    try:
        for product_id, quantity in quantities.items():
            products[product_id].stock -= quantity

        db.add(order)
        db.commit()
        db.refresh(order)

        return order

    except Exception:
        db.rollback()
        raise

def cancel_order(order_id: int, db: Session) -> Order:
    # 1. Lock the order row to prevent concurrent cancellations.
    order = (
        db.query(Order)
        .filter(Order.id == order_id)
        .with_for_update()
        .first()
    )

    if order is None:
        raise OrderNotFoundError("Order not found")

    # 2. Validate the order's current state while holding the lock.
    if order.status == "CANCELLED":
        raise OrderAlreadyCancelledError("Order is already cancelled")

    if order.status != "PLACED":
        raise InvalidOrderStateError(
            "Only placed orders can be cancelled"
        )

    try:
        # 3. Lock associated product rows in sorted ID order.
        items = list(order.items)
        product_ids = sorted({item.product_id for item in items})
        products = {}

        for product_id in product_ids:
            product = (
                db.query(Product)
                .filter(Product.id == product_id)
                .with_for_update()
                .first()
            )

            if product is not None:
                products[product_id] = product

        # 4. Restore stock.
        for item in items:
            product = products.get(item.product_id)

            if product is not None:
                product.stock += item.quantity

        # 5. Mark the order cancelled and commit atomically.
        order.status = "CANCELLED"
        db.commit()
        db.refresh(order)

        return order

    except Exception:
        db.rollback()
        raise