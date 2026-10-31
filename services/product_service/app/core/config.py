"""Configuration settings for Product & Inventory Service."""

import os
from dotenv import load_dotenv

load_dotenv()

SERVICE_NAME = "product-inventory-service"
PORT = int(os.getenv("PORT", "8002"))

# MongoDB Configuration
MONGODB_URL = os.getenv("MONGODB_URL", "mongodb://admin:adminpassword@localhost:27017/catalog_db?authSource=admin")
MONGODB_DB_NAME = os.getenv("MONGODB_DB_NAME", "catalog_db")

# RabbitMQ Configuration
RABBITMQ_URL = os.getenv("RABBITMQ_URL", "amqp://guest:guest@localhost:5672/")
