"""
TEE Attestation Client for Vigil
Generates platform-specific attestation quotes for mutual trust with AgentShield enclave.

Supported Platforms:
- Intel SGX (DCAP/EPID)
- AMD SEV-SNP
- Intel TDX
- Azure Confidential Compute

Status: Stub implementation - requires platform SDKs
"""

import os
import json
import hashlib
import base64
import uuid
import time
import struct
from typing import Optional, Dict, Any
from enum import Enum
from datetime import datetime


class TEEType(str, Enum):
    """Supported TEE platforms"""
    SGX = "sgx"
    SEV = "sev"
    TDX = "tdx"
    AZURE_CC = "azure"
    NONE = "none"


class TEEAttestationClient:
    """Generate and manage TEE attestation quotes
    
    Supports multiple TEE platforms with automatic detection.
    Generates properly-structured attestation reports that can be
    verified by AgentShield enclave.
    """
    
    def __init__(self):
        self.tee_type = self._detect_tee_type()
        self.enabled = os.getenv("VIGIL_TEE_ENABLED", "false").lower() == "true"
        self.instance_id = str(uuid.uuid4())[:16]
        self.measurements = self._load_or_generate_measurements()
        
        if self.enabled:
            print(f"✓ TEE Attestation enabled (Platform: {self.tee_type}, Instance: {self.instance_id})")
        else:
            print(f"⚠ TEE Attestation disabled (Standard mode)")
    
    def _detect_tee_type(self) -> TEEType:
        """Auto-detect TEE platform from environment"""
        
        # Explicit override
        tee_type_env = os.getenv("VIGIL_TEE_TYPE", "").lower()
        if tee_type_env in [t.value for t in TEEType]:
            return TEEType(tee_type_env)
        
        # Intel SGX detection
        if os.path.exists("/dev/sgx_enclave") or os.path.exists("/dev/isgx"):
            return TEEType.SGX
        
        # AMD SEV detection
        if os.path.exists("/dev/sev-guest"):
            return TEEType.SEV
        
        # Intel TDX detection
        if os.path.exists("/dev/tdx-guest"):
            return TEEType.TDX
        
        # Azure Confidential Compute (check IMDS endpoint reachability)
        try:
            import socket
            sock = socket.create_connection(("169.254.169.254", 80), timeout=1)
            sock.close()
            if os.path.exists("/sys/firmware/acpi/tables/SPCR"):
                return TEEType.AZURE_CC
        except Exception:
            pass
        
        return TEEType.NONE
    
    def _load_or_generate_measurements(self) -> Dict[str, str]:
        """Load measurements from cache or generate fresh ones"""
        cache_file = os.getenv("VIGIL_MEASUREMENTS_CACHE", "/tmp/vigil_measurements.json")
        
        # Try to load from cache
        if os.path.exists(cache_file):
            try:
                with open(cache_file, 'r') as f:
                    return json.load(f)
            except Exception:
                pass
        
        # Generate measurements based on platform
        measurements = self._generate_measurements()
        
        # Save to cache
        try:
            os.makedirs(os.path.dirname(cache_file), exist_ok=True)
            with open(cache_file, 'w') as f:
                json.dump(measurements, f)
        except Exception:
            pass
        
        return measurements
    
    def _generate_measurements(self) -> Dict[str, str]:
        """Generate platform-specific measurements"""
        if self.tee_type == TEEType.SGX:
            mrenclave = hashlib.sha256(b"vigil-gateway-sgx-v1.0" + self.instance_id.encode()).hexdigest()
            mrsigner = hashlib.sha256(b"vigil-signer-key").hexdigest()
            return {
                "mrenclave": mrenclave,
                "mrsigner": mrsigner,
                "isv_prod_id": "1",
                "isv_svn": "1"
            }
        elif self.tee_type == TEEType.SEV:
            measurement = hashlib.sha384(b"vigil-gateway-sev-v1.0" + self.instance_id.encode()).hexdigest()
            return {
                "measurement": measurement,
                "policy": "0x30000",
                "guest_svn": "1"
            }
        elif self.tee_type == TEEType.TDX:
            mrtd = hashlib.sha384(b"vigil-gateway-tdx-v1.0" + self.instance_id.encode()).hexdigest()
            rtmr0 = hashlib.sha384(b"vigil-rtmr0-acpi").hexdigest()
            rtmr1 = hashlib.sha384(b"vigil-rtmr1-firmware").hexdigest()
            return {
                "mrtd": mrtd,
                "rtmr0": rtmr0,
                "rtmr1": rtmr1,
                "tdx_svn": "1"
            }
        elif self.tee_type == TEEType.AZURE_CC:
            return {
                "vm_id": self.instance_id,
                "vm_size": "Standard_DC2s_v3",
                "location": "eastus",
                "environment": "AzurePublicCloud"
            }
        else:
            return {}
    
    def generate_attestation_quote(self, nonce: Optional[bytes] = None) -> Dict[str, Any]:
        """Generate platform-specific attestation quote
        
        Args:
            nonce: Fresh random nonce to prevent replay (optional, generated if not provided)
        
        Returns:
            Attestation quote including measurements, signature, and platform-specific data
        """
        # Generate nonce if not provided
        if nonce is None:
            nonce = os.urandom(32)
        
        if not self.enabled:
            return {"type": "none", "attestation": None}
        
        if self.tee_type == TEEType.SGX:
            return self._generate_sgx_quote(nonce)
        elif self.tee_type == TEEType.SEV:
            return self._generate_sev_quote(nonce)
        elif self.tee_type == TEEType.TDX:
            return self._generate_tdx_quote(nonce)
        elif self.tee_type == TEEType.AZURE_CC:
            return self._generate_azure_quote(nonce)
        else:
            return {"type": "none", "attestation": None}
    
    def _generate_sgx_quote(self, nonce: bytes) -> Dict[str, Any]:
        """Generate Intel SGX attestation quote (DCAP or EPID)
        
        Returns a properly-structured quote that AgentShield can verify.
        In production, this would call into SGX SDK; we return a realistic mock.
        """
        quote_id = hashlib.sha256(nonce + self.instance_id.encode()).hexdigest()[:16]
        quote_data = {
            "version": 3,
            "sign_type": 0,  # ECDSA with P-256
            "epid_group_flags": 0,
            "tcb_evaluation_flags": 0,
            "pce_svn": 12,
            "cpusvn": "0" * 32,
            "misc_select": 1,
            "attributes": "0100000000000000",  # Enclave initiated
            "mr_enclave": self.measurements.get("mrenclave"),
            "mr_signer": self.measurements.get("mrsigner"),
            "config_id": "0" * 32,
            "isv_prod_id": int(self.measurements.get("isv_prod_id", 1)),
            "isv_svn": int(self.measurements.get("isv_svn", 1)),
            "config_svn": 0,
            "reserved": "0" * 32,
            "report_data": hashlib.sha256(nonce).hexdigest()[:64]
        }
        
        # Mock quote signature
        quote_signature = base64.b64encode(
            hashlib.sha256(json.dumps(quote_data, sort_keys=True).encode()).digest()
        ).decode()
        
        return {
            "type": "sgx",
            "tee_type": self.tee_type.value,
            "quote_id": quote_id,
            "quote": base64.b64encode(json.dumps(quote_data).encode()).decode(),
            "signature": quote_signature,
            "signature_algorithm": "ECDSA-P256",
            "mrenclave": self.measurements.get("mrenclave"),
            "mrsigner": self.measurements.get("mrsigner"),
            "isv_prod_id": int(self.measurements.get("isv_prod_id", 1)),
            "isv_svn": int(self.measurements.get("isv_svn", 1)),
            "nonce": base64.b64encode(nonce).decode(),
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "instance_id": self.instance_id
        }
    
    def _generate_sev_quote(self, nonce: bytes) -> Dict[str, Any]:
        """Generate AMD SEV-SNP attestation report
        
        Returns properly-structured report for AgentShield verification.
        """
        report_id = hashlib.sha256(nonce + self.instance_id.encode()).hexdigest()[:16]
        report_data = {
            "report_version": 2,
            "guest_svn": int(self.measurements.get("guest_svn", 1)),
            "policy": self.measurements.get("policy", "0x30000"),
            "family_id": "0" * 16,
            "image_id": "0" * 16,
            "vmpl": 0,
            "signature_algo": 1,  # ECDSA P-384
            "platform_version": "03000000000000000B000000000000000D000000000000000F00000000000000",
            "platform_info": 0x0001000000000000,
            "flags": 0x0000000000000000,
            "committed_svn": 0,
            "committed_version": 0,
            "launch_svn": 0,
            "measurement": self.measurements.get("measurement"),
            "host_data": hashlib.sha256(nonce).hexdigest()[:64],
            "id_key_digest": hashlib.sha384(b"vigil-id-key").hexdigest(),
            "author_key_digest": hashlib.sha384(b"vigil-author-key").hexdigest(),
            "report_id": report_id,
            "report_id_ma": report_id
        }
        
        # Mock report signature
        report_signature = base64.b64encode(
            hashlib.sha384(json.dumps(report_data, sort_keys=True).encode()).digest()
        ).decode()
        
        return {
            "type": "sev",
            "tee_type": self.tee_type.value,
            "report_id": report_id,
            "report": base64.b64encode(json.dumps(report_data).encode()).decode(),
            "signature": report_signature,
            "signature_algorithm": "ECDSA-P384",
            "measurement": self.measurements.get("measurement"),
            "policy": self.measurements.get("policy"),
            "guest_svn": int(self.measurements.get("guest_svn", 1)),
            "nonce": base64.b64encode(nonce).decode(),
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "instance_id": self.instance_id
        }
    
    def _generate_tdx_quote(self, nonce: bytes) -> Dict[str, Any]:
        """Generate Intel TDX attestation quote
        
        Returns properly-structured quote for AgentShield verification.
        """
        quote_id = hashlib.sha256(nonce + self.instance_id.encode()).hexdigest()[:16]
        quote_data = {
            "version": 4,
            "tee_type": 2,  # TDX
            "pce_svn": 12,
            "cpusvn": "0" * 32,
            "tdx_module_identifier": "03060402",
            "mr_td": self.measurements.get("mrtd"),
            "mr_td_commit": hashlib.sha384(b"vigil-mr-td-commit").hexdigest(),
            "mr_config_id": "0" * 96,
            "mr_owner": hashlib.sha384(b"vigil-owner").hexdigest(),
            "mr_owner_config": "0" * 96,
            "rtmr0": self.measurements.get("rtmr0"),
            "rtmr1": self.measurements.get("rtmr1"),
            "rtmr2": hashlib.sha384(b"vigil-rtmr2").hexdigest(),
            "rtmr3": hashlib.sha384(b"vigil-rtmr3").hexdigest(),
            "report_data": hashlib.sha256(nonce).hexdigest()[:64],
            "tdx_svn": int(self.measurements.get("tdx_svn", 1)),
            "pce_svn": 12,
            "xfam": "0" * 16
        }
        
        # Mock quote signature
        quote_signature = base64.b64encode(
            hashlib.sha384(json.dumps(quote_data, sort_keys=True).encode()).digest()
        ).decode()
        
        return {
            "type": "tdx",
            "tee_type": self.tee_type.value,
            "quote_id": quote_id,
            "quote": base64.b64encode(json.dumps(quote_data).encode()).decode(),
            "signature": quote_signature,
            "signature_algorithm": "ECDSA-P384",
            "mrtd": self.measurements.get("mrtd"),
            "rtmr0": self.measurements.get("rtmr0"),
            "rtmr1": self.measurements.get("rtmr1"),
            "tdx_svn": int(self.measurements.get("tdx_svn", 1)),
            "nonce": base64.b64encode(nonce).decode(),
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "instance_id": self.instance_id
        }
    
    def _generate_azure_quote(self, nonce: bytes) -> Dict[str, Any]:
        """Generate Azure Confidential Compute attestation token
        
        Returns properly-structured token for AgentShield verification.
        """
        token_id = hashlib.sha256(nonce + self.instance_id.encode()).hexdigest()[:16]
        token_payload = {
            "aud": "https://attest.azure.net",
            "exp": int(time.time()) + 3600,
            "iat": int(time.time()),
            "iss": "https://attest.azure.net",
            "jti": token_id,
            "cnf": {
                "x5c": [base64.b64encode(hashlib.sha256(b"vigil-cert").digest()).decode()]
            },
            "tee": "sev-snp",
            "is_debuggable": False,
            "hwmodel": "EPYC",
            "hwversion": "2.12",
            "vmid": self.measurements.get("vm_id"),
            "vmsize": self.measurements.get("vm_size"),
            "ostype": "linux",
            "nonce": base64.b64encode(nonce).decode(),
            "sev_snp_fw_version": "0.0.0.0",
            "guest_svn": 1,
            "policy": 0,
            "measurement": hashlib.sha384(b"vigil-sev-measurement").hexdigest()
        }
        
        # Create JWT-like token (not real JWT, just structured for demo)
        token_sig = base64.b64encode(
            hashlib.sha256(json.dumps(token_payload, sort_keys=True).encode()).digest()
        ).decode()
        
        return {
            "type": "azure",
            "tee_type": self.tee_type.value,
            "token_id": token_id,
            "token": base64.b64encode(json.dumps(token_payload).encode()).decode(),
            "signature": token_sig,
            "signature_algorithm": "RS256",
            "vm_id": self.measurements.get("vm_id"),
            "vm_size": self.measurements.get("vm_size"),
            "location": self.measurements.get("location"),
            "nonce": base64.b64encode(nonce).decode(),
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "instance_id": self.instance_id
        }
    
    
    def get_measurements(self) -> Dict[str, str]:
        """Get current enclave/VM measurements
        
        Returns:
            Platform-specific measurements (MRENCLAVE, MRSIGNER, MRTD, etc.)
        """
        return self.measurements
    
    def verify_measurement_policy(self, measurements: Optional[Dict[str, str]] = None) -> bool:
        """Verify measurements against local allow-list
        
        Args:
            measurements: Measurements from remote party (e.g., AgentShield).
                         If not provided, uses local measurements.
        
        Returns:
            True if measurements are in allow-list, False otherwise
        """
        # Use local measurements if not provided
        if measurements is None:
            measurements = self.measurements
        
        policy_path = os.getenv("VIGIL_TEE_MEASUREMENT_POLICY", "/app/measurements.json")
        if not os.path.exists(policy_path):
            if self.enabled:
                print(f"⚠ No measurement policy found at {policy_path}, allowing all (INSECURE)")
            return True
        
        try:
            with open(policy_path, 'r') as f:
                policy = json.load(f)
        except Exception as e:
            print(f"✗ Failed to load measurement policy: {e}")
            return False
        
        if self.tee_type == TEEType.SGX:
            allowed = policy.get("sgx", {}).get("allowed_mrenclaves", [])
            remote_mrenclave = measurements.get("mrenclave")
            if remote_mrenclave in allowed:
                return True
        elif self.tee_type == TEEType.SEV:
            allowed = policy.get("sev", {}).get("allowed_measurements", [])
            remote_measurement = measurements.get("measurement")
            if remote_measurement in allowed:
                return True
        elif self.tee_type == TEEType.TDX:
            allowed = policy.get("tdx", {}).get("allowed_mrtds", [])
            remote_mrtd = measurements.get("mrtd")
            if remote_mrtd in allowed:
                return True
        else:
            return True
        
        print(f"✗ Remote measurements not in allow-list (platform={self.tee_type})")
        return False
    
    def validate_attestation_quote(self, quote: Dict[str, Any]) -> bool:
        """Validate attestation quote structure and fields
        
        Args:
            quote: Quote dictionary from generate_attestation_quote()
        
        Returns:
            True if quote is valid, False otherwise
        """
        required_fields = ["type", "tee_type", "timestamp", "instance_id", "nonce"]
        
        for field in required_fields:
            if field not in quote:
                print(f"✗ Missing required field in attestation quote: {field}")
                return False
        
        # Verify nonce is base64-encoded
        try:
            base64.b64decode(quote["nonce"])
        except Exception:
            print("✗ Invalid nonce encoding (not base64)")
            return False
        
        # Verify timestamp format
        try:
            datetime.fromisoformat(quote["timestamp"].replace("Z", "+00:00"))
        except Exception:
            print("✗ Invalid timestamp format")
            return False
        
        # Verify platform-specific fields
        if quote["type"] == "sgx" and "mrenclave" not in quote:
            print("✗ Missing mrenclave in SGX quote")
            return False
        elif quote["type"] == "sev" and "measurement" not in quote:
            print("✗ Missing measurement in SEV quote")
            return False
        elif quote["type"] == "tdx" and "mrtd" not in quote:
            print("✗ Missing mrtd in TDX quote")
            return False
        
        return True


# Example measurement policy file (measurements.json):
"""
{
  "sgx": {
    "allowed_mrenclaves": [
      "abc123...",  // AgentShield enclave v1.0
      "def456..."   // AgentShield enclave v1.1
    ]
  },
  "sev": {
    "allowed_measurements": [
      "xyz789..."  // AgentShield SEV VM v1.0
    ]
  },
  "tdx": {
    "allowed_mrtds": [
      "uvw012..."  // AgentShield TDX VM v1.0
    ]
  }
}
"""
