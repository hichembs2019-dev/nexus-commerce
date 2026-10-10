FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src ./src

# Persisted via the docker-compose volume mount - see docker-compose.yml.
ENV DATABASE_PATH=/data/nexus_commerce.db
VOLUME ["/data"]

CMD ["python", "-m", "src.main"]
