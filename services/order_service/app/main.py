"""FastAPI application entrypoint for Order Service."""

import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from common.rabbitmq import RabbitMQClient
from services.order_service.app.core.config import SERVICE_NAME, RABBITMQ_URL
from services.order_service.app.core.broker import set_rabbitmq_client
from services.order_service.app.database import init_db, close_db
from services.order_service.app.routers import orders
from services.order_service.app.consumer import OrderEventConsumer

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("order_service")

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
        consumer = OrderEventConsumer(rabbitmq_client)
        await consumer.start()
        logger.info("RabbitMQ broker connected and OrderEventConsumer started.")
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
    title="Order Microservice",
    description="Manages order creation, lifecycle state, and coordinates the distributed Saga.",
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
app.include_router(orders.router)


@app.get("/health", tags=["Health"])
async def health_check():
    """Healthcheck endpoint for container orchestrators and load balancers."""
    return {
        "status": "healthy",
        "service": SERVICE_NAME,
    }
