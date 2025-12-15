# Vigil Gateway - Production Dockerfile
FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN useradd -m -u 1000 vigil && \
    mkdir -p /app && \
    chown -R vigil:vigil /app

WORKDIR /app

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY --chown=vigil:vigil . .

# Switch to non-root user
USER vigil

# Set PYTHONPATH to include src
ENV PYTHONPATH=/app/src

# Expose gateway port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Run the gateway module
CMD ["python", "-m", "vigil.local_server"]
