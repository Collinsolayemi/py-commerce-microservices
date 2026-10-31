"""RabbitMQ client wrapper using aio-pika for asynchronous pub/sub messaging."""

from __future__ import annotations
import json
import logging
from typing import Callable, Awaitable, List, Optional
import aio_pika
from aio_pika.abc import (
    AbstractRobustConnection,
    AbstractRobustChannel,
    AbstractRobustExchange,
    AbstractIncomingMessage,
)

from common.config import ECOMMERCE_EXCHANGE, ECOMMERCE_EXCHANGE_TYPE
from common.events import BaseEvent

logger = logging.getLogger("rabbitmq")


class RabbitMQClient:
    """Async RabbitMQ client supporting topic exchange publishing and consumer bindings."""

    def __init__(self, rabbitmq_url: str):
        self.rabbitmq_url = rabbitmq_url
        self.connection: Optional[AbstractRobustConnection] = None
        self.channel: Optional[AbstractRobustChannel] = None
        self.exchange: Optional[AbstractRobustExchange] = None

    async def connect(self) -> None:
        """Establish robust connection and declare primary topic exchange."""
        logger.info(f"Connecting to RabbitMQ at {self.rabbitmq_url}...")
        self.connection = await aio_pika.connect_robust(self.rabbitmq_url)
        self.channel = await self.connection.channel()
        
        # Fair dispatch - prefetch 10 messages per worker
        await self.channel.set_qos(prefetch_count=10)

        # Declare main topic exchange (durable)
        self.exchange = await self.channel.declare_exchange(
            name=ECOMMERCE_EXCHANGE,
            type=ECOMMERCE_EXCHANGE_TYPE,
            durable=True,
        )
        logger.info(f"RabbitMQ connected. Topic exchange '{ECOMMERCE_EXCHANGE}' ready.")

    async def publish(self, routing_key: str, event: BaseEvent) -> None:
        """Publish a Pydantic event to the topic exchange with persistent delivery."""
        if not self.exchange:
            raise RuntimeError("RabbitMQ exchange is not initialized. Call connect() first.")

        payload_bytes = event.model_dump_json().encode("utf-8") if hasattr(event, "model_dump_json") else event.json().encode("utf-8")

        message = aio_pika.Message(
            body=payload_bytes,
            content_type="application/json",
            delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
            message_id=event.event_id,
        )

        await self.exchange.publish(message, routing_key=routing_key)
        logger.info(f"Published event [{event.__class__.__name__}] -> key: '{routing_key}' (ID: {event.event_id})")

    async def setup_consumer(
        self,
        queue_name: str,
        routing_keys: List[str],
        callback: Callable[[AbstractIncomingMessage], Awaitable[None]],
    ) -> None:
        """Declare a persistent queue, bind it to routing keys, and register the consumer callback."""
        if not self.channel or not self.exchange:
            raise RuntimeError("RabbitMQ channel/exchange not initialized. Call connect() first.")

        # Declare durable queue
        queue = await self.channel.declare_queue(name=queue_name, durable=True)

        # Bind queue to each routing key pattern
        for key in routing_keys:
            await queue.bind(self.exchange, routing_key=key)
            logger.info(f"Queue '{queue_name}' bound to routing key '{key}'")

        # Start consuming
        await queue.consume(callback)
        logger.info(f"Consumer started on queue '{queue_name}'")

    async def close(self) -> None:
        """Gracefully close channel and connection."""
        if self.channel and not self.channel.is_closed:
            await self.channel.close()
        if self.connection and not self.connection.is_closed:
            await self.connection.close()
        logger.info("RabbitMQ connection closed.")

