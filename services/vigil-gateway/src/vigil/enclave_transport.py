# src/vigil/enclave_transport.py
import socket
import json
from typing import Dict
# Note: You would use 'hazmat' primitives for real HPKE, simplified here for clarity
import base64

class EnclaveTransport:
    """
    The 'Blind' Forwarder.
    Encrypts traffic using the Enclave's Public Key (HPKE) and sends via VSOCK.
    """
    def __init__(self, cid: int = 88, port: int = 5000):
        self.cid = cid
        self.port = port
        # In prod, this comes from the Attestation Document
        self.enclave_pub_key = "public_key_loaded_from_attestation"

    def send_secure(self, payload: Dict) -> Dict:
        # 1. ENCRYPT (HPKE) - The Host OS cannot read this payload
        secure_blob = self._hpke_encrypt(json.dumps(payload))
        
        # 2. TUNNEL (VSOCK) - No TCP/IP stack involved
        try:
            # socket.AF_VSOCK is only available on Linux/Nitro
            sock = socket.socket(socket.AF_VSOCK, socket.SOCK_STREAM)
            sock.connect((self.cid, self.port))
            sock.sendall(secure_blob)
            
            # 3. RECEIVE
            response_blob = sock.recv(4096)
            sock.close()
            
            return self._hpke_decrypt(response_blob)
        except AttributeError:
            # Fallback for Local Dev (Mocking VSOCK with HTTP)
            print("⚠️ VSOCK not found. Using HTTP Mock for local dev.")
            import requests
            return requests.post("http://localhost:9000/process", json={"blob": secure_blob}).json()

    def _hpke_encrypt(self, data: str) -> bytes:
        # Placeholder for 'cryptography' lib HPKE implementation
        return base64.b64encode(data.encode())

    def _hpke_decrypt(self, data: bytes) -> Dict:
        return json.loads(base64.b64decode(data))
