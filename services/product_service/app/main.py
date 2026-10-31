"""FastAPI application entrypoint for Product & Inventory Service."""

import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from common.rabbitmq import RabbitMQClient
from services.product_service.app.core.config import SERVICE_NAME, RABBITMQ_URL
from services.product_service.app.database import init_db, close_db
from services.product_service.app.routers import products
from services.product_service.app.consumer import ProductEventConsumer

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("product_service")

rabbitmq_client = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager to connect databases and event broker."""
    global rabbitmq_client
    logger.info(f"Starting {SERVICE_NAME}...")

    # 1. Connect Database
    await init_db()

    # 2. Connect RabbitMQ and start event consumer
    try:
        rabbitmq_client = RabbitMQClient(RABBITMQ_URL)
        await rabbitmq_client.connect()
        consumer = ProductEventConsumer(rabbitmq_client)
        await consumer.start()
    except Exception as exc:
        logger.warning(
            f"RabbitMQ connection not established ({exc}). "
            f"Service will run in standalone mode until broker is reachable."
        )

    yield

    # Shutdown hooks
    logger.info(f"Shutting down {SERVICE_NAME}...")
    if rabbitmq_client:
        await rabbitmq_client.close()
    await close_db()


app = FastAPI(
    title="Product & Inventory Microservice",
    description="Manages product catalog and atomic inventory reservations for the E-Commerce platform.",
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
app.include_router(products.router)


@app.get("/health", tags=["Health"])
async def health_check():
    """Healthcheck endpoint for container orchestrators and load balancers."""
    return {
        "status": "healthy",
        "service": SERVICE_NAME,
    }

