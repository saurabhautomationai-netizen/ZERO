# syntax=docker/dockerfile:1
FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy ZERO source code and documentation
COPY zero_core/ /app/zero_core/
COPY docs/ /app/docs/

EXPOSE 8000

# Healthcheck to ensure FastAPI app responds
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/agents || exit 1

# Default entrypoint: Run FastAPI server via Uvicorn
CMD ["uvicorn", "zero_core.interfaces.web.app:app", "--host", "0.0.0.0", "--port", "8000"]
