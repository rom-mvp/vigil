# Use a lightweight Python image
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# 1. Install System Deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# 2. Install Python Deps (Cached Layer)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 3. Download Spacy Model (Baked into image for speed)
RUN python -m spacy download en_core_web_sm

# 4. Copy Application Code
COPY firewall_engine.py .
COPY pii_engine.py .
COPY local_server.py .
COPY dashboard_server.py .
COPY dashboard.html .

# 5. Environment Defaults
ENV VIGIL_MODE=local
ENV PYTHONUNBUFFERED=1

# 6. Expose Ports (8000=Proxy, 5000=Dashboard)
EXPOSE 8000
EXPOSE 5000

# Default command: Run the Local Proxy
CMD ["python", "local_server.py"]
