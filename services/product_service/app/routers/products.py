"""Product catalog and inventory HTTP endpoints."""

from typing import List
from fastapi import APIRouter, HTTPException, status
from services.product_service.app.models.product import (
    ProductCreate,
    ProductResponse,
    StockAdjustment,
)
from services.product_service.app.database import ProductRepository

router = APIRouter(prefix="/products", tags=["Products & Inventory"])


@router.get("", response_model=List[ProductResponse])
async def list_products(limit: int = 50, skip: int = 0):
    """Retrieve list of products with current stock counts."""
    return await ProductRepository.list_products(limit=limit, skip=skip)


@router.post("", response_model=ProductResponse, status_code=status.HTTP_201_CREATED)
async def create_product(product: ProductCreate):
    """Add a new product to the catalog."""
    data = product.model_dump() if hasattr(product, "model_dump") else product.dict()
    created = await ProductRepository.create(data)
    return created


@router.get("/{product_id}", response_model=ProductResponse)
async def get_product(product_id: str):
    """Fetch details and stock for a specific product."""
    product = await ProductRepository.get_by_id(product_id)
    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Product with id '{product_id}' not found",
        )
    return product


@router.patch("/{product_id}/stock", response_model=ProductResponse)
async def adjust_stock(product_id: str, adjustment: StockAdjustment):
    """Manually increase or decrease available stock."""
    product = await ProductRepository.get_by_id(product_id)
    if not product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")

    new_stock = product["stock_quantity"] + adjustment.delta
    if new_stock < 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Adjustment would result in negative stock quantity",
        )

    # Apply update
    if adjustment.delta > 0:
        await ProductRepository.release_reserved_stock(product_id, 0) # touch
    product["stock_quantity"] = new_stock
    return product

