"""Configuration for Product Reviews & Ratings Service."""

import os

SERVICE_NAME = "review-service"
SERVICE_PORT = int(os.getenv("REVIEW_SERVICE_PORT", "8007"))
RABBITMQ_URL = os.getenv("RABBITMQ_URL", "amqp://guest:guest@localhost:5672/")

