FROM python:3.11-slim

WORKDIR /app

COPY common /app/common
RUN pip install --no-cache-dir /app/common

COPY services/cart_service/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY services /app/services

EXPOSE 8009

CMD ["uvicorn", "services.cart_service.app.main:app", "--host", "0.0.0.0", "--port", "8009"]
