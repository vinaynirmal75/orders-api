
import logging

from fastapi import (
    Depends,
    FastAPI,
    HTTPException,
    Query,
    Request,
    Response,
    status,
)
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.exceptions import ProductInUseError


from app.database import Base, engine, get_db
from app.exceptions import (
    CustomerNotFoundError,
    DuplicateCustomerEmailError,
    InsufficientStockError,
    InvalidOrderStateError,
    OrderAPIError,
    OrderAlreadyCancelledError,
    OrderNotFoundError,
    ProductNotFoundError,
)
from app.logging_config import configure_logging
from app.models import Customer, Order, Product
from app.schemas import (
    CustomerCreate,
    CustomerOut,
    OrderCreate,
    OrderOut,
    ProductCreate,
    ProductOut,
    ProductUpdate,
)
from app.services import cancel_order as cancel_order_service
from app.services import place_order
from contextlib import asynccontextmanager

# Configure logging and initialize the application.
configure_logging()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create missing tables for a fresh local development database.
    # Use migrations (e.g. Alembic) for production schema changes.
    Base.metadata.create_all(bind=engine)
    logger.info("Orders API started")
    yield


app = FastAPI(title="Orders API", lifespan=lifespan)


# Map custom errors to HTTP status codes and messages.
ERROR_RESPONSES = {
    CustomerNotFoundError: (404, "Customer not found"),
    ProductNotFoundError: (404, "Product not found"),
    OrderNotFoundError: (404, "Order not found"),
    InsufficientStockError: (409, "Insufficient stock"),
    DuplicateCustomerEmailError: (409, "Customer email already exists"),
    OrderAlreadyCancelledError: (409, "Order is already cancelled"),
    InvalidOrderStateError: (409, "Invalid order state"),
    ProductInUseError: (409, "Product is referenced by an existing order"),
}


@app.exception_handler(OrderAPIError)
async def handle_order_api_error(request: Request, exc: OrderAPIError):
    status_code, detail = ERROR_RESPONSES.get(
        type(exc),
        (400, "Request could not be processed"),
    )

    detail = str(exc) or detail

    # Log expected business errors without exposing internal details.
    logger.warning(
        "Request failed: %s %s | %s - %s",
        request.method,
        request.url.path,
        type(exc).__name__,
        detail,
    )

    return JSONResponse(
        status_code=status_code,
        content={"detail": detail},
    )


@app.get("/health")
def health():
    return {"status": "ok"}


# Product endpoints

@app.post(
    "/products",
    response_model=ProductOut,
    status_code=status.HTTP_201_CREATED,
)
def create_product(
    product_data: ProductCreate,
    db: Session = Depends(get_db),
):
    product = Product(
        name=product_data.name,
        price=product_data.price,
        stock=product_data.stock,
    )

    db.add(product)
    db.commit()
    db.refresh(product)

    logger.info("Product created: id=%s", product.id)
    return product


@app.get("/products/{product_id}", response_model=ProductOut)
def get_product(product_id: int, db: Session = Depends(get_db)):
    product = db.get(Product, product_id)

    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")

    return product


@app.get("/products", response_model=list[ProductOut])
def get_products(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    ):
    return (
        db.query(Product)
        .order_by(Product.id)
        .offset(offset)
        .limit(limit)
        .all()
    )

@app.put("/products/{product_id}", response_model=ProductOut)
def update_product(
    product_id: int,
    product_data: ProductUpdate,
    db: Session = Depends(get_db),
):
    product = db.get(Product, product_id)

    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")

    product.name = product_data.name
    product.price = product_data.price
    product.stock = product_data.stock

    db.commit()
    db.refresh(product)

    logger.info("Product updated: id=%s", product.id)
    return product


@app.delete(
    "/products/{product_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_product(
    product_id: int,
    db: Session = Depends(get_db),
    ):
    product = db.get(Product, product_id)

    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")

    try:
        db.delete(product)
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise ProductInUseError(
            "Cannot delete a product referenced by an existing order"
        ) from exc

    logger.info("Product deleted: id=%s", product_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)

# Customer endpoints

@app.post(
    "/customers",
    response_model=CustomerOut,
    status_code=status.HTTP_201_CREATED,
)
def create_customer(
    customer: CustomerCreate,
    db: Session = Depends(get_db),
):
    new_customer = Customer(
        name=customer.name,
        email=customer.email,
    )

    db.add(new_customer)

    try:
        db.commit()
        db.refresh(new_customer)
    except IntegrityError as exc:
        db.rollback()
        raise DuplicateCustomerEmailError() from exc

    logger.info("Customer created: id=%s", new_customer.id)
    return new_customer


@app.get("/customers/{customer_id}", response_model=CustomerOut)
def get_customer(
    customer_id: int,
    db: Session = Depends(get_db),
):
    customer = db.get(Customer, customer_id)

    if customer is None:
        raise HTTPException(
            status_code=404,
            detail="Customer not found",
        )

    return customer


# Order endpoints

@app.post(
    "/orders",
    response_model=OrderOut,
    status_code=status.HTTP_201_CREATED,
)
def create_order(
    payload: OrderCreate,
    db: Session = Depends(get_db),
):
    order = place_order(payload, db)
    logger.info("Order created: id=%s", order.id)
    return order


@app.get("/orders/{order_id}", response_model=OrderOut)
def get_order(order_id: int, db: Session = Depends(get_db)):
    order = db.get(Order, order_id)

    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")

    return order


@app.get("/orders", response_model=list[OrderOut])
def list_orders(
    customer_id: int | None = None,
    order_status: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=10, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    query = db.query(Order)

    if customer_id is not None:
        query = query.filter(Order.customer_id == customer_id)

    if order_status is not None:
        query = query.filter(Order.status == order_status)

    return (
        query
        .order_by(Order.id.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )


@app.post("/orders/{order_id}/cancel", response_model=OrderOut)
def cancel_order(
    order_id: int,
    db: Session = Depends(get_db),
):
    order = cancel_order_service(order_id, db)

    logger.info("Order cancelled: id=%s", order.id)
    return order