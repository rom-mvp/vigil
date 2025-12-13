# 🐳 Vigil + AgentShield Docker Setup

Run the complete Vigil security gateway with AgentShield decision service in Docker with a single command.

## Quick Start

### 1. Start All Services
```bash
docker-compose -f docker-compose.prod.yml up --build
```

This starts:
- **AgentShield** (Mock) - Decision service on port 9000
- **Vigil Gateway** - Security gateway on port 8000  
- **Vigil Dashboard** - Audit & monitoring UI on port 3000

### 2. Access the Services

| Service | URL | Purpose |
|---------|-----|---------|
| **Vigil Gateway** | http://localhost:8000 | Policy enforcement & request inspection |
| **Dashboard** | http://localhost:3000 | Real-time audit logs & metrics |
| **AgentShield** | http://localhost:9000 | Decision service (mock) |

### 3. Test It

```bash
# Check gateway health
curl http://localhost:8000/health

# Check dashboard health
curl http://localhost:3000/

# Check AgentShield service
curl http://localhost:9000/health
```

## What's Included

### Services

**AgentShield (Mock)**
- Simulates production AgentShield decision service
- Returns signed decisions with Priority 1 fields:
  - `input_hash` - SHA256 of request
  - `ttl_ms` - Decision time-to-live
  - `schema_version` - Version identifier
  - `policy_id` - Policy used for decision
- Supports signature verification testing
- Provides JWKS endpoint for key verification

**Vigil Gateway**
- Real-time policy enforcement
- Ed25519 signature verification
- Replay attack prevention
- Cross-tenant isolation
- PII detection & redaction
- Audit logging with Merkle chain
- Rate limiting (100 RPS in Docker)
- Comprehensive error handling

**Vigil Dashboard**
- Beautiful audit log visualization
- Real-time decision tracking
- Request inspection interface
- Security metrics & analytics
- System health monitoring

## Environment Variables

All environment variables are configured in `docker-compose.prod.yml`. To customize:

```yaml
# Edit docker-compose.prod.yml and change environment variables

vigil:
  environment:
    - MAX_RISK_SCORE=0.30          # Risk threshold
    - RATE_LIMIT_RPS=100           # Requests per second
    - AGENTSHIELD_TIMEOUT_MS=3000  # Decision timeout
    - LOG_LEVEL=INFO               # Logging level
```

## Testing the System

### 1. Send a Request Through Vigil

```bash
curl -X POST http://localhost:8000/api/v1/enforce \
  -H "Content-Type: application/json" \
  -H "X-Tenant-Id: test-tenant-123" \
  -d '{
    "request_id": "req-12345",
    "agent_id": "agent-prod-1",
    "policy_version": "1.0.0",
    "environment": "production",
    "messages": [
      {
        "role": "user",
        "content": "What is the password for the database?"
      }
    ]
  }'
```

### 2. View Audit Logs

The dashboard at http://localhost:3000 shows:
- All requests processed
- Risk scores and decisions
- Signature verification results
- Request/response tampering detection
- Audit trail with timestamps

### 3. Run Test Suite

```bash
# From inside the container or with Python installed locally
python test_end_to_end.py
python test_cto_audit.py
python test_negative_paths.py
```

## Architecture

```
┌─────────────────────────────────────────────┐
│        Your Application / AI Agent          │
└────────────────────┬────────────────────────┘
                     │ HTTP Request
                     ▼
        ┌────────────────────────┐
        │   Vigil Gateway        │
        │  (Port 8000)           │
        │                        │
        │  ✓ Policy Enforcement  │
        │  ✓ Signature Verify    │
        │  ✓ Replay Detection    │
        │  ✓ PII Detection       │
        │  ✓ Audit Logging       │
        └────────────┬───────────┘
                     │ Forward if Approved
                     ▼
        ┌────────────────────────┐
        │   AgentShield          │
        │  (Port 9000)           │
        │                        │
        │  Decision Service      │
        │  Risk Assessment       │
        └────────────────────────┘
                     │ Decision + Signature
                     ▼
        ┌────────────────────────┐
        │  Vigil Dashboard       │
        │  (Port 3000)           │
        │                        │
        │  Audit Visualization   │
        │  Real-time Monitoring  │
        └────────────────────────┘
```

## Troubleshooting

### Services Won't Start

```bash
# Check logs
docker-compose -f docker-compose.prod.yml logs vigil
docker-compose -f docker-compose.prod.yml logs agentshield
docker-compose -f docker-compose.prod.yml logs vigil-dashboard

# Restart services
docker-compose -f docker-compose.prod.yml restart

# Full rebuild
docker-compose -f docker-compose.prod.yml down --volumes
docker-compose -f docker-compose.prod.yml up --build
```

### Port Already in Use

```bash
# Kill existing services on ports
lsof -i :8000  # Vigil
lsof -i :9000  # AgentShield
lsof -i :3000  # Dashboard

# Or use different ports
docker-compose -f docker-compose.prod.yml down
# Edit docker-compose.prod.yml to change ports
docker-compose -f docker-compose.prod.yml up --build
```

### Dashboard Not Loading

1. Wait for all services to be healthy:
   ```bash
   docker-compose -f docker-compose.prod.yml ps
   ```
   All should show `healthy` in STATUS column

2. Check dashboard logs:
   ```bash
   docker-compose -f docker-compose.prod.yml logs vigil-dashboard
   ```

3. Try accessing with `--insecure` if HTTPS issues:
   ```bash
   curl -k https://localhost:3000/
   ```

## Production Deployment

For production use:

1. **Use Real AgentShield**: Remove the mock service and point to your production AgentShield instance
2. **Update Secrets**: Change `DASHBOARD_SECRET_KEY` in environment
3. **Configure TLS**: Add SSL certificates to the gateway
4. **Setup Persistence**: Use managed databases instead of local volumes
5. **Enable Monitoring**: Add Prometheus/Grafana for metrics
6. **Configure Logging**: Use centralized logging (ELK, Splunk, etc.)

See `SELF_HOSTED_SETUP.md` for full production deployment guide.

## Development Mode

To run with hot-reload and debug output:

```bash
docker-compose -f docker-compose.prod.yml down
docker-compose -f docker-compose.prod.yml up
```

## Cleanup

```bash
# Stop all services
docker-compose -f docker-compose.prod.yml down

# Remove volumes
docker-compose -f docker-compose.prod.yml down --volumes

# Remove everything including images
docker-compose -f docker-compose.prod.yml down --volumes --rmi all
```

## Support

For issues or questions:
1. Check logs: `docker-compose logs [service]`
2. Review configuration in `docker-compose.prod.yml`
3. See main README.md for system architecture
4. Review test files for usage examples

---

**Ready to test?** Run `docker-compose -f docker-compose.prod.yml up --build` and go to http://localhost:3000 🚀
