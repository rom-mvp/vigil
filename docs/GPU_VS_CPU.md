# 🔀 Vigil Deployment Modes: GPU vs CPU

## Overview

Vigil Gateway supports **two deployment modes** to balance performance, cost, and developer experience:

| Mode | Use Case | Performance | Cost | Requirements |
|------|----------|-------------|------|--------------|
| **GPU** | Production (high traffic) | ~5-10ms/req | $0.50-1.00/hr | NVIDIA GPU, CUDA 12.0 |
| **CPU** | Dev/Staging/Low traffic | ~50-100ms/req | $0.05-0.10/hr | Any Linux/Mac/Windows |

## When to Use Each Mode

### ✅ Use CPU Mode (Dockerfile.cpu) When:
- **Local Development**: Running on MacBook (M1/M2/M3) or Windows laptop
- **Early Stage**: Pre-product-market-fit, <100 RPS traffic
- **Cost Optimization**: Budget constraints, non-critical environments
- **Staging/QA**: Testing environments with low load
- **Low Traffic Production**: <100 requests per second

### ✅ Use GPU Mode (Dockerfile.prod) When:
- **High Traffic Production**: >1000 requests per second
- **Low Latency Critical**: <10ms vector scanning required
- **Large Scale**: Multi-tenant SaaS with thousands of concurrent users
- **Cost-Effective at Scale**: GPU amortizes at high throughput

## Performance Comparison

### CPU Mode (Dockerfile.cpu)
```
Hardware: 4-core CPU, 8GB RAM
Vector Scan: ~50-100ms per request
Throughput: ~20-50 RPS per instance
Cost: $0.05-0.10/hour (AWS t3.large, GCP n1-standard-4)

Example Latency Breakdown:
- Network: 5ms
- Authentication: 2ms
- Vector Scan (CPU): 80ms  ← Bottleneck
- PII Detection: 10ms
- Firewall: 3ms
- Total: ~100ms
```

### GPU Mode (Dockerfile.prod)
```
Hardware: 1x NVIDIA T4 GPU, 4-core CPU, 16GB RAM
Vector Scan: ~5-10ms per request (CUDA acceleration)
Throughput: ~200-500 RPS per instance
Cost: $0.50-1.00/hour (AWS g4dn.xlarge, GCP n1-standard-4 + T4)

Example Latency Breakdown:
- Network: 5ms
- Authentication: 2ms
- Vector Scan (GPU): 8ms   ← 10x faster
- PII Detection: 10ms
- Firewall: 3ms
- Total: ~28ms
```

## Quick Start

### CPU Mode (Developer Setup)

```bash
# 1. Build CPU image
./build-cpu.sh

# 2. Run locally (works on any machine)
docker run -p 8000:8000 \
  -e REDIS_URL=redis://localhost:6379/0 \
  -e AGENTSHIELD_URL=http://localhost:9000 \
  -e VIGIL_DEVICE_MODE=cpu \
  vigil:cpu

# 3. Test
curl http://localhost:8000/health
```

### GPU Mode (Production Setup)

```bash
# 1. Build GPU image (requires nvidia-docker2)
./build-prod.sh

# 2. Run on GPU instance
docker run --gpus all -p 8000:8000 \
  -e REDIS_URL=redis://redis:6379/0 \
  -e AGENTSHIELD_URL=http://agentshield:9000 \
  -e VIGIL_DEVICE_MODE=gpu \
  vigil:latest

# 3. Verify GPU usage
docker exec vigil nvidia-smi
```

## Docker Images

### Dockerfile.cpu
```dockerfile
# Base: python:3.11-slim (no CUDA)
# ONNX: onnxruntime (CPU-only)
# Size: ~800MB
# Works: Mac M1/M2, Windows, Linux (any CPU)
# ENV: VIGIL_DEVICE_MODE=cpu
```

### Dockerfile.prod
```dockerfile
# Base: nvidia/cuda:12.0.0-runtime-ubuntu22.04
# ONNX: onnxruntime-gpu (CUDA acceleration)
# Size: ~3GB
# Works: Linux with NVIDIA GPU + nvidia-docker2
# ENV: VIGIL_DEVICE_MODE=gpu
```

## Environment Variable: VIGIL_DEVICE_MODE

The `VIGIL_DEVICE_MODE` environment variable controls which ONNX Runtime execution provider is used:

| Value | Behavior | Use Case |
|-------|----------|----------|
| `cpu` | Force CPU-only execution | Mac/Windows dev, cheap servers |
| `gpu` | Force CUDA GPU execution | Production with GPU |
| `auto` | Try GPU, fallback to CPU | Flexible deployment (default) |

### Code Implementation

```python
# src/vigil/vector_engine.py

device_mode = os.environ.get("VIGIL_DEVICE_MODE", "auto").lower()

if device_mode == "cpu":
    providers = ['CPUExecutionProvider']  # CPU-only
elif device_mode == "gpu":
    providers = ['CUDAExecutionProvider']  # GPU-only (fail if no GPU)
else:
    providers = ['CUDAExecutionProvider', 'CPUExecutionProvider']  # Auto
```

## Docker Compose Examples

### docker-compose.dev.yml (CPU Mode)
```yaml
version: '3.8'
services:
  vigil:
    image: vigil:cpu
    build:
      context: .
      dockerfile: Dockerfile.cpu
    ports:
      - "8000:8000"
    environment:
      VIGIL_DEVICE_MODE: cpu
      REDIS_URL: redis://redis:6379/0
      AGENTSHIELD_URL: http://agentshield:9000
    depends_on:
      - redis
      - agentshield
  
  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
  
  agentshield:
    image: agentshield:latest
    ports:
      - "9000:9000"
```

### docker-compose.prod.yml (GPU Mode)
```yaml
version: '3.8'
services:
  vigil:
    image: vigil:latest
    build:
      context: .
      dockerfile: Dockerfile.prod
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]
    ports:
      - "8000:8000"
    environment:
      VIGIL_DEVICE_MODE: gpu
      REDIS_URL: redis://redis:6379/0
      AGENTSHIELD_URL: http://agentshield:9000
    depends_on:
      - redis
      - agentshield
  
  redis:
    image: redis:7-alpine
    command: redis-server --requirepass ${REDIS_PASSWORD}
  
  agentshield:
    image: agentshield:latest
    environment:
      VAULT_ENCRYPTION_KEY: ${VAULT_ENCRYPTION_KEY}
```

## Cloud Provider Recommendations

### AWS
| Mode | Instance Type | vCPU | RAM | GPU | $/hour | Use Case |
|------|---------------|------|-----|-----|--------|----------|
| CPU | t3.large | 2 | 8GB | - | $0.08 | Dev/Staging |
| CPU | c6i.2xlarge | 8 | 16GB | - | $0.34 | Low-traffic prod |
| GPU | g4dn.xlarge | 4 | 16GB | 1x T4 | $0.53 | High-traffic prod |
| GPU | g5.xlarge | 4 | 16GB | 1x A10G | $1.01 | Ultra-low latency |

### GCP
| Mode | Machine Type | vCPU | RAM | GPU | $/hour | Use Case |
|------|--------------|------|-----|-----|--------|----------|
| CPU | n1-standard-2 | 2 | 7.5GB | - | $0.10 | Dev/Staging |
| CPU | n2-standard-4 | 4 | 16GB | - | $0.19 | Low-traffic prod |
| GPU | n1-standard-4 + T4 | 4 | 15GB | 1x T4 | $0.47 | High-traffic prod |

### Azure
| Mode | VM Size | vCPU | RAM | GPU | $/hour | Use Case |
|------|---------|------|-----|-----|--------|----------|
| CPU | D2s_v3 | 2 | 8GB | - | $0.10 | Dev/Staging |
| CPU | D4s_v3 | 4 | 16GB | - | $0.19 | Low-traffic prod |
| GPU | NC4as_T4_v3 | 4 | 28GB | 1x T4 | $0.53 | High-traffic prod |

## Migration Path: CPU → GPU

### Phase 1: Start with CPU (Month 1-3)
```bash
# Cheap, fast iteration
# Deploy on t3.large ($0.08/hr)
# Total cost: ~$60/month
./build-cpu.sh
docker-compose -f docker-compose.dev.yml up -d
```

### Phase 2: Add GPU for Hot Path (Month 4-6)
```bash
# Keep CPU for staging
# Add GPU for production traffic
# Deploy GPU on g4dn.xlarge ($0.53/hr)
# Total cost: ~$380/month production + $60/month staging
./build-prod.sh
# Deploy GPU to production, CPU to staging
```

### Phase 3: Scale GPU Horizontally (Month 7+)
```bash
# Multiple GPU instances for high traffic
# 3x g4dn.xlarge behind load balancer
# Total cost: ~$1,140/month (handles 1000+ RPS)
docker-compose -f docker-compose.prod.yml up -d --scale vigil=3
```

## Cost Calculator

### Example: 1 Million Requests/Month

#### CPU-Only Deployment
```
Traffic: 1M requests/month ≈ 0.38 RPS average
Instance: 1x t3.large (CPU)
Capacity: ~50 RPS per instance
Cost: $60/month (1 instance * $0.08/hr * 730hr)
Latency: ~100ms per request
```

#### GPU Deployment (Over-provisioned for Low Traffic)
```
Traffic: 1M requests/month ≈ 0.38 RPS average
Instance: 1x g4dn.xlarge (GPU) - OVERKILL
Capacity: ~500 RPS per instance (99% idle!)
Cost: $387/month (1 instance * $0.53/hr * 730hr)
Latency: ~10ms per request
```

**Verdict:** Use CPU mode for <10 RPS average traffic

### Example: 100 Million Requests/Month

#### CPU-Only Deployment
```
Traffic: 100M requests/month ≈ 38 RPS average
Instances: 2x c6i.2xlarge (CPU) for redundancy
Capacity: ~100 RPS (2 instances * 50 RPS)
Cost: $496/month (2 * $0.34/hr * 730hr)
Latency: ~100ms per request
```

#### GPU Deployment
```
Traffic: 100M requests/month ≈ 38 RPS average
Instances: 1x g4dn.xlarge (GPU) - 8% utilization
Capacity: ~500 RPS per instance
Cost: $387/month (1 instance * $0.53/hr * 730hr)
Latency: ~10ms per request
```

**Verdict:** GPU becomes cost-effective at ~30+ RPS average traffic (when factoring in latency)

## Monitoring

### CPU Mode Metrics
```bash
# Check CPU usage
docker stats vigil-cpu

# Expected: 60-80% CPU during load
# Memory: 1-2GB
# No GPU metrics
```

### GPU Mode Metrics
```bash
# Check GPU usage
docker exec vigil-gpu nvidia-smi

# Expected: 30-60% GPU utilization
# VRAM: 1-3GB
# CPU: 20-40% (preprocessing)
```

## Troubleshooting

### CPU Mode: Slow Performance
```bash
# Check if accidentally using GPU image
docker inspect vigil-cpu | grep VIGIL_DEVICE_MODE
# Should show: VIGIL_DEVICE_MODE=cpu

# Increase workers
docker run -e GUNICORN_WORKERS=8 vigil:cpu

# Scale horizontally
docker-compose up -d --scale vigil=3
```

### GPU Mode: GPU Not Detected
```bash
# Check nvidia-docker2 installed
docker run --rm --gpus all nvidia/cuda:12.0.0-base nvidia-smi

# Check VIGIL_DEVICE_MODE
docker exec vigil-gpu printenv | grep VIGIL_DEVICE_MODE
# Should show: VIGIL_DEVICE_MODE=gpu

# Check ONNX providers
docker exec vigil-gpu python3 -c "import onnxruntime as ort; print(ort.get_available_providers())"
# Should show: ['CUDAExecutionProvider', 'CPUExecutionProvider']
```

## Summary

| Scenario | Recommendation |
|----------|----------------|
| MacBook Developer | CPU mode (Dockerfile.cpu) |
| Windows Developer | CPU mode (Dockerfile.cpu) |
| Staging Environment | CPU mode (docker-compose.dev.yml) |
| Production <100 RPS | CPU mode (t3.large or c6i.2xlarge) |
| Production >100 RPS | GPU mode (g4dn.xlarge) |
| Production >1000 RPS | GPU mode + horizontal scaling (3x g4dn.xlarge) |
| Budget Constrained | CPU mode (acceptable latency trade-off) |
| Latency Critical | GPU mode (10x faster vector scanning) |

**Key Insight:** Start with CPU mode for fast iteration and low cost. Migrate to GPU mode when traffic justifies the premium (~30+ RPS break-even point).
