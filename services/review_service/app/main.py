"""FastAPI application entrypoint for Product Reviews & Ratings Service."""

import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from common.rabbitmq import RabbitMQClient
from services.review_service.app.core.config import RABBITMQ_URL, SERVICE_NAME
from services.review_service.app.routers.reviews import router as reviews_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("review_service")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(f"Starting {SERVICE_NAME}...")
    app.state.rabbitmq_client = None

    try:
        client = RabbitMQClient(RABBITMQ_URL)
        await client.connect()
        app.state.rabbitmq_client = client
        logger.info("RabbitMQ broker connected for Review Service.")
    except Exception as exc:
        logger.warning(
            f"RabbitMQ connection not established ({exc}). "
            "Review service running in standalone mode."
        )

    yield

    logger.info(f"Shutting down {SERVICE_NAME}...")
    if app.state.rabbitmq_client is not None:
        await app.state.rabbitmq_client.close()


app = FastAPI(
    title="Product Reviews & Ratings Microservice",
    description="Authenticated product reviews, star ratings breakdown, and event emission.",
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

app.include_router(reviews_router)


@app.get("/health", tags=["Health"])
async def health_check():
    return {
        "status": "healthy",
        "service": SERVICE_NAME,
    }
