#!/usr/bin/env python3
"""
TEE Implementation Guide for Vigil

This document describes the production TEE (Trusted Execution Environment) implementation
integrated into Vigil Enhanced Gateway.

## Architecture Overview

Vigil now supports secure communication with AgentShield enclaves via:

1. **Attestation Client** (src/vigil/tee_attestation.py)
   - Generates platform-specific attestation quotes
   - Supports: SGX (DCAP), SEV-SNP, TDX, Azure CC
   - Measurements are cached and deterministic
   - Quote validation framework

2. **Key Sealing** (src/vigil/key_sealing.py)
   - Seals sensitive keys to platform measurements
   - Supports MRENCLAVE and MRSIGNER binding types
   - Mock implementation (AES-GCM ready for real SDKs)
   - Per-platform sealing variants

3. **vsock Transport** (src/vigil/vsock_transport.py)
   - Low-latency VM-to-enclave communication
   - Length-prefixed JSON message serialization
   - Connection pooling and retry logic
   - Fallback to HTTP if vsock unavailable

4. **Integration Layer** (src/vigil/tee_integration.py)
   - Orchestrates attestation, sealing, and transport
   - Caches quotes for performance (1-hour TTL)
   - Global singleton for application-wide access
   - Configuration from environment variables

5. **Enhanced Server** (vigil_enhanced_server.py)
   - Initializes TEE on startup
   - Exposes /api/attestation/* endpoints
   - Includes attestation quote in decision requests
   - Health check reports TEE status

## Environment Configuration

### Basic TEE Setup

```bash
# Enable TEE features
export VIGIL_TEE_ENABLED=true

# Auto-detect platform (tries SGX -> SEV -> TDX -> Azure)
export VIGIL_TEE_TYPE=auto

# Or specify platform explicitly
export VIGIL_TEE_TYPE=sgx      # Intel SGX
export VIGIL_TEE_TYPE=sev      # AMD SEV-SNP
export VIGIL_TEE_TYPE=tdx      # Intel TDX
export VIGIL_TEE_TYPE=azure    # Azure Confidential Compute
```

### Key Sealing Configuration

```bash
# Binding type (affects unsealing requirements)
export VIGIL_KEY_SEALING_TYPE=mrenclave   # Strict: exact enclave measurement
export VIGIL_KEY_SEALING_TYPE=mrsigner    # Flexible: signer identity (allows updates)

# Optional: Custom sealing seed (for testing/reproducibility)
export VIGIL_KEY_SEALING_SEED="my-custom-seed"

# Optional: Measurement policy file (allow-list of trusted measurements)
export VIGIL_TEE_MEASUREMENT_POLICY_FILE=/app/measurements.json
```

### AgentShield Communication

```bash
# Transport mode
export AGENTSHIELD_MODE=http        # Standard HTTP/HTTPS
export AGENTSHIELD_MODE=vsock       # VM-to-enclave vsock (low-latency)

# vsock configuration (only used when AGENTSHIELD_MODE=vsock)
export AGENTSHIELD_VSOCK_CID=3      # Enclave CID (3 = host-to-guest)
export AGENTSHIELD_VSOCK_PORT=5555  # Enclave listening port
export AGENTSHIELD_TIMEOUT_MS=1000  # Request timeout
```

## API Endpoints

### GET /health
Returns server health including TEE status.

Response:
```json
{
  "status": "healthy",
  "service": "vigil-enhanced-gateway",
  "components": {
    "redis": true,
    "tee_enabled": true,
    "attestation": true
  },
  "tee_type": "sgx"
}
```

### GET /api/attestation/quote
Get TEE attestation quote for external verification.

Requires: Valid API key in Authorization header

Query Parameters:
- `refresh=true` : Force fresh quote generation (bypass cache)

Response:
```json
{
  "type": "sgx",
  "instance_id": "12345678-abcd-ef01-2345-6789abcdef01",
  "timestamp": "2024-01-15T10:30:00Z",
  "quote": "base64-encoded-quote-blob",
  "signature": "base64-encoded-signature",
  "mrenclave": "0123456789abcdef...",
  "mrsigner": "fedcba9876543210...",
  ...
}
```

### POST /api/attestation/verify
Verify that current measurements match the local policy allow-list.

Requires: Valid API key in Authorization header

Response:
```json
{
  "valid": true,
  "timestamp": "2024-01-15T10:30:00Z"
}
```

### POST /v1/chat/completions
Main decision endpoint (existing).

Now includes attestation quote in response metadata:
```json
{
  ...existing response...,
  "vigil_metadata": {
    "risk_score": 0.15,
    "security_layers": 9,
    "tee_enabled": true,
    "attestation_quote": {
      "type": "sgx",
      "instance_id": "...",
      "timestamp": "...",
      ...
    }
  }
}
```

## Measurement Policy File

Create `/app/measurements.json` to specify trusted enclave measurements:

```json
{
  "sgx": {
    "allowed_mrenclaves": [
      "1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef",
      "fedcba9876543210fedcba9876543210fedcba9876543210fedcba9876543210"
    ],
    "allowed_mrsigners": [
      "aabbccddeeff00112233445566778899aabbccddeeff00112233445566778899"
    ]
  },
  "sev": {
    "allowed_measurements": [
      "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
    ]
  },
  "tdx": {
    "allowed_mrtds": [
      "fedcba9876543210fedcba9876543210fedcba9876543210fedcba9876543210"
    ]
  },
  "azure": {
    "allowed_vm_ids": [
      "my-app-vm-prod-001"
    ]
  }
}
```

If no policy file exists, all measurements are accepted (INSECURE - enable for testing only).

## Integration with AgentShield

### Request Flow (HTTP Mode)

```
Vigil Client
  |
  +-> GET /api/attestation/quote
  |     +-> Generates SGX/SEV/TDX/Azure quote
  |     +-> Returns quote blob + signature
  |
  +-> POST /v1/chat/completions
        +-> Includes attestation quote in _attestation field
        +-> AgentShield verifies quote signature
        +-> AgentShield checks measurements vs policy
        +-> AgentShield makes decision + signs it
        +-> Returns signed decision to Vigil
```

### Request Flow (vsock Mode)

```
Vigil Client (vigil_enhanced_server.py)
  |
  +-> Initialize TEEIntegration (TEE_ENABLED=true, AGENTSHIELD_MODE=vsock)
  |
  +-> VsockTransport connects to enclave (CID:PORT)
  |
  +-> Send attestation quote
        +-> Enclave verifies quote
        +-> Enclave responds with sealed keys / capabilities
  |
  +-> Relay policy decisions via vsock
```

## Implementation Details by Platform

### Intel SGX (DCAP/EPID)

**Quote Fields:**
- version: 3 (DCAP)
- sign_type: 0 (EPID) or 2 (ECDSA)
- mr_enclave: SHA256(enclave code) - 32 bytes
- mr_signer: SHA256(key used to sign enclave) - 32 bytes
- report_data: Hash of nonce (prevents replay)
- tcb_evaluation_flags: Security advisory status
- cpusvn: CPU security version

**Sealing:** sgx_seal_data() to MRENCLAVE or MRSIGNER

### AMD SEV-SNP

**Report Fields:**
- version: 2
- guest_svn: Guest security version
- policy: Policy bits (SMT, debug, etc.)
- measurement: SHA384(guest code) - 48 bytes
- host_data: Guest-supplied data
- id_key_digest: Platform attestation key
- author_key_digest: Optional author key

**Sealing:** SVSM sealed storage APIs

### Intel TDX

**Quote Fields:**
- mrtd: SHA384(TD measurement) - 48 bytes
- rtmr0-3: Runtime measurement registers (4 × 48 bytes)
- mr_td: Encrypted TD measurement
- mr_owner: Owner measurement
- tdx_svn: TD security version
- xfam: Extended feature access mask

**Sealing:** TD-shim sealed storage

### Azure Confidential Compute

**Token Fields:**
- tee: "sev-snp"
- vm_id: Azure VM resource ID
- vm_size: VM SKU
- location: Region
- policy: SEV policy bits
- measurement: SEV measurement
- timestamp: ISO8601 timestamp

**Sealing:** Azure Managed HSM with Key Vault

## Testing

### Run Integration Tests

```bash
cd /workspaces/vigil
python test_tee_integration.py
```

Expected output:
```
✓ PASS: TEE Attestation
✓ PASS: Key Sealing
✓ PASS: TEE Integration
✓ PASS: Mock AgentShield Enclave

Total: 4/4 tests passed
```

### Manual Testing with curl

```bash
# 1. Get API key
API_KEY=$(cat api_keys.json | jq -r '.keys[0].key')

# 2. Get health status
curl -s http://localhost:8000/health | jq .

# 3. Get attestation quote
curl -s -H "Authorization: Bearer $API_KEY" \
  http://localhost:8000/api/attestation/quote | jq .

# 4. Verify measurements
curl -s -X POST -H "Authorization: Bearer $API_KEY" \
  http://localhost:8000/api/attestation/verify | jq .

# 5. Send decision request with attestation
curl -s -X POST -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [
      {"role": "user", "content": "What is 2+2?"}
    ]
  }' \
  http://localhost:8000/v1/chat/completions | jq '.vigil_metadata.attestation_quote'
```

## Production Deployment

### SGX Host

```bash
# Enable SGX in BIOS
# Install SGX driver: https://github.com/intel/linux-sgx-driver

# Run Vigil in SGX-enabled container
docker build -f Dockerfile.sgx -t vigil:sgx .
docker run --device=/dev/isgx \
  -e VIGIL_TEE_ENABLED=true \
  -e VIGIL_TEE_TYPE=sgx \
  vigil:sgx
```

### SEV-SNP VM (Azure)

```bash
# Create SEV-SNP enabled VM (Standard_D4pds_v5 or later)
# Ubuntu 22.04 LTS with SEV-SNP enabled

# Install attestation client
apt-get install -y snphost

# Run Vigil
export VIGIL_TEE_ENABLED=true
export VIGIL_TEE_TYPE=sev
python vigil_enhanced_server.py
```

### TDX VM (Intel)

```bash
# Create TDX-enabled VM (Intel Xeon Scalable 4th Gen)
# Ubuntu 24.04 LTS with TDX support

# Install TDX tools
apt-get install -y tdx-tools

# Run Vigil
export VIGIL_TEE_ENABLED=true
export VIGIL_TEE_TYPE=tdx
python vigil_enhanced_server.py
```

### Azure Confidential Containers

```bash
# Create confidential container group
az container create \
  --resource-group myResourceGroup \
  --name vigil-cc \
  --image vigil:latest \
  --environment-variables \
    VIGIL_TEE_ENABLED=true \
    VIGIL_TEE_TYPE=azure \
    AGENTSHIELD_MODE=http \
  --secure-environment-variables \
    AGENTSHIELD_API_KEY="$AGENTSHIELD_KEY"
```

## Future Enhancements

### Real SDK Integration

Once platform SDKs available:
1. Replace mock quote generation with real SDK calls
2. Implement real key sealing (currently mock AES-GCM)
3. Add real measurement generation from enclave state
4. Integrate with SGX DCAP/EPID, SEV-SNP PSP, TDX, Azure Attestation Service

### Measurement Rollover

1. Pre-generate new measurements during enclave update
2. Allow both old and new measurements in policy
3. Automated policy update via secure channel

### Hardware-Backed Secrets

1. Seal AgentShield API keys to enclave measurement
2. Release keys only when measurements verify
3. Support for TPM-backed key storage

### Nested Attestation

1. Vigil attests to AgentShield
2. AgentShield attests to Vigil (mutual authentication)
3. End-to-end encrypted channel

## Security Considerations

### Measurement Stability

- Measurements must be deterministic across container restarts
- Use /tmp/vigil_measurements.json for caching
- Include instance_id to allow multiple instances
- Regenerate on new container start

### Quote Freshness

- Quotes cached for 1 hour by default
- Nonce regenerated per quote to prevent replay
- AgentShield should validate timestamp within policy window (e.g., 5 minutes)

### Measurement Policy

- Store in read-only volume (/app/measurements.json)
- Sign policy file for integrity verification
- Rotate periodically as enclaves update
- Maintain allow-list of acceptable measurements

### Transport Security

- vsock inherits VM isolation guarantees
- HTTP mode should use mTLS with AgentShield CA
- Quote signature must be verified by AgentShield
- Protect API keys in sealed storage

## Troubleshooting

### "TEE disabled" message

```bash
# Check environment variable
echo $VIGIL_TEE_ENABLED

# Should be "true"
export VIGIL_TEE_ENABLED=true
```

### "vsock not available on this platform"

```bash
# Check if AF_VSOCK is supported
python -c "import socket; socket.socket(socket.AF_VSOCK, socket.SOCK_STREAM)"

# If error: only available on Linux with vhost-vsock kernel module
# On Windows/Mac, fall back to HTTP mode:
export AGENTSHIELD_MODE=http
```

### "No measurement policy found"

```bash
# Create allow-list policy
mkdir -p /app
cat > /app/measurements.json << 'EOF'
{
  "sgx": {"allowed_mrenclaves": []},
  "sev": {"allowed_measurements": []},
  "tdx": {"allowed_mrtds": []},
  "azure": {"allowed_vm_ids": []}
}
EOF
```

### Quote validation errors

```bash
# Check quote structure
curl -s -H "Authorization: Bearer $API_KEY" \
  http://localhost:8000/api/attestation/quote | jq '.' | head -20

# Verify nonce is base64-encoded
# Verify timestamp is ISO8601
# Verify platform-specific fields are present
```

## References

- Intel SGX: https://software.intel.com/en-us/sgx/documentation
- AMD SEV: https://developer.amd.com/sev/
- Intel TDX: https://www.intel.com/content/www/us/en/developer/articles/technical/intel-trust-domain-extensions.html
- Azure CC: https://azure.microsoft.com/en-us/products/azure-confidential-computing/
- Vigil Repository: https://github.com/example/vigil
- AgentShield Repository: https://github.com/example/agentshield
"""

# This is a documentation module - no executable code
if __name__ == "__main__":
    # Extract and print docstring as formatted guide
    import sys
    doc = __doc__
    if doc:
        print(doc)
    else:
        print("No documentation available")
        sys.exit(1)
