# ---------- Builder stage: build wheels ----------
FROM python:3.11-slim AS builder

# Install build dependencies
RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    g++ \
    git \
    curl \
    ca-certificates \
    libpq-dev \
    libffi-dev \
    libssl-dev \
    cargo \
    libjpeg-dev \
    zlib1g-dev \
    wget \
    pkg-config \
    && rm -rf /var/lib/apt/lists/*

ENV APP_HOME=/opt/app
RUN useradd --create-home --home-dir $APP_HOME appuser
WORKDIR $APP_HOME

COPY requirements.txt .
RUN python -m pip install --upgrade pip setuptools wheel \
 && python -m pip wheel --no-cache-dir --wheel-dir /wheels -r requirements.txt

# ---------- Final runtime stage ----------
FROM python:3.11-slim

RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
    libpq5 \
    libjpeg62-turbo \
    zlib1g \
    && rm -rf /var/lib/apt/lists/*

ENV APP_HOME=/opt/app
WORKDIR $APP_HOME

RUN useradd --create-home --home-dir $APP_HOME appuser
USER appuser

COPY --from=builder /wheels /wheels
COPY --from=builder /opt/app/requirements.txt ./requirements.txt

RUN python -m pip install --upgrade pip \
 && python -m pip install --no-index --find-links=/wheels -r requirements.txt --no-cache-dir \
 && rm -rf /wheels

# Copy source code
COPY . .

EXPOSE 8001

# ✅ Run FastAPI with uvicorn on port 8001 with reload
CMD ["uvicorn", "src.main:app", "--reload", "--host", "0.0.0.0", "--port", "8001"]
