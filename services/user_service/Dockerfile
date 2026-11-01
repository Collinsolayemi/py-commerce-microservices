FROM python:3.11-slim

WORKDIR /app

# Prevent Python from writing .pyc and enable unbuffered output
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Install shared library
COPY common /app/common
RUN pip install --no-cache-dir -e /app/common

# Install service dependencies
COPY services/user_service/requirements.txt /app/services/user_service/
RUN pip install --no-cache-dir -r /app/services/user_service/requirements.txt

# Copy service source code
COPY services/user_service /app/services/user_service

ENV PYTHONPATH=/app

EXPOSE 8001

CMD ["uvicorn", "services.user_service.app.main:app", "--host", "0.0.0.0", "--port", "8001"]
