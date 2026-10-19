
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models import Customer, Order, OrderItem, Product
from app.schemas import OrderCreate


def place_order(payload: OrderCreate, db: Session) -> Order:
    # 1. Verify that the customer exists.
    customer = db.get(Customer, payload.customer_id)

    if customer is None:
        raise HTTPException(
            status_code=404,
            detail="Customer not found",
        )

    # 2. Aggregate quantities in case a product appears
    # more than once in the request.
    quantities = {}
    for item in payload.items:
        quantities[item.product_id] = (
            quantities.get(item.product_id, 0) + item.quantity
        )

    # 3. Validate every product and its available stock.
    products = {}
    for product_id, quantity in quantities.items():
        product = db.get(Product, product_id)

        if product is None:
            raise HTTPException(
                status_code=404,
                detail=f"Product {product_id} not found",
            )

        if product.stock < quantity:
            raise HTTPException(
                status_code=400,
                detail=f"Insufficient stock for product {product_id}",
            )

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
