"""Configuration for Shipping & Fulfillment Service."""

import os

SERVICE_NAME = "shipping-service"
SERVICE_PORT = int(os.getenv("SHIPPING_SERVICE_PORT", "8006"))
RABBITMQ_URL = os.getenv("RABBITMQ_URL", "amqp://guest:guest@localhost:5672/")
DEFAULT_CARRIER = os.getenv("DEFAULT_CARRIER", "FORME Express")
