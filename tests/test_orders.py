from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from decimal import Decimal
from uuid import uuid4


from app.exceptions import InsufficientStockError, OrderAlreadyCancelledError
from app.models import Customer, Order, OrderItem, Product
from app.schemas import OrderCreate
from app.services import place_order

import pytest
from sqlalchemy import event


@pytest.fixture()
def customer_payload():
    return {
        "name": "Order Test Customer",
        "email": "order.customer@example.com",
    }


@pytest.fixture()
def product_payload():
    return {
        "name": "Test Product",
        "price": "100.00",
        "stock": 20,
    }


@pytest.fixture()
def order_setup(client, customer_payload, product_payload):
    customer_response = client.post(
        "/customers",
        json=customer_payload,
    )
    assert customer_response.status_code == 201

    product_response = client.post(
        "/products",
        json=product_payload,
    )
    assert product_response.status_code == 201

    return {
        "customer_id": customer_response.json()["id"],
        "product_id": product_response.json()["id"],
    }


def test_create_order(client, order_setup):
    payload = {
        "customer_id": order_setup["customer_id"],
        "items": [
            {
                "product_id": order_setup["product_id"],
                "quantity": 2,
            }
        ],
    }

    response = client.post("/orders", json=payload)

    assert response.status_code == 201

    data = response.json()

    assert data["customer_id"] == order_setup["customer_id"]
    assert data["status"] == "PLACED"
    assert len(data["items"]) == 1
    assert data["items"][0]["product_id"] == order_setup["product_id"]
    assert data["items"][0]["quantity"] == 2
    assert float(data["items"][0]["unit_price"]) == 100.00


def test_creating_order_reduces_product_stock(client, order_setup):
    payload = {
        "customer_id": order_setup["customer_id"],
        "items": [
            {
                "product_id": order_setup["product_id"],
                "quantity": 4,
            }
        ],
    }

    response = client.post("/orders", json=payload)

    assert response.status_code == 201

    product_response = client.get(
        f"/products/{order_setup['product_id']}"
    )

    assert product_response.status_code == 200
    assert product_response.json()["stock"] == 16


def test_order_rejects_nonexistent_customer(client, order_setup):
    payload = {
        "customer_id": 999999,
        "items": [
            {
                "product_id": order_setup["product_id"],
                "quantity": 1,
            }
        ],
    }

    response = client.post("/orders", json=payload)

    assert response.status_code == 404
    assert response.json()["detail"] == "Customer not found"


def test_order_rejects_nonexistent_product(client, order_setup):
    payload = {
        "customer_id": order_setup["customer_id"],
        "items": [
            {
                "product_id": 999999,
                "quantity": 1,
            }
        ],
    }

    response = client.post("/orders", json=payload)

    assert response.status_code == 404
    assert response.json()["detail"] == "Product 999999 not found"


def test_order_rejects_insufficient_stock(client, order_setup):
    payload = {
        "customer_id": order_setup["customer_id"],
        "items": [
            {
                "product_id": order_setup["product_id"],
                "quantity": 21,
            }
        ],
    }

    response = client.post("/orders", json=payload)

    assert response.status_code == 409
    assert response.json()["detail"] == "Insufficient stock"

    product_response = client.get(
        f"/products/{order_setup['product_id']}"
    )

    assert product_response.json()["stock"] == 20


def test_duplicate_product_items_cannot_bypass_stock_check(
    client,
    order_setup,
):
    payload = {
        "customer_id": order_setup["customer_id"],
        "items": [
            {
                "product_id": order_setup["product_id"],
                "quantity": 12,
            },
            {
                "product_id": order_setup["product_id"],
                "quantity": 12,
            },
        ],
    }

    response = client.post("/orders", json=payload)

    assert response.status_code == 409
    assert response.json()["detail"] == "Insufficient stock"

    product_response = client.get(
        f"/products/{order_setup['product_id']}"
    )

    assert product_response.json()["stock"] == 20


def test_get_existing_order(client, order_setup):
    payload = {
        "customer_id": order_setup["customer_id"],
        "items": [
            {
                "product_id": order_setup["product_id"],
                "quantity": 2,
            }
        ],
    }

    created = client.post("/orders", json=payload)
    assert created.status_code == 201

    order_id = created.json()["id"]

    response = client.get(f"/orders/{order_id}")

    assert response.status_code == 200
    assert response.json()["id"] == order_id
    assert response.json()["customer_id"] == order_setup["customer_id"]


def test_get_nonexistent_order(client):
    response = client.get("/orders/999999")

    assert response.status_code == 404
    assert response.json()["detail"] == "Order not found"


def test_list_orders(client, order_setup):
    payload = {
        "customer_id": order_setup["customer_id"],
        "items": [
            {
                "product_id": order_setup["product_id"],
                "quantity": 1,
            }
        ],
    }

    first = client.post("/orders", json=payload)
    second = client.post("/orders", json=payload)

    assert first.status_code == 201
    assert second.status_code == 201

    response = client.get("/orders")

    assert response.status_code == 200
    assert len(response.json()) == 2


def test_filter_orders_by_customer(client, order_setup):
    payload = {
        "customer_id": order_setup["customer_id"],
        "items": [
            {
                "product_id": order_setup["product_id"],
                "quantity": 1,
            }
        ],
    }

    created = client.post("/orders", json=payload)
    assert created.status_code == 201

    response = client.get(
        f"/orders?customer_id={order_setup['customer_id']}"
    )

    assert response.status_code == 200
    assert len(response.json()) == 1
    assert (
        response.json()[0]["customer_id"]
        == order_setup["customer_id"]
    )


def test_list_orders_supports_limit_and_offset(client, order_setup):
    payload = {
        "customer_id": order_setup["customer_id"],
        "items": [
            {
                "product_id": order_setup["product_id"],
                "quantity": 1,
            }
        ],
    }

    for _ in range(3):
        response = client.post("/orders", json=payload)
        assert response.status_code == 201

    limited = client.get("/orders?limit=2")
    assert limited.status_code == 200
    assert len(limited.json()) == 2

    offset = client.get("/orders?limit=2&offset=2")
    assert offset.status_code == 200
    assert len(offset.json()) == 1


def test_cancel_order_restores_product_stock(client, order_setup):
    payload = {
        "customer_id": order_setup["customer_id"],
        "items": [
            {
                "product_id": order_setup["product_id"],
                "quantity": 5,
            }
        ],
    }

    created = client.post("/orders", json=payload)
    assert created.status_code == 201

    order_id = created.json()["id"]

    product_response = client.get(
        f"/products/{order_setup['product_id']}"
    )
    assert product_response.json()["stock"] == 15

    cancelled = client.post(f"/orders/{order_id}/cancel")

    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "CANCELLED"

    product_response = client.get(
        f"/products/{order_setup['product_id']}"
    )
    assert product_response.json()["stock"] == 20


def test_cannot_cancel_order_twice(client, order_setup):
    payload = {
        "customer_id": order_setup["customer_id"],
        "items": [
            {
                "product_id": order_setup["product_id"],
                "quantity": 2,
            }
        ],
    }

    created = client.post("/orders", json=payload)
    assert created.status_code == 201

    order_id = created.json()["id"]

    first_cancel = client.post(f"/orders/{order_id}/cancel")
    assert first_cancel.status_code == 200

    second_cancel = client.post(f"/orders/{order_id}/cancel")

    assert second_cancel.status_code == 409
    assert second_cancel.json()["detail"] == "Order is already cancelled"


def test_cancel_nonexistent_order(client):
    response = client.post("/orders/999999/cancel")

    assert response.status_code == 404
    assert response.json()["detail"] == "Order not found"


@pytest.mark.parametrize(
    "payload",
    [
        {"customer_id": 1, "items": []},
        {"customer_id": 1, "items": [{"product_id": 1, "quantity": 0}]},
        {"customer_id": 1, "items": [{"product_id": 1, "quantity": -1}]},
        {"items": [{"product_id": 1, "quantity": 1}]},
    ],
)
def test_create_order_rejects_invalid_payload(client, payload):
    response = client.post("/orders", json=payload)

    assert response.status_code == 422


def test_concurrent_orders_cannot_oversell_stock(
    independent_session_factory,
):
    SessionLocal = independent_session_factory

    # Create committed records visible to both sessions.
    setup_db = SessionLocal()
    customer = Customer(
        name="Concurrency Test Customer",
        email=f"concurrency-{uuid4().hex}@example.com",
    )
    product = Product(
        name="Last Unit",
        price=Decimal("10.00"),
        stock=1,
    )

    setup_db.add_all([customer, product])
    setup_db.commit()

    customer_id = customer.id
    product_id = product.id
    setup_db.close()

    payload = OrderCreate(
        customer_id=customer_id,
        items=[{"product_id": product_id, "quantity": 1}],
    )

    # Synchronize both workers immediately before they read the product row.
    # With SELECT ... FOR UPDATE, PostgreSQL serializes access to this row.
    # Without the lock, both workers can observe stock=1 and oversell it.
    product_read_barrier = Barrier(2)

    def is_target_product_read(statement):
        normalized = statement.lower()
        return "from products" in normalized and "where products.id" in normalized

    def synchronize_product_read(conn, cursor, statement, parameters, context, executemany):
        if is_target_product_read(statement):
            product_read_barrier.wait(timeout=10)

    def synchronize_unlocked_read_result(conn, cursor, statement, parameters, context, executemany):
        normalized = statement.lower()
        # If FOR UPDATE is removed, make both SELECTs finish before either
        # worker continues to decrement stock. With FOR UPDATE, the second
        # SELECT waits for the first transaction, so do not barrier here.
        if is_target_product_read(statement) and "for update" not in normalized:
            product_read_barrier.wait(timeout=10)

    database_engine = SessionLocal.kw["bind"]
    event.listen(database_engine, "before_cursor_execute", synchronize_product_read)
    event.listen(database_engine, "after_cursor_execute", synchronize_unlocked_read_result)

    def attempt_order():
        db = SessionLocal()
        try:
            place_order(payload, db)
            return "success"
        except InsufficientStockError:
            return "insufficient_stock"
        finally:
            db.close()

    try:
        try:
            with ThreadPoolExecutor(max_workers=2) as executor:
                results = list(
                    executor.map(
                        lambda _: attempt_order(),
                        range(2),
                    )
                )
        finally:
            # These barriers are only for the two competing worker queries.
            # Remove the listeners before verification/cleanup queries run.
            event.remove(
                database_engine,
                "before_cursor_execute",
                synchronize_product_read,
            )
            event.remove(
                database_engine,
                "after_cursor_execute",
                synchronize_unlocked_read_result,
            )

        # Only one order can purchase the final unit.
        assert results.count("success") == 1
        assert results.count("insufficient_stock") == 1

        verify_db = SessionLocal()
        try:
            remaining_product = verify_db.get(Product, product_id)

            assert remaining_product.stock == 0

            orders = (
                verify_db.query(Order)
                .filter(Order.customer_id == customer_id)
                .all()
            )
            assert len(orders) == 1
        finally:
            verify_db.close()

    finally:
        # Remove test records in foreign-key-safe order.
        cleanup_db = SessionLocal()
        try:
            order_ids = [
                order.id
                for order in cleanup_db.query(Order)
                .filter(Order.customer_id == customer_id)
                .all()
            ]

            if order_ids:
                cleanup_db.query(OrderItem).filter(
                    OrderItem.order_id.in_(order_ids)
                ).delete(synchronize_session=False)

                cleanup_db.query(Order).filter(
                    Order.id.in_(order_ids)
                ).delete(synchronize_session=False)

            cleanup_db.query(Product).filter(
                Product.id == product_id
            ).delete(synchronize_session=False)

            cleanup_db.query(Customer).filter(
                Customer.id == customer_id
            ).delete(synchronize_session=False)

            cleanup_db.commit()
        except Exception:
            cleanup_db.rollback()
            raise
        finally:
            cleanup_db.close()

def test_concurrent_cancellations_restore_stock_only_once(
    independent_session_factory,
):
    SessionLocal = independent_session_factory

    # Create a committed order with one product.
    setup_db = SessionLocal()
    customer = Customer(
        name="Cancellation Concurrency Customer",
        email=f"cancel-concurrency-{uuid4().hex}@example.com",
    )
    product = Product(
        name="Cancellation Test Product",
        price=Decimal("10.00"),
        stock=9,
    )
    setup_db.add_all([customer, product])
    setup_db.commit()
    setup_db.refresh(customer)
    setup_db.refresh(product)

    order = Order(customer_id=customer.id, status="PLACED")
    setup_db.add(order)
    setup_db.flush()

    order_item = OrderItem(
        order_id=order.id,
        product_id=product.id,
        quantity=1,
        unit_price=Decimal("10.00"),
    )
    setup_db.add(order_item)

    # Simulate stock already deducted when the order was placed.
    product.stock = 8
    setup_db.commit()

    order_id = order.id
    product_id = product.id
    setup_db.close()

    def attempt_cancellation():
        db = SessionLocal()
        try:
            from app.services import cancel_order

            cancel_order(order_id, db)
            return "success"
        except OrderAlreadyCancelledError:
            return "already_cancelled"
        finally:
            db.close()

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(
                executor.map(
                    lambda _: attempt_cancellation(),
                    range(2),
                )
            )

        assert results.count("success") == 1
        assert results.count("already_cancelled") == 1

        verify_db = SessionLocal()
        try:
            final_product = verify_db.get(Product, product_id)
            final_order = verify_db.get(Order, order_id)

            assert final_product.stock == 9
            assert final_order.status == "CANCELLED"
        finally:
            verify_db.close()

    finally:
        cleanup_db = SessionLocal()
        try:
            cleanup_order = cleanup_db.get(Order, order_id)
            if cleanup_order is not None:
                cleanup_db.delete(cleanup_order)
                cleanup_db.flush()

            cleanup_product = cleanup_db.get(Product, product_id)
            if cleanup_product is not None:
                cleanup_db.delete(cleanup_product)
                cleanup_db.flush()

            cleanup_customer = cleanup_db.get(Customer, customer.id)
            if cleanup_customer is not None:
                cleanup_db.delete(cleanup_customer)

            cleanup_db.commit()
        except Exception:
            cleanup_db.rollback()
            raise
        finally:
            cleanup_db.close()