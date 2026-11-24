FROM python:3.11-slim

WORKDIR /app

COPY common /app/common
RUN pip install --no-cache-dir /app/common

COPY services/coupon_service/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY services /app/services

EXPOSE 8008

CMD ["uvicorn", "services.coupon_service.app.main:app", "--host", "0.0.0.0", "--port", "8008"]

