import pytest


@pytest.fixture()
def product_payload():
    return {
        "name": "Gaming Mouse",
        "price": "1499.99",
        "stock": 25,
    }


def test_create_product(client, product_payload):
    response = client.post("/products", json=product_payload)

    assert response.status_code == 201

    data = response.json()
    assert data["name"] == product_payload["name"]
    assert float(data["price"]) == 1499.99
    assert data["stock"] == 25
    assert "id" in data


def test_get_existing_product(client, product_payload):
    created = client.post("/products", json=product_payload)
    product_id = created.json()["id"]

    response = client.get(f"/products/{product_id}")

    assert response.status_code == 200
    assert response.json()["id"] == product_id
    assert response.json()["name"] == "Gaming Mouse"


def test_get_nonexistent_product(client):
    response = client.get("/products/999999")

    assert response.status_code == 404
    assert response.json()["detail"] == "Product not found"


def test_list_products(client):
    client.post(
        "/products",
        json={"name": "Mouse", "price": "500.00", "stock": 10},
    )
    client.post(
        "/products",
        json={"name": "Keyboard", "price": "1200.00", "stock": 5},
    )

    response = client.get("/products")

    assert response.status_code == 200

    products = response.json()
    assert len(products) == 2
    assert {product["name"] for product in products} == {
        "Mouse",
        "Keyboard",
    }


def test_list_products_with_pagination(client):
    client.post(
        "/products",
        json={"name": "Mouse", "price": "500.00", "stock": 10},
    )
    client.post(
        "/products",
        json={"name": "Keyboard", "price": "1200.00", "stock": 5},
    )
    client.post(
        "/products",
        json={"name": "Monitor", "price": "8000.00", "stock": 3},
    )

    response = client.get("/products?limit=2&offset=1")

    assert response.status_code == 200

    products = response.json()
    assert len(products) == 2
    assert [product["name"] for product in products] == [
        "Keyboard",
        "Monitor",
    ]


def test_list_products_invalid_limit_returns_422(client):
    response = client.get("/products?limit=0")

    assert response.status_code == 422


def test_list_products_negative_offset_returns_422(client):
    response = client.get("/products?offset=-1")

    assert response.status_code == 422

def test_update_product(client, product_payload):
    created = client.post("/products", json=product_payload)
    product_id = created.json()["id"]

    updated_payload = {
        "name": "Wireless Gaming Mouse",
        "price": "1799.99",
        "stock": 30,
    }

    response = client.put(
        f"/products/{product_id}",
        json=updated_payload,
    )

    assert response.status_code == 200
    assert response.json()["name"] == "Wireless Gaming Mouse"
    assert float(response.json()["price"]) == 1799.99
    assert response.json()["stock"] == 30


def test_update_nonexistent_product(client):
    response = client.put(
        "/products/999999",
        json={"name": "Mouse", "price": "500.00", "stock": 10},
    )

    assert response.status_code == 404


def test_delete_product(client, product_payload):
    created = client.post("/products", json=product_payload)
    product_id = created.json()["id"]

    response = client.delete(f"/products/{product_id}")

    assert response.status_code == 204
    assert response.content == b""

    follow_up = client.get(f"/products/{product_id}")
    assert follow_up.status_code == 404


def test_delete_nonexistent_product(client):
    response = client.delete("/products/999999")

    assert response.status_code == 404


@pytest.mark.parametrize(
    "payload",
    [
        {"name": "Mouse", "price": "0", "stock": 10},
        {"name": "Mouse", "price": "-10", "stock": 10},
        {"name": "Mouse", "price": "100", "stock": -1},
        {"name": "", "price": "100", "stock": 10},
        {"name": "Mouse", "price": "100"},
    ],
)
def test_create_product_rejects_invalid_payload(client, payload):
    response = client.post("/products", json=payload)

    assert response.status_code == 422


def test_delete_product_referenced_by_order_returns_409(
    client,
    product_payload,
):
    # Create a product
    product_response = client.post(
        "/products",
        json=product_payload,
    )
    product_id = product_response.json()["id"]

    # Create a customer
    customer_response = client.post(
        "/customers",
        json={
            "name": "Test Customer",
            "email": "delete-product-test@example.com",
        },
    )
    customer_id = customer_response.json()["id"]

    # Create an order referencing the product
    order_response = client.post(
        "/orders",
        json={
            "customer_id": customer_id,
            "items": [
                {
                    "product_id": product_id,
                    "quantity": 1,
                }
            ],
        },
    )

    assert order_response.status_code == 201

    # Attempt to delete the referenced product
    delete_response = client.delete(f"/products/{product_id}")

    assert delete_response.status_code == 409
    assert "referenced by an existing order" in (
        delete_response.json()["detail"].lower()
    )

    # Verify the product still exists
    get_response = client.get(f"/products/{product_id}")
    assert get_response.status_code == 200

@pytest.mark.parametrize(
    "price",
    [
        "12.345",          # More than 2 decimal places
        "123456789.00",    # Exceeds Numeric(10, 2) precision
    ],
)
def test_create_product_rejects_invalid_price_precision(client, price):
    response = client.post(
        "/products",
        json={"name": "Test Product", "price": price, "stock": 10},
    )

    assert response.status_code == 422


def test_update_product_rejects_invalid_price_precision(client, product_payload):
    created = client.post("/products", json=product_payload)
    product_id = created.json()["id"]

    response = client.put(
        f"/products/{product_id}",
        json={
            "name": "Updated Product",
            "price": "12.345",
            "stock": 10,
        },
    )

    assert response.status_code == 422