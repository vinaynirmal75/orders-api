import pytest


@pytest.fixture()
def customer_payload():
    return {
        "name": "Test Customer",
        "email": "test.customer@example.com",
    }


def test_create_customer(client, customer_payload):
    response = client.post("/customers", json=customer_payload)

    assert response.status_code == 201

    data = response.json()
    assert data["name"] == customer_payload["name"]
    assert data["email"] == customer_payload["email"]
    assert "id" in data


def test_get_existing_customer(client, customer_payload):
    created = client.post("/customers", json=customer_payload)
    customer_id = created.json()["id"]

    response = client.get(f"/customers/{customer_id}")

    assert response.status_code == 200
    assert response.json()["id"] == customer_id
    assert response.json()["email"] == customer_payload["email"]


def test_get_nonexistent_customer(client):
    response = client.get("/customers/999999")

    assert response.status_code == 404
    assert response.json()["detail"] == "Customer not found"


def test_duplicate_customer_email_returns_conflict(
    client,
    customer_payload,
):
    first = client.post("/customers", json=customer_payload)
    second = client.post("/customers", json=customer_payload)

    assert first.status_code == 201
    assert second.status_code == 409
    assert second.json()["detail"] == "Customer email already exists"


@pytest.mark.parametrize(
    "payload",
    [
        {"name": "", "email": "test@example.com"},
        {"name": "Test Customer", "email": "x"},
        {"name": "Test Customer"},
        {"email": "test@example.com"},
    ],
)
def test_create_customer_rejects_invalid_payload(client, payload):
    response = client.post("/customers", json=payload)

    assert response.status_code == 422