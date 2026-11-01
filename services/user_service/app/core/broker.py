"""RabbitMQ client singleton accessor to prevent circular imports."""

from typing import Optional
from common.rabbitmq import RabbitMQClient

_rabbitmq_client: Optional[RabbitMQClient] = None


def set_rabbitmq_client(client: Optional[RabbitMQClient]) -> None:
    global _rabbitmq_client
    _rabbitmq_client = client


def get_rabbitmq_client() -> Optional[RabbitMQClient]:
    return _rabbitmq_client

