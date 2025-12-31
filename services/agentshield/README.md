# AgentShield Service

Production-grade attestation verification service with AWS Nitro and Azure TDX support.

## Features

- **Real Attestation Verification**: Validates AWS Nitro and Azure TDX attestation documents
- **PCR Validation**: Checks measured PCR values against allowlist
- **Ed25519 Signing**: Cryptographically signs decisions
- **Health Checks**: Comprehensive health and status endpoints
- **Production Ready**: Gunicorn WSGI server, structured logging, error handling

## Environment Variables

- `APP_ENV`: Environment (dev/prod)
- `PORT`: Service port (default: 9000)
- `HARDWARE_BACKEND`: Attestation backend (aws_nitro/azure_tdx)
- `AWS_REGION`: AWS region for Nitro verification
- `REQUIRE_ATTESTATION`: Enforce attestation requirement (true/false)
- `REDIS_URL`: Redis connection string
- `DATABASE_URL`: PostgreSQL connection string
- `AGENTSHIELD_SIGNING_KEY_B64`: Base64-encoded Ed25519 signing key

## Endpoints

### Health & Status
- `GET /health` - Health check
- `GET /status` - Detailed status

### Attestation
- `POST /api/v1/verify-attestation` - Verify attestation document
- `GET /api/v1/enclave-info` - Get enclave information

### Signing
- `POST /api/v1/sign-decision` - Sign a decision

## Docker Build

```bash
docker build -f Dockerfile.prod -t agentshield:latest .
```

## Local Development

```bash
pip install -r requirements.txt
python app.py
```

## Production Deployment

```bash
gunicorn -w 4 -b 0.0.0.0:9000 app:app
```
