FROM python:3.11-slim AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    curl \
    python3-dev \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

WORKDIR /tmp/build

COPY requirements.txt .

RUN python -m venv /opt/venv && \
    /opt/venv/bin/pip install --no-cache-dir --upgrade pip && \
    /opt/venv/bin/pip install --no-cache-dir -r requirements.txt

FROM python:3.11-slim AS runtime

ARG BUILD_DATE
ARG APP_VERSION

LABEL maintainer="Anna Zaitseva" \
      version="${APP_VERSION}" \
      description="FastAPI application" \
      build_date="${BUILD_DATE}" \
      website="https://github.com/ClfrnAnna/InfrastructureAdministrationLearning"

RUN apt-get update && apt-get install -y --no-install-recommends curl && \
    rm -rf /var/lib/apt/lists/* && \
    apt-get clean

RUN groupadd -r appuser && useradd -r -g appuser -s /bin/false appuser

WORKDIR /app

COPY --from=builder /opt/venv /opt/venv

COPY --chown=appuser:appuser app/main.py ./

USER appuser

ENV PATH="/opt/venv/bin:$PATH"

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]