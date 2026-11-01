"""FastAPI application entrypoint for Notification Service."""

import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from common.rabbitmq import RabbitMQClient
from services.notification_service.app.core.config import SERVICE_NAME, RABBITMQ_URL
from services.notification_service.app.consumer import NotificationConsumer
from services.notification_service.app.routers.notifications import router as notifications_router

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("notification_service")

rabbitmq_client = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager to connect RabbitMQ and start event consumer."""
    global rabbitmq_client
    logger.info(f"Starting {SERVICE_NAME}...")

    # Connect RabbitMQ and start consumer
    try:
        rabbitmq_client = RabbitMQClient(RABBITMQ_URL)
        await rabbitmq_client.connect()
        consumer = NotificationConsumer(rabbitmq_client)
        await consumer.start()
        logger.info("RabbitMQ broker connected and NotificationConsumer listening.")
    except Exception as exc:
        logger.warning(
            f"RabbitMQ connection not established ({exc}). "
            f"Notification service running in standalone mock mode."
        )

    yield

    # Shutdown hooks
    logger.info(f"Shutting down {SERVICE_NAME}...")
    if rabbitmq_client:
        await rabbitmq_client.close()


app = FastAPI(
    title="Notification Microservice",
    description="Consumes events across the distributed platform and dispatches customer notifications.",
    version="0.1.0",
    lifespan=lifespan,
)

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include Routers
app.include_router(notifications_router)


@app.get("/health", tags=["Health"])
async def health_check():
    """Healthcheck endpoint for orchestrators and load balancers."""
    return {
        "status": "healthy",
        "service": SERVICE_NAME,
    }

