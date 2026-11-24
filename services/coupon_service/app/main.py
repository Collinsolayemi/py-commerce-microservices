"""FastAPI application entrypoint for Promotions & Coupons Service."""

import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from common.rabbitmq import RabbitMQClient
from services.coupon_service.app.consumer import CouponConsumer
from services.coupon_service.app.core.config import RABBITMQ_URL, SERVICE_NAME
from services.coupon_service.app.routers.coupons import router as coupons_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("coupon_service")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Connect RabbitMQ and start CouponConsumer; fall back gracefully if broker is offline."""
    logger.info(f"Starting {SERVICE_NAME}...")
    app.state.rabbitmq_client = None

    try:
        client = RabbitMQClient(RABBITMQ_URL)
        await client.connect()
        consumer = CouponConsumer(client)
        await consumer.start()
        app.state.rabbitmq_client = client
        logger.info("RabbitMQ broker connected and CouponConsumer listening.")
    except Exception as exc:
        logger.warning(
            f"RabbitMQ connection not established ({exc}). "
            "Coupon service running in standalone mode."
        )

    yield

    logger.info(f"Shutting down {SERVICE_NAME}...")
    if app.state.rabbitmq_client is not None:
        await app.state.rabbitmq_client.close()


app = FastAPI(
    title="Promotions & Coupons Microservice",
    description="Promotional discount codes, idempotent order redemptions, and Saga quota release.",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(coupons_router)


@app.get("/health", tags=["Health"])
async def health_check():
    return {
        "status": "healthy",
        "service": SERVICE_NAME,
    }

