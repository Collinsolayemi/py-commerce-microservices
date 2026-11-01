FROM python:3.11-slim

WORKDIR /app

# Prevent Python from writing .pyc and enable unbuffered output
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Install shared library
COPY common /app/common
RUN pip install --no-cache-dir -e /app/common

# Install service dependencies
COPY services/notification_service/requirements.txt /app/services/notification_service/
RUN pip install --no-cache-dir -r /app/services/notification_service/requirements.txt

# Copy service source code
COPY services/notification_service /app/services/notification_service

ENV PYTHONPATH=/app

EXPOSE 8005

CMD ["uvicorn", "services.notification_service.app.main:app", "--host", "0.0.0.0", "--port", "8005"]

