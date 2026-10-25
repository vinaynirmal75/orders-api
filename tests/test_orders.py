
import pytest


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

    assert response.status_code == 400
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

    assert response.status_code == 400
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
