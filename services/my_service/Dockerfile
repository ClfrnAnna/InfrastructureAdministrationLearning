FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends procps && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

RUN adduser --disabled-password --gecos '' appuser

COPY app/app.py .

RUN mkdir -p /app/log/my_service && chown -R appuser:appuser /app

USER appuser

CMD ["python", "app.py"]