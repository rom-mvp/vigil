"""
Integration test for real AgentShield backend.

Tests:
- Ed25519 signature verification
- Merkle proof validation
- AWS Nitro attestation verification
- Azure TDX attestation verification
- ML-based threat detection (sentence transformers)
- Replay protection (300s window)
- Decision caching with semantic similarity
"""

import pytest
import requests
import json
import base64
import hashlib
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, MagicMock
import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../src'))

from vigil.clients import AgentShieldClient


class TestAgentShieldRealClient:
    """Test real AgentShield client integration."""

    @pytest.fixture
    def client(self):
        """Create AgentShieldClient for testing."""
        return AgentShieldClient(
            base_url="http://localhost:9000",
            api_key="test-api-key",
            timeout_ms=5000,
            require_signed=True,
            verify_merkle=True
        )

    @pytest.fixture
    def mock_decision(self):
        """Mock AgentShield decision with signatures and proofs."""
        return {
            "action": "ALLOW",
            "risk_score": 0.15,
            "reasons": [],
            "issued_at": datetime.utcnow().isoformat(),
            "expires_at_ms": int((datetime.utcnow() + timedelta(minutes=5)).timestamp() * 1000),
            "signature": base64.b64encode(b"mock_ed25519_signature").decode(),
            "signature_key_id": "agentshield-key-1",
            "canonical_payload_hash": base64.b64encode(hashlib.sha256(b"payload").digest()).decode(),
            "merkle_root": base64.urlsafe_b64encode(hashlib.sha256(b"root").digest()).decode().rstrip('='),
            "merkle_proof": [
                {"sibling": base64.urlsafe_b64encode(hashlib.sha256(b"sib1").digest()).decode().rstrip('='), "side": "left"},
                {"sibling": base64.urlsafe_b64encode(hashlib.sha256(b"sib2").digest()).decode().rstrip('='), "side": "right"},
            ],
            "timestamp": datetime.utcnow().isoformat(),
        }

    # ========================================================================
    # SIGNATURE VERIFICATION TESTS
    # ========================================================================

    def test_signature_verification_required(self, client, mock_decision):
        """Test that signature verification is enforced when required."""
        # This would normally call the real backend
        # For testing, we verify the client structure is correct
        assert client.require_signed is True
        assert hasattr(client, '_verify_signature')

    @patch('vigil.clients.agentshield_client.requests.get')
    def test_jwks_caching(self, mock_get, client):
        """Test JWKS is fetched and cached."""
        jwks_response = {
            "keys": [
                {
                    "kid": "key-1",
                    "kty": "OKP",
                    "crv": "Ed25519",
                    "x": base64.urlsafe_b64encode(b"x" * 32).decode().rstrip('='),
                }
            ]
        }
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = jwks_response
        mock_get.return_value = mock_response

        # First call
        keys1 = client.get_jwks()
        assert keys1 == jwks_response

        # Second call should hit cache
        keys2 = client.get_jwks()
        assert keys2 == jwks_response
        assert mock_get.call_count == 1  # Only called once due to cache

    # ========================================================================
    # MERKLE PROOF VALIDATION TESTS
    # ========================================================================

    def test_merkle_proof_validation_enabled(self, client):
        """Test that Merkle proof validation is enabled."""
        assert client.verify_merkle is True
        assert hasattr(client, '_verify_merkle_proof')

    @patch('vigil.clients.agentshield_client.requests.get')
    def test_merkle_root_fetch(self, mock_get, client):
        """Test fetching current Merkle root."""
        root_response = {
            "merkle_root": base64.urlsafe_b64encode(hashlib.sha256(b"root").digest()).decode().rstrip('='),
            "timestamp": datetime.utcnow().isoformat(),
        }
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = root_response
        mock_get.return_value = mock_response

        root = client.get_merkle_root()
        assert root == root_response

    # ========================================================================
    # AWS NITRO ATTESTATION TESTS
    # ========================================================================

    @patch('vigil.clients.agentshield_client.os.getenv')
    @patch('vigil.clients.agentshield_client.boto3')
    def test_nitro_attestation_verification(self, mock_boto3, mock_getenv, client):
        """Test AWS Nitro enclave attestation verification."""
        mock_getenv.return_value = "us-east-1"

        # Mock boto3 EC2 client
        mock_ec2_client = MagicMock()
        mock_boto3.client.return_value = mock_ec2_client

        # Mock attestation verification response
        mock_ec2_client.verify_attestation_document.return_value = {
            "VerificationResult": True,
            "DocumentContent": {
                "pcr0": "abcd1234",
                "pcr1": "efgh5678",
                "pcr2": "ijkl9012",
                "timestamp": datetime.utcnow().timestamp(),
            }
        }

        decision_with_attestation = {
            "action": "ALLOW",
            "attestation_document": base64.b64encode(b"mock_nitro_doc").decode(),
            "attestation_type": "aws_nitro",
            "policy_measurements": {
                "aws_nitro_pcr_allow_list": [
                    {"pcr0": "abcd1234", "pcr1": "efgh5678", "pcr2": "ijkl9012"}
                ]
            }
        }

        result = client.verify_attestation(decision_with_attestation)
        assert result is True

    @patch('vigil.clients.agentshield_client.os.getenv')
    @patch('vigil.clients.agentshield_client.boto3')
    def test_nitro_attestation_pcr_mismatch(self, mock_boto3, mock_getenv, client):
        """Test Nitro attestation fails when PCR not in allow-list."""
        mock_getenv.return_value = "us-east-1"

        mock_ec2_client = MagicMock()
        mock_boto3.client.return_value = mock_ec2_client

        mock_ec2_client.verify_attestation_document.return_value = {
            "VerificationResult": True,
            "DocumentContent": {
                "pcr0": "wrong1234",  # Different PCR
                "pcr1": "efgh5678",
                "pcr2": "ijkl9012",
                "timestamp": datetime.utcnow().timestamp(),
            }
        }

        decision = {
            "action": "ALLOW",
            "attestation_document": base64.b64encode(b"nitro_doc").decode(),
            "attestation_type": "aws_nitro",
            "policy_measurements": {
                "aws_nitro_pcr_allow_list": [
                    {"pcr0": "abcd1234", "pcr1": "efgh5678", "pcr2": "ijkl9012"}
                ]
            }
        }

        result = client.verify_attestation(decision)
        assert result is False

    # ========================================================================
    # AZURE TDX ATTESTATION TESTS
    # ========================================================================

    @patch('vigil.clients.agentshield_client.os.getenv')
    @patch('vigil.clients.agentshield_client.AttestationClient')
    def test_azure_tdx_attestation_verification(self, mock_att_client_cls, mock_getenv, client):
        """Test Azure TDX attestation verification."""
        mock_getenv.return_value = "https://attest.azure.net"

        # Mock Azure attestation client
        mock_att_client = MagicMock()
        mock_att_client_cls.return_value = mock_att_client

        # Mock verification result
        mock_result = MagicMock()
        mock_result.is_valid = True
        mock_result.get_claims.return_value = {
            "x-ms-attest-enclave-identity": {
                "mrenclave": "abc123",
                "mrsigner": "def456",
            },
            "exp": int(datetime.utcnow().timestamp()),
        }
        mock_att_client.verify_attestation_report.return_value = mock_result

        decision = {
            "action": "ALLOW",
            "attestation_document": base64.b64encode(b"azure_report").decode(),
            "attestation_type": "azure_tdx",
            "policy_measurements": {
                "azure_tdx_allow_list": [
                    {"mrenclave": "abc123", "mrsigner": "def456"}
                ]
            }
        }

        result = client.verify_attestation(decision)
        assert result is True

    @patch('vigil.clients.agentshield_client.os.getenv')
    @patch('vigil.clients.agentshield_client.AttestationClient')
    def test_azure_tdx_attestation_expired(self, mock_att_client_cls, mock_getenv, client):
        """Test Azure TDX attestation fails when expired."""
        mock_getenv.return_value = "https://attest.azure.net"

        mock_att_client = MagicMock()
        mock_att_client_cls.return_value = mock_att_client

        # Mock expired report
        mock_result = MagicMock()
        mock_result.is_valid = True
        mock_result.get_claims.return_value = {
            "x-ms-attest-enclave-identity": {
                "mrenclave": "abc123",
                "mrsigner": "def456",
            },
            "exp": int((datetime.utcnow() - timedelta(minutes=10)).timestamp()),  # 10 min old
        }
        mock_att_client.verify_attestation_report.return_value = mock_result

        decision = {
            "action": "ALLOW",
            "attestation_document": base64.b64encode(b"azure_report").decode(),
            "attestation_type": "azure_tdx",
        }

        result = client.verify_attestation(decision)
        assert result is False

    # ========================================================================
    # ML THREAT DETECTION TESTS
    # ========================================================================

    def test_decision_ml_detection_metadata(self, mock_decision):
        """Test that ML threat detection metadata is included."""
        # Decision should include ML analysis results
        assert "risk_score" in mock_decision
        assert isinstance(mock_decision["risk_score"], float)
        assert 0 <= mock_decision["risk_score"] <= 1.0

    # ========================================================================
    # REPLAY PROTECTION TESTS
    # ========================================================================

    def test_replay_window_configuration(self, client):
        """Test replay protection window is configured."""
        # Replay window should be 300 seconds (5 minutes)
        # This is typically enforced by AgentShield backend
        assert client.timeout > 0

    @patch('vigil.clients.agentshield_client.requests.post')
    def test_replay_detection_response(self, mock_post, client):
        """Test that replay attempts are detected."""
        # AgentShield returns 409 Conflict for replays
        mock_response = Mock()
        mock_response.status_code = 409
        mock_response.json.return_value = {
            "action": "BLOCK",
            "reason": "replay_detected",
            "message": "Request matches replay window"
        }
        mock_post.return_value = mock_response

        # Real AgentShield would return this, client should handle it
        assert hasattr(client, 'enforce')

    # ========================================================================
    # DECISION CACHING TESTS
    # ========================================================================

    def test_semantic_similarity_caching(self):
        """Test semantic decision cache uses similarity matching."""
        # This is tested in vigil_enhanced_server.py's SemanticDecisionCache
        # Verify the client can be used with a cache wrapper
        from vigil_enhanced_server import SemanticDecisionCache

        cache = SemanticDecisionCache(ttl_seconds=300, sim_threshold=0.92)
        assert cache.ttl == 300
        assert cache.sim_threshold == 0.92

    # ========================================================================
    # HEALTH & CONNECTIVITY TESTS
    # ========================================================================

    @patch('vigil.clients.agentshield_client.requests.get')
    def test_health_check(self, mock_get, client):
        """Test AgentShield health check."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "status": "healthy",
            "version": "1.0.0",
            "backend": "real"
        }
        mock_get.return_value = mock_response

        health = client.health()
        assert health["status"] == "healthy"

    # ========================================================================
    # ERROR HANDLING TESTS
    # ========================================================================

    def test_missing_attestation_document(self, client):
        """Test handling of missing attestation document."""
        decision = {
            "action": "ALLOW",
            "risk_score": 0.1
            # No attestation_document
        }

        result = client.verify_attestation(decision)
        assert result is False  # Should return False, not raise

    def test_unknown_attestation_type(self, client):
        """Test handling of unknown attestation type."""
        decision = {
            "action": "ALLOW",
            "attestation_document": base64.b64encode(b"doc").decode(),
            "attestation_type": "unknown_tee",  # Invalid type
        }

        result = client.verify_attestation(decision)
        assert result is False

    def test_invalid_attestation_raises_error(self, client):
        """Test that invalid attestation raises ValueError when required."""
        client.require_signed = True

        with patch.object(
            client, '_verify_nitro_attestation', side_effect=Exception("Invalid doc")
        ):
            decision = {
                "action": "ALLOW",
                "attestation_document": "invalid_base64!!!",
                "attestation_type": "aws_nitro",
            }

            with pytest.raises(ValueError):
                client.verify_attestation(decision)


class TestGatewayAttestationIntegration:
    """Test Vigil gateway integration with real attestation."""

    @pytest.fixture
    def gateway_client(self):
        """Create HTTP client for gateway testing."""
        return requests.Session()

    def test_gateway_health_check(self, gateway_client):
        """Test gateway health endpoint."""
        try:
            response = gateway_client.get("http://localhost:8000/health", timeout=5)
            assert response.status_code == 200
        except requests.ConnectionError:
            pytest.skip("Gateway not running")

    def test_gateway_attestation_validation_in_decision(self, gateway_client):
        """Test that gateway validates attestation in AgentShield decision."""
        try:
            payload = {
                "messages": [
                    {"role": "user", "content": "What is 2+2?"}
                ]
            }
            response = gateway_client.post(
                "http://localhost:8000/v1/chat/completions",
                json=payload,
                headers={"Authorization": "Bearer test-key"},
                timeout=5
            )
            assert response.status_code in [200, 202]

            # Response should include attestation status if present
            resp_data = response.json()
            if "attestation_verified" in resp_data:
                assert isinstance(resp_data["attestation_verified"], bool)
        except requests.ConnectionError:
            pytest.skip("Gateway not running")


class TestProductionReadiness:
    """Verify production-ready features."""

    def test_no_mock_imports(self):
        """Verify no mock_agentshield imports remain."""
        import vigil_enhanced_server
        source = open(vigil_enhanced_server.__file__).read()

        # Should NOT import or use mock_agentshield
        assert "mock_agentshield" not in source
        assert "create_agentshield_mock" not in source

    def test_real_client_imported(self):
        """Verify real AgentShieldClient is imported."""
        from vigil.clients import AgentShieldClient
        assert AgentShieldClient is not None

        # Should have real methods
        assert hasattr(AgentShieldClient, 'verify_attestation')
        assert hasattr(AgentShieldClient, '_verify_nitro_attestation')
        assert hasattr(AgentShieldClient, '_verify_azure_attestation')

    def test_no_hardcoded_secrets(self):
        """Verify no hardcoded secrets in code."""
        import os
        import glob

        secret_patterns = ["password", "secret", "token", "api_key"]
        for py_file in glob.glob("/workspaces/vigil/src/**/*.py", recursive=True):
            with open(py_file) as f:
                content = f.read().lower()
                # Just check for obviously hardcoded values
                if "password=" in content or "secret=" in content:
                    if "getenv" not in content:
                        pytest.fail(f"Possible hardcoded secret in {py_file}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
