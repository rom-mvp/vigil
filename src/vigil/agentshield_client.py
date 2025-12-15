import base64
import hashlib
import json
import os
import threading
import time
from collections import defaultdict, OrderedDict
from enum import Enum
from typing import Any, Dict, Optional

import requests

try:
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding, ed25519, rsa
    from cryptography.hazmat.primitives.serialization import load_pem_public_key
    _CRYPTO_AVAILABLE = True
except ImportError:
    _CRYPTO_AVAILABLE = False


class VigilErrorCode(str, Enum):
    """Error taxonomy for structured error handling."""
    AGENTSHIELD_TIMEOUT = "AGENTSHIELD_TIMEOUT"
    AGENTSHIELD_UNREACHABLE = "AGENTSHIELD_UNREACHABLE"
    DECISION_SCHEMA_INVALID = "DECISION_SCHEMA_INVALID"
    SIGNATURE_INVALID = "SIGNATURE_INVALID"
    CONTEXT_MISMATCH = "CONTEXT_MISMATCH"
    EXPIRED_DECISION = "EXPIRED_DECISION"
    REPLAY_DETECTED = "REPLAY_DETECTED"
    POLICY_LOAD_FAILED = "POLICY_LOAD_FAILED"
    AUDIT_WRITE_FAILED = "AUDIT_WRITE_FAILED"
    INPUT_HASH_MISMATCH = "INPUT_HASH_MISMATCH"
    SCHEMA_VERSION_INVALID = "SCHEMA_VERSION_INVALID"
    KEY_NOT_FOUND = "KEY_NOT_FOUND"


class VigilMetrics:
    """Priority 5: Observability - Metrics collection for decisions and errors."""
    
    def __init__(self):
        self.decision_outcomes = defaultdict(int)  # action -> count
        self.error_codes = defaultdict(int)  # error_code -> count
        self.latencies = []  # all latencies in ms
        self.latency_p50 = 0.0
        self.latency_p95 = 0.0
        self.latency_p99 = 0.0
        self._lock = threading.Lock()
    
    def record_decision(self, action: str):
        """Record a decision outcome."""
        with self._lock:
            self.decision_outcomes[action] += 1
    
    def record_error(self, error_code: str):
        """Record an error code."""
        with self._lock:
            self.error_codes[error_code] += 1
    
    def record_latency(self, latency_ms: float):
        """Record a latency measurement."""
        with self._lock:
            self.latencies.append(latency_ms)
            # Keep only last 1000 measurements
            if len(self.latencies) > 1000:
                self.latencies = self.latencies[-1000:]
            self._compute_percentiles()
    
    def _compute_percentiles(self):
        """Compute p50, p95, p99 percentiles."""
        if not self.latencies:
            self.latency_p50 = 0.0
            self.latency_p95 = 0.0
            self.latency_p99 = 0.0
            return
        
        sorted_latencies = sorted(self.latencies)
        n = len(sorted_latencies)
        
        self.latency_p50 = sorted_latencies[int(n * 0.50)]
        self.latency_p95 = sorted_latencies[int(n * 0.95)] if n > 1 else sorted_latencies[0]
        self.latency_p99 = sorted_latencies[int(n * 0.99)] if n > 1 else sorted_latencies[0]
    
    def get_stats(self) -> Dict[str, Any]:
        """Get current metrics."""
        with self._lock:
            return {
                "decision_outcomes": dict(self.decision_outcomes),
                "error_codes": dict(self.error_codes),
                "latency_p50_ms": round(self.latency_p50, 2),
                "latency_p95_ms": round(self.latency_p95, 2),
                "latency_p99_ms": round(self.latency_p99, 2),
                "samples_count": len(self.latencies)
            }


class AgentShieldClient:
    def __init__(self):
        self.base_url = os.getenv("AGENTSHIELD_URL", "http://localhost:9000")
        self.timeout_ms = int(os.getenv("AGENTSHIELD_TIMEOUT_MS", "1000"))  # Reduced from 3000ms to 1000ms
        self.mode = os.getenv("AGENTSHIELD_MODE", "http")
        self.require_signed = os.getenv("AGENTSHIELD_REQUIRE_SIGNED", "true").lower() == "true"
        self.key_id = os.getenv("AGENTSHIELD_KEY_ID", "default")
        self.pubkey_path = os.getenv("AGENTSHIELD_PUBKEY_PATH")
        self.pubkey_pem = os.getenv("AGENTSHIELD_PUBKEY_PEM")
        self.jwks_url = os.getenv("AGENTSHIELD_JWKS_URL")
        self.mtls_cert = os.getenv("AGENTSHIELD_MTLS_CERT")
        self.mtls_key = os.getenv("AGENTSHIELD_MTLS_KEY")
        self.max_retries = int(os.getenv("AGENTSHIELD_MAX_RETRIES", "2"))  # Retry on network errors only
        self.supported_schema_versions = {"as_decision_v1"}  # Supported schema versions
        self._jwks_cache: Optional[Dict] = None
        self._jwks_cache_time: float = 0
        self._jwks_cache_ttl = int(os.getenv("AGENTSHIELD_JWKS_TTL", "3600"))
        self._pubkey = self._load_pubkey()
        
        # Priority 5: Metrics and observability
        self.metrics = VigilMetrics()
        
        # Priority 5: Background key refresh thread
        self._start_background_key_refresh()

        # Priority 6: High Availability & Fail-Open
        self.fail_open = os.getenv("FAIL_OPEN", "false").lower() == "true"
        self.decision_cache = OrderedDict()
        self.decision_cache_ttl = 300  # 5 minutes default for cache validity
        self.decision_cache_limit = 1000
        self.decision_cache_lock = threading.Lock()
        self.log_sync_worker = None
        self.firewall_engine = None

    def register_log_worker(self, worker):
        self.log_sync_worker = worker

    def register_firewall_engine(self, engine):
        self.firewall_engine = engine

    def _cache_decision(self, input_hash: str, decision: dict):
        """Cache an ALLOW decision."""
        if decision.get("action") != "ALLOW":
            return
        
        with self.decision_cache_lock:
            # Evict if full (LRU: pop first item)
            if len(self.decision_cache) >= self.decision_cache_limit:
                self.decision_cache.popitem(last=False)
            
            # Add/Update (move to end)
            if input_hash in self.decision_cache:
                self.decision_cache.move_to_end(input_hash)
            
            self.decision_cache[input_hash] = {
                "decision": decision,
                "cached_at": time.time()
            }

    def _get_cached_decision(self, input_hash: str) -> Optional[dict]:
        """Retrieve a valid cached decision."""
        with self.decision_cache_lock:
            entry = self.decision_cache.get(input_hash)
            if not entry:
                return None
            
            # Check TTL
            age = time.time() - entry["cached_at"]
            if age > self.decision_cache_ttl:
                del self.decision_cache[input_hash]
                return None
            
            # Update LRU
            self.decision_cache.move_to_end(input_hash)
            return entry["decision"]

    def fetch_policies(self) -> list:
        """Fetch active policy rules (regexes) from AgentShield."""
        try:
            url = f"{self.base_url}/v1/policies/rules"
            resp = requests.get(url, timeout=self.timeout_ms / 1000.0)
            if resp.status_code == 200:
                data = resp.json()
                return data.get("rules", [])
        except Exception:
            pass
        return []

    def _fetch_jwks(self) -> Dict:
        if not self.jwks_url:
            return {}
        now = time.time()
        if self._jwks_cache and (now - self._jwks_cache_time) < self._jwks_cache_ttl:
            return self._jwks_cache
        try:
            resp = requests.get(self.jwks_url, timeout=self.timeout_ms / 1000.0)
            resp.raise_for_status()
            self._jwks_cache = resp.json()
            self._jwks_cache_time = now
            return self._jwks_cache
        except Exception:
            return self._jwks_cache or {}

    def _load_pubkey(self):
        data = None
        if self.pubkey_path and os.path.exists(self.pubkey_path):
            with open(self.pubkey_path, "rb") as f:
                data = f.read()
        elif self.pubkey_pem:
            data = self.pubkey_pem.encode("utf-8")
        if data and _CRYPTO_AVAILABLE:
            return load_pem_public_key(data)
        return None

    def _get_key_from_jwks(self, key_id: str):
        jwks = self._fetch_jwks()
        keys = jwks.get("keys", [])
        for key_data in keys:
            if key_data.get("kid") == key_id:
                kty = key_data.get("kty")
                if kty == "OKP" and key_data.get("crv") == "Ed25519":
                    x_b64 = key_data.get("x")
                    if x_b64:
                        x_bytes = base64.urlsafe_b64decode(x_b64 + "==")
                        return ed25519.Ed25519PublicKey.from_public_bytes(x_bytes)
                elif kty == "RSA":
                    # Future: decode RSA from JWK if needed
                    pass
        return None

    def _start_background_key_refresh(self):
        """Priority 5: Observability - Background thread to refresh keys automatically."""
        def _refresh():
            while True:
                try:
                    time.sleep(self._jwks_cache_ttl // 2)  # Refresh every half-TTL
                    self._fetch_jwks()  # Will update cache if needed
                except Exception:
                    pass  # Silently fail, will retry on next cycle
        
        thread = threading.Thread(target=_refresh, daemon=True)
        thread.start()

    @staticmethod
    def compute_input_hash(request_data: Dict[str, Any]) -> str:
        """Compute SHA-256 hash of canonicalized request input.
        
        This prevents request tampering. The hash is computed before sending
        to AgentShield and verified against the echoed value in the response.
        """
        # Canonical fields to hash (exclude metadata, include core context)
        canonical_data = {
            "agent_id": request_data.get("agent_id"),
            "messages": request_data.get("messages"),
            "policy_id": request_data.get("policy_id"),
            "request_id": request_data.get("request_id"),
            "tenant_id": request_data.get("tenant_id"),
            "timestamp_ms": request_data.get("timestamp_ms")
        }
        canonical_json = json.dumps(canonical_data, sort_keys=True, separators=(',', ':'))
        return hashlib.sha256(canonical_json.encode('utf-8')).hexdigest()

    @staticmethod
    def _canonical_payload(enforcement_request: Dict[str, Any], decision: Dict[str, Any]) -> bytes:
        payload = {
            "request_context": {
                "request_id": enforcement_request.get("request_id"),
                "tenant_id": enforcement_request.get("tenant_id"),
                "agent_id": enforcement_request.get("agent_id"),
                "policy_version": enforcement_request.get("policy_version"),
                "environment": enforcement_request.get("environment"),
            },
            "decision": {
                "action": decision.get("action"),
                "risk_score": decision.get("risk_score"),
                "reasons": decision.get("reasons"),
                "audit_event_id": decision.get("audit_event_id"),
                "signature_hash": decision.get("signature_hash"),
                "sanitized": decision.get("sanitized"),
            },
        }
        return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")

    def _verify_signature(self, enforcement_request: dict, decision: dict):
        if not self.require_signed:
            return True
        if not _CRYPTO_AVAILABLE:
            raise RuntimeError("cryptography not installed; cannot verify signature")

        signature_b64 = decision.get("signature")
        signature_key_id = decision.get("signature_key_id") or decision.get("key_id")
        if not signature_b64 or not signature_key_id:
            error = ValueError("Unsigned decision or missing signature_key_id")
            error.vigil_error_code = VigilErrorCode.SIGNATURE_INVALID
            raise error

        # 1. Validate schema_version (NEW)
        schema_version = decision.get("schema_version")
        if schema_version:
            if schema_version not in self.supported_schema_versions:
                error = ValueError(f"Unsupported schema_version: {schema_version}")
                error.vigil_error_code = VigilErrorCode.SCHEMA_VERSION_INVALID
                raise error
        
        # 2. Validate timestamp with clock skew tolerance (UPDATED)
        issued_at = decision.get("issued_at")
        if issued_at:
            current_time = time.time()
            clock_skew_tolerance = 120  # ±2 minutes tolerance
            decision_age = current_time - issued_at
            
            # Check if decision is too old
            max_age_seconds = int(os.getenv("DECISION_MAX_AGE_SECONDS", "300"))  # 5 minutes default
            if decision_age > (max_age_seconds + clock_skew_tolerance):
                error = ValueError(f"Decision timestamp expired: {decision_age}s > {max_age_seconds}s")
                error.vigil_error_code = VigilErrorCode.EXPIRED_DECISION
                raise error
            
            # Check if decision is from the future (clock skew)
            if decision_age < -clock_skew_tolerance:
                error = ValueError(f"Decision timestamp in future: {-decision_age}s (clock skew)")
                error.vigil_error_code = VigilErrorCode.EXPIRED_DECISION
                raise error
        
        # 3. Validate ttl_ms (NEW)
        ttl_ms = decision.get("ttl_ms")
        if ttl_ms and issued_at:
            current_time_ms = int(time.time() * 1000)
            issued_at_ms = int(issued_at * 1000)
            expiry_time_ms = issued_at_ms + ttl_ms
            
            if current_time_ms > expiry_time_ms:
                error = ValueError(f"Decision TTL expired: current={current_time_ms} > expiry={expiry_time_ms}")
                error.vigil_error_code = VigilErrorCode.EXPIRED_DECISION
                raise error

        # 4. Validate context_echo (UPDATED with new fields)
        context_echo = decision.get("context_echo")
        if context_echo:
            req_request_id = enforcement_request.get("request_id")
            req_tenant = enforcement_request.get("tenant_id")
            req_agent = enforcement_request.get("agent_id")
            req_policy_version = enforcement_request.get("policy_version")
            req_policy_id = enforcement_request.get("policy_id")  # NEW
            req_input_hash = enforcement_request.get("input_hash")  # NEW
            
            # Request ID validation - prevents replay
            if context_echo.get("request_id") != req_request_id:
                error = ValueError(f"Replay detected: request_id mismatch {context_echo.get('request_id')} != {req_request_id}")
                error.vigil_error_code = VigilErrorCode.REPLAY_DETECTED
                raise error
            
            # Tenant isolation
            if context_echo.get("tenant_id") != req_tenant:
                error = ValueError(f"Context mismatch: tenant {context_echo.get('tenant_id')} != {req_tenant}")
                error.vigil_error_code = VigilErrorCode.CONTEXT_MISMATCH
                raise error
            
            # Agent validation
            if context_echo.get("agent_id") != req_agent:
                error = ValueError(f"Context mismatch: agent {context_echo.get('agent_id')} != {req_agent}")
                error.vigil_error_code = VigilErrorCode.CONTEXT_MISMATCH
                raise error
            
            # Policy version
            if context_echo.get("policy_version") != req_policy_version:
                error = ValueError(f"Context mismatch: policy_version {context_echo.get('policy_version')} != {req_policy_version}")
                error.vigil_error_code = VigilErrorCode.CONTEXT_MISMATCH
                raise error
            
            # Policy ID validation (NEW)
            if req_policy_id and context_echo.get("policy_id") != req_policy_id:
                error = ValueError(f"Context mismatch: policy_id {context_echo.get('policy_id')} != {req_policy_id}")
                error.vigil_error_code = VigilErrorCode.CONTEXT_MISMATCH
                raise error
            
            # Input hash validation (NEW - CRITICAL)
            if req_input_hash and context_echo.get("input_hash") != req_input_hash:
                error = ValueError(f"Input hash mismatch: request tampered")
                error.vigil_error_code = VigilErrorCode.INPUT_HASH_MISMATCH
                raise error

        # 5. Load key from JWKS or pinned (TEE.fail: must succeed for verification)
        pubkey = None
        if self.jwks_url:
            pubkey = self._get_key_from_jwks(signature_key_id)
        if not pubkey:
            pubkey = self._pubkey
        if not pubkey:
            # TEE.fail: Key not found is critical failure - fail closed
            error = RuntimeError(f"Signature verification failed: key '{signature_key_id}' not available")
            error.vigil_error_code = VigilErrorCode.KEY_NOT_FOUND
            raise error

        try:
            signature = base64.urlsafe_b64decode(signature_b64 + "==")
        except Exception as exc:
            error = ValueError("Invalid signature encoding")
            error.vigil_error_code = VigilErrorCode.SIGNATURE_INVALID
            raise error from exc

        # Build canonical payload from CURRENT decision state
        current_canonical = self._canonical_payload(enforcement_request, decision)
        current_canonical_hash = hashlib.sha256(current_canonical).digest()

        # 6. Verify signature based on key type
        try:
            if isinstance(pubkey, ed25519.Ed25519PublicKey):
                # Ed25519: verify against canonical_payload_hash if provided, else canonical payload
                canonical_hash = decision.get("canonical_payload_hash")
                if canonical_hash:
                    # TEE.fail: Verify the provided hash matches current state
                    provided_hash = base64.urlsafe_b64decode(canonical_hash + "==")
                    if provided_hash != current_canonical_hash:
                        error = ValueError("TEE.fail: Decision payload tampered (hash mismatch)")
                        error.vigil_error_code = VigilErrorCode.SIGNATURE_INVALID
                        raise error
                    message = provided_hash
                else:
                    message = current_canonical_hash
                pubkey.verify(signature, message)
            elif isinstance(pubkey, rsa.RSAPublicKey):
                # RSA: verify against canonical payload
                payload = current_canonical
                pubkey.verify(
                    signature,
                    payload,
                    padding.PKCS1v15(),
                    hashes.SHA256(),
                )
            else:
                error = ValueError("Unsupported key type for verification")
                error.vigil_error_code = VigilErrorCode.SIGNATURE_INVALID
                raise error
        except Exception as e:
            if not hasattr(e, 'vigil_error_code'):
                e.vigil_error_code = VigilErrorCode.SIGNATURE_INVALID
            raise
        return True

    def _get_keys(self) -> Dict:
        """Public method to get JWKS keys for dashboard API."""
        return self._fetch_jwks()

    def enforce(self, enforcement_request: dict) -> dict:
        if self.mode != "http":
            # vsock mode not implemented in dev; stub
            raise RuntimeError("vsock mode not implemented")
        
        # Add timestamp_ms if not present
        if "timestamp_ms" not in enforcement_request:
            enforcement_request["timestamp_ms"] = int(time.time() * 1000)
        
        # Add ttl_ms if not present (default 5 minutes)
        if "ttl_ms" not in enforcement_request:
            enforcement_request["ttl_ms"] = 300000  # 5 minutes
        
        # Compute input_hash (CRITICAL - prevents request tampering)
        input_hash = self.compute_input_hash(enforcement_request)
        enforcement_request["input_hash"] = input_hash
        
        url = f"{self.base_url}/v1/enforce"
        cert = None
        if self.mtls_cert and self.mtls_key:
            cert = (self.mtls_cert, self.mtls_key)
        
        # Retry logic for network errors only
        last_exception = None
        for attempt in range(self.max_retries + 1):
            try:
                resp = requests.post(
                    url,
                    json=enforcement_request,
                    timeout=self.timeout_ms / 1000.0,
                    cert=cert
                )
                resp.raise_for_status()
                decision = resp.json()
                
                # Validate decision response
                if self.require_signed:
                    try:
                        self._verify_signature(enforcement_request, decision)
                        decision["sig_verified"] = True
                        decision["error_code"] = None
                    except Exception as e:
                        decision["sig_verified"] = False
                        decision["error_code"] = getattr(e, 'vigil_error_code', VigilErrorCode.SIGNATURE_INVALID)
                        raise
                else:
                    decision["sig_verified"] = False
                    decision["error_code"] = None
                
                # Add input_hash and policy_id to decision for audit logging
                decision["input_hash"] = input_hash
                decision["policy_id"] = enforcement_request.get("policy_id")
                
                # Priority 5: Record metrics
                action = decision.get("action")
                if action:
                    self.metrics.record_decision(action)
                
                return decision
                
            except requests.exceptions.Timeout as e:
                last_exception = e
                error_code = VigilErrorCode.AGENTSHIELD_TIMEOUT
                # Priority 5: Record error metric
                self.metrics.record_error(error_code.value)
                if attempt < self.max_retries:
                    continue  # Retry on timeout
                break
            except requests.exceptions.ConnectionError as e:
                last_exception = e
                error_code = VigilErrorCode.AGENTSHIELD_UNREACHABLE
                # Priority 5: Record error metric
                self.metrics.record_error(error_code.value)
                if attempt < self.max_retries:
                    continue  # Retry on connection error
                break
            except requests.exceptions.RequestException as e:
                # Non-retryable HTTP errors (4xx, 5xx)
                last_exception = e
                error_code = VigilErrorCode.AGENTSHIELD_UNREACHABLE
                # Priority 5: Record error metric
                self.metrics.record_error(error_code.value)
                break
            except ValueError as e:
                # Schema or verification errors - don't retry
                last_exception = e
                error_code = getattr(e, 'vigil_error_code', VigilErrorCode.DECISION_SCHEMA_INVALID)
                # Priority 5: Record error metric
                self.metrics.record_error(error_code.value)
                break
            except Exception as e:
                # Other errors - don't retry
                last_exception = e
                error_code = getattr(e, 'vigil_error_code', VigilErrorCode.AGENTSHIELD_UNREACHABLE)
                # Priority 5: Record error metric
                self.metrics.record_error(error_code.value)
                break
        
        # All retries exhausted or non-retryable error
        if last_exception:
            error = RuntimeError(f"AgentShield enforcement failed: {str(last_exception)}")
            error.vigil_error_code = error_code
            error.__cause__ = last_exception
            raise error
        
        # Should never reach here
        error = RuntimeError("AgentShield enforcement failed: unknown error")
        error.vigil_error_code = VigilErrorCode.AGENTSHIELD_UNREACHABLE
        raise error

    def get_decision(self, decision_request: dict) -> dict:
        """Call AgentShield /decision endpoint to obtain a signed decision envelope.

        Adds required timing fields, computes a simple nonce, and verifies
        the signature using JWKS or pinned public key.
        """
        url = f"{self.base_url}/decision"

        # Required temporal/context fields
        if "timestamp_ms" not in decision_request:
            decision_request["timestamp_ms"] = int(time.time() * 1000)
        if "ttl_ms" not in decision_request:
            decision_request["ttl_ms"] = 300000  # 5 minutes
        if "nonce" not in decision_request:
            decision_request["nonce"] = base64.urlsafe_b64encode(os.urandom(16)).decode("ascii").rstrip("=")

        # Compute input_hash similar to enforce()
        input_hash = self.compute_input_hash(decision_request)
        decision_request["input_hash"] = input_hash

        try:
            resp = requests.post(
                url,
                json=decision_request,
                timeout=self.timeout_ms / 1000.0,
            )
            resp.raise_for_status()
            envelope = resp.json()

            # Verify signature on the returned envelope
            self._verify_decision_envelope(envelope)
            envelope["sig_verified"] = True
            return envelope
        except Exception as e:
            err = RuntimeError(f"AgentShield decision failed: {e}")
            err.vigil_error_code = VigilErrorCode.AGENTSHIELD_UNREACHABLE
            raise err

    def _verify_decision_envelope(self, envelope: dict) -> None:
        """Verify Ed25519 signature over canonical decision payload.

        Expects fields: signature, key_id, schema_version, issued_at, ttl_ms,
        context_echo, decision (ALLOW/BLOCK/etc).
        """
        if not _CRYPTO_AVAILABLE:
            raise RuntimeError("cryptography not installed; cannot verify signature")

        # Basic freshness checks
        issued_at = envelope.get("issued_at")
        ttl_ms = envelope.get("ttl_ms")
        if issued_at and ttl_ms:
            now_ms = int(time.time() * 1000)
            if now_ms > int(issued_at) + int(ttl_ms):
                error = ValueError("Decision TTL expired")
                error.vigil_error_code = VigilErrorCode.EXPIRED_DECISION
                raise error

        # Canonicalize payload for signature verification
        context_echo = envelope.get("context_echo", {})
        canonical = {
            "decision": envelope.get("decision"),
            "risk_score": envelope.get("risk_score"),
            "reasons": envelope.get("reasons"),
            "audit_event_id": envelope.get("audit_event_id"),
            "context_echo": {
                "tenant_id": context_echo.get("tenant_id"),
                "agent_id": context_echo.get("agent_id"),
                "policy_id": context_echo.get("policy_id"),
                "policy_version": context_echo.get("policy_version"),
                "request_id": context_echo.get("request_id"),
                "timestamp_ms": context_echo.get("timestamp_ms"),
                "ttl_ms": context_echo.get("ttl_ms"),
                "input_hash": context_echo.get("input_hash"),
            },
            "issued_at": envelope.get("issued_at"),
        }

        canonical_bytes = json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode("utf-8")

        # Load public key
        kid = envelope.get("key_id") or envelope.get("signature_key_id")
        pubkey = None
        if self.jwks_url:
            pubkey = self._get_key_from_jwks(kid)
        if not pubkey:
            pubkey = self._pubkey
        if not pubkey:
            error = RuntimeError(f"Signature verification failed: key '{kid}' not available")
            error.vigil_error_code = VigilErrorCode.KEY_NOT_FOUND
            raise error

        # Verify signature
        sig_b64 = envelope.get("signature")
        try:
            signature = base64.urlsafe_b64decode((sig_b64 or "") + "==")
        except Exception as exc:
            error = ValueError("Invalid signature encoding")
            error.vigil_error_code = VigilErrorCode.SIGNATURE_INVALID
            raise error from exc

        try:
            if isinstance(pubkey, ed25519.Ed25519PublicKey):
                pubkey.verify(signature, canonical_bytes)
            elif isinstance(pubkey, rsa.RSAPublicKey):
                pubkey.verify(signature, canonical_bytes, padding.PKCS1v15(), hashes.SHA256())
            else:
                error = ValueError("Unsupported key type for verification")
                error.vigil_error_code = VigilErrorCode.SIGNATURE_INVALID
                raise error
        except Exception as e:
            if not hasattr(e, 'vigil_error_code'):
                e.vigil_error_code = VigilErrorCode.SIGNATURE_INVALID
            raise
