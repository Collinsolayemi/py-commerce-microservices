"""Configuration settings for Notification Service."""

import os
from dotenv import load_dotenv

load_dotenv()

SERVICE_NAME = "notification-service"
PORT = int(os.getenv("PORT", "8005"))

# RabbitMQ Configuration
RABBITMQ_URL = os.getenv("RABBITMQ_URL", "amqp://guest:guest@localhost:5672/")

