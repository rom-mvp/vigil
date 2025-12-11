# Vigil Hardening Roadmap (CTO Requirements)

This document maps CTO requirements to concrete implementation steps in Vigil. It outlines immediate code changes and infrastructure guidance.

## Egress Hardening
- Cluster egress policy: Restrict outbound traffic to LLM domains via sidecar namespace/IPs only.
- DNS rewrite: Force `openai.com` and other LLM endpoints to resolve to internal Vigil/NLB proxy.
- Fail-closed: Sidecar attempts to bypass proxy are blocked (iptables/egress deny).

Action:
- Kubernetes: NetworkPolicy + egress gateway; CoreDNS rewrite to internal proxy.
- Docker Compose: Add `VIGIL_FAIL_CLOSED=true` toggle (future use).

## mTLS Everywhere
- Client certs required between sidecar ↔ NLB/Vigil.
- Enforce mutual TLS; no cert → no access.

Action:
- Nginx/Gateway: Configure TLS termination with client CA; add cert validation stubs in Vigil.

## Image/Signing Integrity
- Cosign/Notary signing for sidecar images.
- Admission controller verifies signatures/attestations.
- Treat attestations as short-lived, verified per-connection.

Action:
- CI/CD: Sign images; Gatekeeper/Kyverno policies; store signer metadata.

## Key Lifecycle
- Bind keys to attested measurements; rotate/expire; reject old versions.
- Policy-signing keys in HSM/KMS with multi-party approval.

Action:
- Add `KEY_VERSION`, `MEASUREMENT_ID` headers; enforce rotation windows.

## Policy Controls
- Explicit versioning/expiry/monotonic counters.
- Enclave rejects older versions once higher seen.
- Support simulation (dry-run) and rollback tracking.

Action:
- Implement `policy_version` checks and dry-run mode in gateway.

## Logging Guarantees
- Monotonic sequence numbers + heartbeat logs; external monitor alerts on gaps.
- Tamper-evident append-only store (object storage + Merkle digests).

Action:
- Add `seq_id` increment and `/api/heartbeat`; compute Merkle digest chain for batches.

## Workload Handling
- Early size limits; per-tenant/API-key rate limits in sidecar/NLB.
- Back-pressure/priority queues; CPU-only or enclave-compatible first-pass models.
- Secrets stay out of sidecar; minimize surface.

Action:
- Implement size limits and rate limiting in `local_server.py`.

## GPU/TEE Posture
- If GPUs: require attested confidential-GPU measurements; verify host cannot read VRAM.
- Else: keep sensitive plaintext inside enclave; send only privacy-preserving features.

Action:
- Enforce `GPU_ATTESTED=true` requirement for GPU mode (future).

## Runtime Hardening
- seccomp/AppArmor; disable shell tools; minimal sidecar feature surface.
- Adversarial testing and multi-model/rule-based backups for ML scoring.
- CI/CD locked down with image signing.

Action:
- Provide Docker profiles and CI checks; expand Firewall rules.

---

## Immediate Code Changes (Phase 1)
1. Request size limit (`MAX_REQUEST_BYTES`) and content length checks.
2. Per-API-key token bucket rate limiting.
3. Monotonic log sequence IDs + `/api/heartbeat` endpoint.
4. Policy version headers with strict monotonic enforcement.
5. mTLS/cert check stub: enforce presence of `X-Client-Cert` when `REQUIRE_MTLS=true`.
