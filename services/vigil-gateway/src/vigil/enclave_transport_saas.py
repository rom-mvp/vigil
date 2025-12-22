"""
Vigil Gateway - EnclaveTransport with SaaS Multi-Tenancy
Now uses shared schemas and supports tenant isolation
"""

import os
import time
import json
import socket
import requests
from typing import Dict, Optional

# Import shared schemas (The Contract)
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../..'))

from shared.schemas.protocol import EnclaveRequest, EnclaveResponse, DecryptedPayload
from shared.crypto import HPKECrypto, compute_hash
from shared.errors import VigilError, ErrorCode


class EnclaveTransport:
    """
    The Gateway's connection to the AgentShield Enclave
    Handles HPKE encryption and VSOCK/HTTP transport
    """
    
    def __init__(self, cid: int = 88, port: int = 5000):
        self.cid = cid
        self.port = port
        
        # Get enclave URL from environment (Docker Compose sets this)
        self.enclave_url = os.getenv("ENCLAVE_URL", "http://localhost:5000")
        
        # Initialize HPKE crypto
        self.crypto = HPKECrypto()
        
        print(f"🔐 EnclaveTransport initialized")
        print(f"   VSOCK CID: {self.cid}, Port: {self.port}")
        print(f"   HTTP Fallback: {self.enclave_url}")
    
    def send_secure(
        self,
        payload: Dict,
        tenant_id: str,
        agent_id: str,
        request_id: Optional[str] = None
    ) -> EnclaveResponse:
        """
        Send encrypted payload to enclave for analysis
        Now tenant-aware for SaaS multi-tenancy
        
        Args:
            payload: The prompt data to analyze
            tenant_id: SaaS customer ID (CRITICAL for isolation)
            agent_id: End-user agent identifier
            request_id: Trace ID for distributed logging
        
        Returns:
            EnclaveResponse with decision and signature
        """
        if request_id is None:
            request_id = f"req_{int(time.time() * 1000)}"
        
        # 1. Encrypt the payload using HPKE
        encrypted_blob = self.crypto.encrypt(payload)
        
        # 2. Build the strict SaaS request packet
        packet = EnclaveRequest(
            request_id=request_id,
            tenant_id=tenant_id,  # <--- CRITICAL: Tenant isolation
            agent_id=agent_id,
            payload_encrypted=encrypted_blob.decode('utf-8'),
            timestamp=time.time(),
            schema_version="1.0"
        )
        
        # 3. Attempt connection (VSOCK first, HTTP fallback)
        try:
            # Try VSOCK connection (production mode)
            return self._connect_vsock(packet)
        except (AttributeError, OSError, socket.error):
            # Fallback to HTTP (local development)
            return self._connect_http(packet)
    
    def _connect_vsock(self, packet: EnclaveRequest) -> EnclaveResponse:
        """
        Connect via VSOCK (AWS Nitro Enclaves, Azure Confidential VMs)
        """
        if not hasattr(socket, 'AF_VSOCK'):
            raise AttributeError("VSOCK not available on this platform")
        
        sock = socket.socket(socket.AF_VSOCK, socket.SOCK_STREAM)
        sock.connect((self.cid, self.port))
        
        # Send packet as JSON
        sock.sendall(packet.json().encode())
        
        # Receive response
        response_data = sock.recv(65536)
        sock.close()
        
        response_dict = json.loads(response_data.decode())
        return EnclaveResponse(**response_dict)
    
    def _connect_http(self, packet: EnclaveRequest) -> EnclaveResponse:
        """
        HTTP fallback for local development
        Docker DNS resolves 'agentshield-enclave' hostname
        """
        try:
            response = requests.post(
                f"{self.enclave_url}/v1/enforce",
                json=packet.dict(),
                timeout=10,
                headers={"Content-Type": "application/json"}
            )
            
            if response.status_code == 200:
                return EnclaveResponse(**response.json())
            else:
                raise VigilError(
                    code=ErrorCode.ENCLAVE_UNAVAILABLE,
                    message=f"Enclave returned {response.status_code}",
                    tenant_id=packet.tenant_id
                )
        
        except requests.exceptions.ConnectionError as e:
            raise VigilError(
                code=ErrorCode.VSOCK_CONNECTION_FAILED,
                message="Cannot connect to enclave",
                tenant_id=packet.tenant_id,
                details={"error": str(e)}
            )
    
    def health_check(self) -> bool:
        """
        Check if enclave is reachable
        """
        try:
            response = requests.get(f"{self.enclave_url}/health", timeout=2)
            return response.status_code == 200
        except:
            return False
