"""FastAPI application entrypoint for Payment Service."""

import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from common.rabbitmq import RabbitMQClient
from services.payment_service.app.core.config import SERVICE_NAME, RABBITMQ_URL
from services.payment_service.app.core.broker import set_rabbitmq_client
from services.payment_service.app.database import init_db, close_db
from services.payment_service.app.routers import payments
from services.payment_service.app.consumer import PaymentEventConsumer

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("payment_service")

rabbitmq_client = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager to connect database and event broker."""
    global rabbitmq_client
    logger.info(f"Starting {SERVICE_NAME}...")

    # 1. Connect and initialize database
    await init_db()

    # 2. Connect RabbitMQ and start event consumer
    try:
        rabbitmq_client = RabbitMQClient(RABBITMQ_URL)
        await rabbitmq_client.connect()
        set_rabbitmq_client(rabbitmq_client)
        consumer = PaymentEventConsumer(rabbitmq_client)
        await consumer.start()
        logger.info("RabbitMQ broker connected and PaymentEventConsumer started.")
    except Exception as exc:
        logger.warning(
            f"RabbitMQ connection not established ({exc}). "
            f"Service will run in standalone mode until broker is reachable."
        )
        set_rabbitmq_client(None)

    yield

    # Shutdown hooks
    logger.info(f"Shutting down {SERVICE_NAME}...")
    if rabbitmq_client:
        await rabbitmq_client.close()
        set_rabbitmq_client(None)
    await close_db()


app = FastAPI(
    title="Payment Microservice",
    description="Manages payment authorizations with idempotency and coordinates saga compensation.",
    version="0.1.0",
    lifespan=lifespan,
)

# Enable CORS for frontend clients
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include Routers
app.include_router(payments.router)


@app.get("/health", tags=["Health"])
async def health_check():
    """Healthcheck endpoint for container orchestrators and load balancers."""
    return {
        "status": "healthy",
        "service": SERVICE_NAME,
    }
