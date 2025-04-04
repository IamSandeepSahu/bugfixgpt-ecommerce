FROM python:3.9-slim

WORKDIR /sample-ecommerce-services/inventory

RUN mkdir -p /logs

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "app.py"]
