"""Configuration for Persistent Cart & Wishlist Service."""

import os

SERVICE_NAME = "cart-service"
SERVICE_PORT = int(os.getenv("CART_SERVICE_PORT", "8009"))
RABBITMQ_URL = os.getenv("RABBITMQ_URL", "amqp://guest:guest@localhost:5672/")
