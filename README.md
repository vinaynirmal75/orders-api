# Orders API

[![Orders API CI](https://github.com/vinaynirmal75/orders-api/actions/workflows/ci.yml/badge.svg)](https://github.com/vinaynirmal75/orders-api/actions/workflows/ci.yml)

A REST API for managing customers, products, and orders, built with **FastAPI, PostgreSQL, SQLAlchemy, and Pydantic**. The project includes automated tests with pytest and a GitHub Actions CI workflow.

## Features

- **Customer management** — Create customers and retrieve customer details.
- **Product management** — Create, retrieve, update, and delete products.
- **Order placement** — Place orders for customers using one or more products.
- **Inventory management** — Track product stock and restore stock when an order is cancelled.
- **Order cancellation** — Cancel eligible orders while restoring the associated product quantities.
- **Order listing** — Filter orders by customer and status, with pagination.
- **Input validation** — Validate request fields using Pydantic schemas.
- **Error handling** — Return appropriate HTTP errors for missing resources and invalid order operations.
- **Application logging** — Log application startup and important product, customer, and order operations.
- **Automated testing** — Test the API using pytest and FastAPI's test client.
- **Continuous integration** — Run the automated test suite through GitHub Actions.

## Tech Stack

| Technology | Purpose |
|---|---|
| Python | Application programming language |
| FastAPI | REST API framework |
| PostgreSQL | Relational database |
| SQLAlchemy | ORM and database access |
| Pydantic | Request validation and response schemas |
| pytest | Automated testing |
| GitHub Actions | Continuous integration |

## Project Structure

```text
orders-api/
├── .github/
│   └── workflows/
│       └── ci.yml
├── app/
│   ├── main.py
│   ├── database.py
│   ├── models.py
│   ├── schemas.py
│   ├── services.py
│   ├── exceptions.py
│   └── logging_config.py
├── tests/
│   ├── conftest.py
│   ├── test_health.py
│   ├── test_products.py
│   ├── test_customers.py
│   └── test_orders.py
├── .env.example
├── .gitignore
├── README.md
└── requirements.txt
```

## API Endpoints

### Health

| Method | Endpoint | Description |
|---|---|---|
| GET | `/health` | Check whether the API is responding |

### Customers

| Method | Endpoint | Description |
|---|---|---|
| POST | `/customers` | Create a customer |
| GET | `/customers/{customer_id}` | Retrieve a customer by ID |

### Products

| Method | Endpoint | Description |
|---|---|---|
| POST | `/products` | Create a product |
| GET | `/products` | List products with pagination |
| GET | `/products/{product_id}` | Retrieve a product by ID |
| PUT | `/products/{product_id}` | Update a product |
| DELETE | `/products/{product_id}` | Delete a product |

### Orders

| Method | Endpoint | Description |
|---|---|---|
| POST | `/orders` | Place an order |
| GET | `/orders` | List orders with optional filters and pagination |
| GET | `/orders/{order_id}` | Retrieve an order by ID |
| POST | `/orders/{order_id}/cancel` | Cancel an eligible order |

### Order listing parameters

The `GET /orders` endpoint supports the following query parameters:

| Parameter | Description | Default |
|---|---|---|
| `customer_id` | Filter orders by customer ID | No filter |
| `status` | Filter orders by status | No filter |
| `limit` | Number of orders to return; between 1 and 100 | `10` |
| `offset` | Number of orders to skip; must be non-negative | `0` |

Orders are returned in descending order of ID.

### Product listing parameters

The `GET /products` endpoint supports the following query parameters:

| Parameter | Description | Default |
|---|---|---|
| `limit` | Number of products to return; between 1 and 100 | `20` |
| `offset` | Number of products to skip; must be non-negative | `0` |

Products are returned in ascending order of ID. For example, `GET /products?limit=10&offset=10` returns the next page of up to 10 products.

## Getting Started

### Prerequisites

Install the following before running the project:

- Python
- PostgreSQL
- Git

### 1. Clone the repository

```bash
git clone https://github.com/vinaynirmal75/orders-api.git
cd orders-api
```

### 2. Create and activate a virtual environment

On Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### 3. Install dependencies

```powershell
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### 4. Configure environment variables

Create a local `.env` file in the project root using `.env.example` as a reference.

Set `DATABASE_URL` to your PostgreSQL connection string. For example:

```dotenv
DATABASE_URL=postgresql+psycopg://YOUR_USER:YOUR_PASSWORD@localhost:5432/orders_db
```

Replace the example credentials and database name with your local PostgreSQL configuration.

**Important:** Do not commit `.env` or expose database credentials in source control.

### 5. Create the database

Create the PostgreSQL database referenced by `DATABASE_URL` before starting the application.

### 6. Run the API

```powershell
uvicorn app.main:app --reload
```

Once the application starts, open the interactive API documentation at:

- Swagger UI: http://127.0.0.1:8000/docs
- ReDoc: http://127.0.0.1:8000/redoc
- Health endpoint: http://127.0.0.1:8000/health

## Running Tests

The automated tests use a **dedicated PostgreSQL database named `orders_test_db`**.

Set `TEST_DATABASE_URL` to a connection string pointing to that database. The test configuration also requires the database URL to contain `orders_test_db`.

For example, in PowerShell:

```powershell
$env:TEST_DATABASE_URL = "postgresql+psycopg://YOUR_USER:YOUR_PASSWORD@localhost:5432/orders_test_db"
pytest -v
```

Ensure the test database exists and is accessible before running the suite.

**Warning:** The test fixture creates tables and drops them during the test session. Use only the dedicated test database for automated tests, never your development or production database.

## Continuous Integration

GitHub Actions runs the test suite when changes are pushed to `main` or when a pull request targets `main`.

The workflow provisions PostgreSQL, installs project dependencies, configures the database environment variables, and runs pytest.

The CI status badge at the top of this README links to the workflow results.

## Data Model

The application uses four database models:

- **Customer** — Stores customer names and unique email addresses.
- **Product** — Stores product names, prices, and available stock.
- **Order** — Associates an order with a customer and tracks its status and creation timestamp.
- **OrderItem** — Stores the products and quantities included in an order, along with their unit prices.

## Error Handling

The API handles common errors, including:

- Resources that cannot be found.
- Duplicate customer email addresses.
- Insufficient stock when placing an order.
- Attempts to cancel an already-cancelled order.
- Invalid order-state transitions.

Errors are returned with HTTP status codes and JSON detail messages. For example, missing resources return `404`, conflicting operations such as duplicate customer emails or deleting a product referenced by an order return `409`, and invalid request payloads return `422`.

## Design Decisions

- **Database transactions:** Database changes that form one operation are committed together. Failed database operations are rolled back before the error is returned.
- **Inventory consistency:** Order placement locks the relevant product rows while checking and updating stock. Product rows are locked in ascending ID order to reduce the risk of deadlocks when an order contains multiple products.
- **Purchase-time pricing:** Each order item stores `unit_price`, preserving the product's price at the time the order was placed even if the product's current price changes later.
- **Pagination:** Product and order listing endpoints support `limit` and `offset` to keep responses manageable. Product lists default to 20 items; order lists default to 10. Both endpoints cap the limit at 100.
- **Centralized error handling:** Custom application exceptions are mapped to HTTP status codes and JSON detail messages so expected business errors do not expose raw database errors.

## Future Improvements

- **Database migrations:** Introduce Alembic to manage schema changes safely as the application evolves.
- **Additional integration and load testing:** Expand test coverage for API workflows and evaluate behavior under higher request volumes.
- **Production deployment:** Add deployment configuration and environment-specific settings.
- **Observability:** Improve structured logging, metrics, and performance monitoring.

---

**Project:** Orders API
**Repository:** [vinaynirmal75/orders-api](https://github.com/vinaynirmal75/orders-api)
