from fastapi import FastAPI, Depends, Response, status, HTTPException, Query
from sqlalchemy.orm import Session
from app.schemas import OrderCreate, OrderOut
from app.services import place_order


from app.database import Base, engine, get_db
from app.models import Product, Customer, Order
from app.schemas import ProductCreate, ProductOut, ProductUpdate, CustomerCreate, CustomerOut, OrderOut
from sqlalchemy.exc import IntegrityError

import app.models

Base.metadata.create_all(bind=engine)
app = FastAPI(title="Orders API")

@app.get("/health")
def health():
    return {"status": "ok"}

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

    return product

@app.get("/products/{product_id}", response_model=ProductOut)
def get_product(product_id: int, db: Session = Depends(get_db)):
    product = db.get(Product, product_id)

    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")

    return product

@app.get("/products", response_model=list[ProductOut])
def get_products(db: Session = Depends(get_db)):
    products = db.query(Product).all()
    return products

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
        raise HTTPException(
            status_code=404,
            detail="Product not found",
        )

    db.delete(product)
    db.commit()

    return Response(status_code=status.HTTP_204_NO_CONTENT)


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
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Customer email already exists",
        )

    return new_customer


@app.get("/customers/{customer_id}", response_model=CustomerOut)
def get_customer(
    customer_id: int,
    db: Session = Depends(get_db),
):
    customer = db.get(Customer, customer_id)

    if customer is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Customer not found",
        )

    return customer

@app.post(
    "/orders",
    response_model=OrderOut,
    status_code=status.HTTP_201_CREATED,
)
def create_order(
    payload: OrderCreate,
    db: Session = Depends(get_db),
):
    return place_order(payload, db)

@app.get("/orders/{order_id}", response_model=OrderOut)
def get_order(
    order_id: int,
    db: Session = Depends(get_db),
):
    order = db.get(Order, order_id)

    if order is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Order not found",
        )

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
    order = db.get(Order, order_id)

    if order is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Order not found",
        )

    if order.status == "CANCELLED":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Order is already cancelled",
        )

    if order.status != "PLACED":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only placed orders can be cancelled",
        )

    try:
        for item in order.items:
            product = db.get(Product, item.product_id)

            if product is not None:
                product.stock += item.quantity

        order.status = "CANCELLED"
        db.commit()
        db.refresh(order)

        return order

    except Exception:
        db.rollback()
        raise