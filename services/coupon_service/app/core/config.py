"""Configuration for Promotions & Coupons Service."""

import os

SERVICE_NAME = "coupon-service"
SERVICE_PORT = int(os.getenv("COUPON_SERVICE_PORT", "8008"))
RABBITMQ_URL = os.getenv("RABBITMQ_URL", "amqp://guest:guest@localhost:5672/")

