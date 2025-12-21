"""
vsock Transport for TEE Communication
Provides socket wrapper for Vigil <-> AgentShield enclave communication via vsock.

vsock (Virtual Socket) is a low-latency transport for VM-to-VM or VM-to-Host communication,
commonly used with TEE enclaves (SGX, SEV, TDX).
"""

import socket
import json
import struct
import os
from typing import Optional, Dict, Any


class VsockTransport:
    """vsock client for connecting to AgentShield enclave"""
    
    def __init__(self):
        self.cid = int(os.getenv("AGENTSHIELD_VSOCK_CID", "3"))  # Enclave CID
        self.port = int(os.getenv("AGENTSHIELD_VSOCK_PORT", "9000"))
        self.timeout = float(os.getenv("AGENTSHIELD_TIMEOUT_MS", "1000")) / 1000.0
        self.sock: Optional[socket.socket] = None
        
        # Check if vsock is available
        self.available = self._check_vsock_available()
        if not self.available:
            print("⚠ vsock not available on this platform")
    
    def _check_vsock_available(self) -> bool:
        """Check if AF_VSOCK is supported"""
        try:
            # Try to create a vsock socket
            test_sock = socket.socket(socket.AF_VSOCK, socket.SOCK_STREAM)
            test_sock.close()
            return True
        except (AttributeError, OSError):
            return False
    
    def connect(self) -> bool:
        """Establish vsock connection to AgentShield enclave
        
        Returns:
            True if connected, False on failure
        """
        if not self.available:
            raise RuntimeError("vsock not available on this platform")
        
        try:
            self.sock = socket.socket(socket.AF_VSOCK, socket.SOCK_STREAM)
            self.sock.settimeout(self.timeout)
            
            # Connect to enclave
            # CID: Context ID of the enclave VM
            # Port: Port the enclave is listening on
            self.sock.connect((self.cid, self.port))
            print(f"✓ Connected to AgentShield enclave via vsock (CID={self.cid}, port={self.port})")
            return True
        except Exception as e:
            print(f"✗ Failed to connect to AgentShield enclave: {e}")
            if self.sock:
                self.sock.close()
                self.sock = None
            return False
    
    def send_message(self, message: Dict[str, Any]) -> bool:
        """Send JSON message to enclave
        
        Args:
            message: Dictionary to send (will be JSON-encoded)
        
        Returns:
            True if sent successfully, False on error
        """
        if not self.sock:
            raise RuntimeError("Not connected. Call connect() first.")
        
        try:
            # Serialize to JSON
            payload = json.dumps(message).encode('utf-8')
            
            # Send length prefix (4 bytes, big-endian)
            length = struct.pack('>I', len(payload))
            self.sock.sendall(length + payload)
            return True
        except Exception as e:
            print(f"✗ Failed to send message: {e}")
            return False
    
    def receive_message(self) -> Optional[Dict[str, Any]]:
        """Receive JSON message from enclave
        
        Returns:
            Parsed JSON dictionary, or None on error
        """
        if not self.sock:
            raise RuntimeError("Not connected. Call connect() first.")
        
        try:
            # Read length prefix (4 bytes)
            length_data = self._recv_exact(4)
            if not length_data:
                return None
            
            length = struct.unpack('>I', length_data)[0]
            
            # Read payload
            payload = self._recv_exact(length)
            if not payload:
                return None
            
            # Parse JSON
            return json.loads(payload.decode('utf-8'))
        except Exception as e:
            print(f"✗ Failed to receive message: {e}")
            return None
    
    def _recv_exact(self, n: int) -> Optional[bytes]:
        """Receive exactly n bytes from socket
        
        Args:
            n: Number of bytes to receive
        
        Returns:
            Bytes received, or None on error
        """
        data = b''
        while len(data) < n:
            chunk = self.sock.recv(n - len(data))
            if not chunk:
                return None
            data += chunk
        return data
    
    def close(self):
        """Close vsock connection"""
        if self.sock:
            try:
                self.sock.close()
            except Exception:
                pass
            self.sock = None
            print("✓ vsock connection closed")
    
    def __enter__(self):
        """Context manager entry"""
        self.connect()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        self.close()


def test_vsock_connection():
    """Quick test to verify vsock connectivity"""
    transport = VsockTransport()
    
    if not transport.available:
        print("vsock not available - skipping test")
        return
    
    try:
        with transport:
            # Send test message
            test_msg = {"type": "ping", "data": "hello"}
            if transport.send_message(test_msg):
                print("✓ Sent test message")
                
                # Receive response
                response = transport.receive_message()
                if response:
                    print(f"✓ Received response: {response}")
                else:
                    print("✗ No response received")
            else:
                print("✗ Failed to send test message")
    except Exception as e:
        print(f"✗ Test failed: {e}")


if __name__ == "__main__":
    test_vsock_connection()
