# 🚀 Vigil Production Deployment Guide

## Overview

This guide covers deploying **Vigil Gateway** (the high-performance edge service) to production with GPU support for vector threat scanning.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│ EDGE LOCATIONS (AWS G4/G5, GCP T4, Azure NC-series)        │
│                                                             │
│  ┌────────────────────────────────────────────────────┐    │
│  │ Vigil Gateway (GPU)                                │    │
│  │ - NVIDIA CUDA 12.0                                 │    │
│  │ - ONNX Runtime GPU                                 │    │
│  │ - Vector Threat DB (VRAM)                          │    │
│  │ - API Key Authentication                           │    │
│  │ - Rate Limiting (Redis)                            │    │
│  │ - Port: 8000                                       │    │
│  └────────────────────────────────────────────────────┘    │
│                                                             │
└─────────────────────┬───────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────┐
│ CENTRAL CONTROL PLANE (Standard Compute)                    │
│                                                             │
│  ┌────────────────────────────────────────────────────┐    │
│  │ AgentShield (CPU)                                  │    │
│  │ - Policy Evaluation                                │    │
│  │ - Vault (LLM Keys)                                 │    │
│  │ - Decision Signing (Ed25519)                       │    │
│  │ - Port: 9000                                       │    │
│  └────────────────────────────────────────────────────┘    │
│                                                             │
│  ┌────────────────────────────────────────────────────┐    │
│  │ Redis (State)                                      │    │
│  │ - API Keys                                         │    │
│  │ - Rate Limits                                      │    │
│  │ - Billing Queue                                    │    │
│  │ - Port: 6379                                       │    │
│  └────────────────────────────────────────────────────┘    │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

## Prerequisites

### 1. GPU Instance (for Vigil)

**AWS:**
- Instance type: `g4dn.xlarge` (1x NVIDIA T4, 4 vCPU, 16GB RAM) - $0.526/hr
- Instance type: `g5.xlarge` (1x NVIDIA A10G, 4 vCPU, 16GB RAM) - $1.006/hr
- AMI: Deep Learning AMI (Ubuntu 22.04) with pre-installed CUDA drivers

**GCP:**
- Machine type: `n1-standard-4` + `nvidia-tesla-t4` GPU
- Image: `ubuntu-2204-lts` with NVIDIA GPU drivers

**Azure:**
- VM Size: `Standard_NC4as_T4_v3` (1x T4, 4 vCPU, 28GB RAM)
- Image: Ubuntu Server 22.04 LTS

### 2. Software Requirements

```bash
# Docker
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER

# NVIDIA Container Toolkit
distribution=$(. /etc/os-release;echo $ID$VERSION_ID)
curl -s -L https://nvidia.github.io/nvidia-docker/gpgkey | sudo apt-key add -
curl -s -L https://nvidia.github.io/nvidia-docker/$distribution/nvidia-docker.list | \
  sudo tee /etc/apt/sources.list.d/nvidia-docker.list

sudo apt-get update
sudo apt-get install -y nvidia-docker2
sudo systemctl restart docker

# Verify GPU access from Docker
docker run --rm --gpus all nvidia/cuda:12.0.0-base-ubuntu22.04 nvidia-smi
```

### 3. Download ONNX Models

```bash
# Create models directory
mkdir -p models

# Download all-MiniLM-L6-v2 ONNX model
# Option 1: From HuggingFace (requires transformers library)
python3 -c "
from optimum.onnxruntime import ORTModelForFeatureExtraction
from transformers import AutoTokenizer

model_id = 'sentence-transformers/all-MiniLM-L6-v2'
model = ORTModelForFeatureExtraction.from_pretrained(model_id, export=True)
tokenizer = AutoTokenizer.from_pretrained(model_id)

model.save_pretrained('models')
tokenizer.save_pretrained('models')
"

# Option 2: Download pre-converted ONNX
# (Add specific download URL when available)

# Verify model file
ls -lh models/all-MiniLM-L6-v2.onnx
```

## Build Process

### Option 1: Using Build Script (Recommended)

```bash
# Clone repository
git clone https://github.com/rom-mvp/vigil.git
cd vigil

# Run build script
./build-prod.sh

# Or with custom registry
IMAGE_NAME=vigil \
IMAGE_TAG=v1.0.0 \
REGISTRY=ghcr.io/rom-mvp \
./build-prod.sh
```

### Option 2: Manual Build

```bash
# Build Vigil image
docker build -f Dockerfile.prod -t vigil:latest .

# Tag for registry
docker tag vigil:latest ghcr.io/rom-mvp/vigil:latest

# Push to registry
docker push ghcr.io/rom-mvp/vigil:latest
```

## Deployment

### Method 1: Docker Run (Single Instance)

```bash
# Start Redis
docker run -d \
  --name vigil-redis \
  -p 6379:6379 \
  -v redis-data:/data \
  redis:7-alpine \
  redis-server --appendonly yes --requirepass changeme

# Start Vigil Gateway (GPU)
docker run -d \
  --name vigil-gateway \
  --gpus all \
  -p 8000:8000 \
  -e REDIS_URL=redis://:changeme@redis:6379/0 \
  -e AGENTSHIELD_URL=http://agentshield:9000 \
  -e VIGIL_ENVIRONMENT=production \
  -e VIGIL_FAIL_MODE=closed \
  -v $(pwd)/models:/app/models:ro \
  -v $(pwd)/logs:/app/logs \
  -v $(pwd)/data:/app/data:ro \
  --link vigil-redis:redis \
  --restart unless-stopped \
  vigil:latest
```

### Method 2: Docker Compose (Recommended)

```bash
# Create .env file
cat > .env << EOF
REDIS_PASSWORD=your_secure_redis_password
VAULT_ENCRYPTION_KEY=your_vault_encryption_key_32_bytes
ED25519_PRIVATE_KEY=your_ed25519_private_key_base64
ED25519_PUBLIC_KEY=your_ed25519_public_key_base64
DATABASE_URL=postgresql://user:pass@postgres:5432/agentshield
EOF

# Update docker-compose.prod.yml (use Vigil's Dockerfile.prod)
# See docker-compose.prod.yml in repository

# Start services
docker-compose -f docker-compose.prod.yml up -d

# View logs
docker-compose -f docker-compose.prod.yml logs -f vigil

# Check health
curl http://localhost:8000/health
curl http://localhost:9000/health
```

### Method 3: Kubernetes (Production Scale)

```yaml
# vigil-deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: vigil-gateway
spec:
  replicas: 3
  selector:
    matchLabels:
      app: vigil
  template:
    metadata:
      labels:
        app: vigil
    spec:
      containers:
      - name: vigil
        image: ghcr.io/rom-mvp/vigil:latest
        ports:
        - containerPort: 8000
        env:
        - name: REDIS_URL
          valueFrom:
            secretKeyRef:
              name: vigil-secrets
              key: redis-url
        - name: AGENTSHIELD_URL
          value: "http://agentshield-service:9000"
        - name: VIGIL_ENVIRONMENT
          value: "production"
        - name: VIGIL_FAIL_MODE
          value: "closed"
        resources:
          limits:
            nvidia.com/gpu: 1
            memory: "8Gi"
            cpu: "4"
          requests:
            nvidia.com/gpu: 1
            memory: "4Gi"
            cpu: "2"
        volumeMounts:
        - name: models
          mountPath: /app/models
          readOnly: true
        - name: logs
          mountPath: /app/logs
        livenessProbe:
          httpGet:
            path: /health
            port: 8000
          initialDelaySeconds: 40
          periodSeconds: 30
        readinessProbe:
          httpGet:
            path: /health
            port: 8000
          initialDelaySeconds: 20
          periodSeconds: 10
      volumes:
      - name: models
        persistentVolumeClaim:
          claimName: vigil-models-pvc
      - name: logs
        persistentVolumeClaim:
          claimName: vigil-logs-pvc
      nodeSelector:
        accelerator: nvidia-tesla-t4
---
apiVersion: v1
kind: Service
metadata:
  name: vigil-service
spec:
  type: LoadBalancer
  selector:
    app: vigil
  ports:
  - port: 80
    targetPort: 8000
```

## Configuration

### Environment Variables (Vigil)

```bash
# Redis
REDIS_URL=redis://:password@redis-host:6379/0

# AgentShield
AGENTSHIELD_URL=http://agentshield:9000
AGENTSHIELD_TIMEOUT_MS=3000
AGENTSHIELD_REQUIRED=true

# Vigil Behavior
VIGIL_ENVIRONMENT=production  # or 'development'
VIGIL_FAIL_MODE=closed        # or 'open'

# Vector Scanning
VECTOR_MODEL_PATH=/app/models/all-MiniLM-L6-v2.onnx
VECTOR_DB_PATH=/app/data/threat_vectors.jsonl

# Logging
APPEND_LOG_PATH=/app/logs/append_only.jsonl

# Security
REQUIRE_MTLS=false
MAX_REQUEST_BYTES=1048576
```

### Redis Schema Setup

```bash
# Create sample API key
redis-cli -a your_redis_password

# Add API key for tenant
HSET api_keys:vk_prod_abc123def456 \
  tenant_id "acme-corp" \
  tenant_name "Acme Corporation" \
  tier "enterprise" \
  status "active" \
  created_at "$(date +%s)"

# Verify
HGETALL api_keys:vk_prod_abc123def456
```

## Testing

### 1. Health Check

```bash
# Vigil health
curl http://localhost:8000/health

# Expected: {"status": "healthy"}
```

### 2. API Request

```bash
curl -X POST http://localhost:8000/chat/completions \
  -H "Authorization: Bearer vk_prod_abc123def456" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gpt-4",
    "messages": [
      {"role": "user", "content": "Hello, how are you?"}
    ]
  }'
```

### 3. Load Test

```bash
# Install Apache Bench
sudo apt-get install apache2-utils

# Run load test (100 requests, 10 concurrent)
ab -n 100 -c 10 \
  -H "Authorization: Bearer vk_prod_abc123def456" \
  -H "Content-Type: application/json" \
  -p request.json \
  http://localhost:8000/chat/completions
```

## Monitoring

### 1. GPU Usage

```bash
# Inside container
docker exec vigil-gateway nvidia-smi

# Watch GPU usage
watch -n 1 'docker exec vigil-gateway nvidia-smi'
```

### 2. Container Metrics

```bash
# Resource usage
docker stats vigil-gateway

# Logs
docker logs -f vigil-gateway --tail 100
```

### 3. Application Metrics

```bash
# Redis monitoring
redis-cli -a password INFO

# Check rate limits
redis-cli -a password ZCARD "rate_limit:acme-corp:rpm"

# Check token usage
redis-cli -a password GET "usage:acme-corp:daily:$(date +%Y-%m-%d)"

# Check billing queue
redis-cli -a password LLEN "billing:events"
```

## Scaling

### Horizontal Scaling (Multiple Vigil Instances)

```bash
# Docker Compose scale
docker-compose -f docker-compose.prod.yml up -d --scale vigil=3

# Add NGINX load balancer
# nginx.conf:
upstream vigil_backend {
    least_conn;
    server vigil-1:8000;
    server vigil-2:8000;
    server vigil-3:8000;
}

server {
    listen 80;
    location / {
        proxy_pass http://vigil_backend;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

### Regional Deployment

```
┌─────────────────────┐     ┌─────────────────────┐     ┌─────────────────────┐
│ US-EAST Vigil       │     │ US-WEST Vigil       │     │ EU-WEST Vigil       │
│ (g4dn.xlarge)       │     │ (g4dn.xlarge)       │     │ (g4dn.xlarge)       │
└──────────┬──────────┘     └──────────┬──────────┘     └──────────┬──────────┘
           │                           │                           │
           └───────────────────────────┴───────────────────────────┘
                                       │
                              ┌────────▼────────┐
                              │  AgentShield    │
                              │  (Central)      │
                              └─────────────────┘
```

## Troubleshooting

### GPU Not Detected

```bash
# Check NVIDIA drivers
nvidia-smi

# Check Docker GPU support
docker run --rm --gpus all nvidia/cuda:12.0.0-base-ubuntu22.04 nvidia-smi

# Check container GPU access
docker exec vigil-gateway nvidia-smi
```

### ONNX Runtime Errors

```bash
# Check ONNX providers
docker exec vigil-gateway python3 -c "
import onnxruntime as ort
print('Available providers:', ort.get_available_providers())
"

# Expected: ['CUDAExecutionProvider', 'CPUExecutionProvider']
```

### Redis Connection Issues

```bash
# Test Redis connection
redis-cli -h redis-host -p 6379 -a password PING

# Check from container
docker exec vigil-gateway redis-cli -h redis -p 6379 -a password PING
```

## Security Hardening

1. **TLS/HTTPS:** Use reverse proxy (nginx/caddy) with Let's Encrypt
2. **Redis Auth:** Enable `requirepass` in redis.conf
3. **Network Isolation:** Use Docker networks or VPC subnets
4. **API Key Rotation:** Implement key rotation policy
5. **Secrets Management:** Use AWS Secrets Manager / HashiCorp Vault
6. **Container Security:** Run as non-root user (already configured)
7. **Image Scanning:** Use Trivy/Snyk to scan for vulnerabilities

## Cost Optimization

### GPU Instance Costs (AWS)

| Instance      | GPU        | vCPU | RAM   | $/hour | $/month |
|---------------|------------|------|-------|--------|---------|
| g4dn.xlarge   | 1x T4      | 4    | 16GB  | $0.526 | $383    |
| g4dn.2xlarge  | 1x T4      | 8    | 32GB  | $0.752 | $549    |
| g5.xlarge     | 1x A10G    | 4    | 16GB  | $1.006 | $734    |

### Optimization Strategies

1. **Reserved Instances:** 40% savings with 1-year commitment
2. **Spot Instances:** 70% savings (use for non-critical edge locations)
3. **Auto-scaling:** Scale down during low traffic
4. **CPU Fallback:** Use cheaper CPU instances for low-load regions

## Support

- Documentation: `docs/SAAS_ARCHITECTURE.md`
- Issues: https://github.com/rom-mvp/vigil/issues
- API Reference: `docs/api_reference.md`
