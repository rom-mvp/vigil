#!/usr/bin/env python3
"""
AgentShield Enclave Mock Service
=================================

This is a comprehensive mock implementation of the AgentShield enclave service
for development and testing. It simulates the behavior of a real TEE enclave
that verifies attestation quotes and makes access control decisions.

Architecture:
- Runs as a standalone Flask service
- Accepts attestation quotes from Vigil clients
- Verifies measurements against policy
- Returns signed decisions
- Supports both HTTP and vsock transport

Usage:
    python agentshield_enclave_mock.py

Environment Variables:
    AGENTSHIELD_PORT: HTTP port (default: 8443)
    AGENTSHIELD_VSOCK_PORT: vsock port (default: 5555)
    AGENTSHIELD_VSOCK_CID: vsock CID (default: 3)
    AGENTSHIELD_SIGNING_KEY: Path to Ed25519 private key
    AGENTSHIELD_MEASUREMENT_POLICY: Path to JSON measurement allow-list
"""

import os
import json
import socket
import struct
import hashlib
import base64
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from flask import Flask, request, jsonify
from threading import Thread
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('agentshield-enclave')

app = Flask(__name__)


class EnclaveConfig:
    """Configuration for the mock enclave"""
    def __init__(self):
        self.http_port = int(os.getenv('AGENTSHIELD_PORT', 8443))
        self.vsock_port = int(os.getenv('AGENTSHIELD_VSOCK_PORT', 5555))
        self.vsock_cid = int(os.getenv('AGENTSHIELD_VSOCK_CID', 3))
        self.signing_key_path = os.getenv('AGENTSHIELD_SIGNING_KEY')
        self.measurement_policy_path = os.getenv('AGENTSHIELD_MEASUREMENT_POLICY')
        
        # Load measurement policy
        self.measurement_policy = self._load_measurement_policy()
        
        # Generate or load signing key
        self.signing_key = self._load_signing_key()
        
    def _load_measurement_policy(self) -> Dict[str, List[str]]:
        """Load measurement allow-list from file"""
        if self.measurement_policy_path and os.path.exists(self.measurement_policy_path):
            with open(self.measurement_policy_path, 'r') as f:
                return json.load(f)
        
        # Default policy: accept any measurement in development mode
        logger.warning("No measurement policy loaded, accepting all measurements")
        return {
            "sgx_mrenclave": [],
            "sgx_mrsigner": [],
            "sev_measurement": [],
            "tdx_mrtd": [],
            "azure_measurement": []
        }
    
    def _load_signing_key(self) -> bytes:
        """Load or generate Ed25519 signing key"""
        if self.signing_key_path and os.path.exists(self.signing_key_path):
            with open(self.signing_key_path, 'rb') as f:
                return f.read()
        
        # Generate a deterministic key for testing
        # In production, this would be sealed to the enclave
        logger.warning("Generating deterministic signing key for testing")
        seed = hashlib.sha256(b"agentshield-mock-signing-key").digest()
        return seed


class AttestationVerifier:
    """Verifies TEE attestation quotes"""
    
    def __init__(self, config: EnclaveConfig):
        self.config = config
    
    def verify_quote(self, quote: Dict[str, Any]) -> Dict[str, Any]:
        """
        Verify an attestation quote
        
        Returns:
            dict: Verification result with status and details
        """
        try:
            # Extract quote fields
            tee_type = quote.get('tee_type')
            measurements = quote.get('measurements', {})
            timestamp = quote.get('timestamp')
            
            # Verify timestamp freshness (within 5 minutes)
            if not self._verify_timestamp(timestamp):
                return {
                    'verified': False,
                    'error': 'Quote timestamp too old or invalid',
                    'details': {'timestamp': timestamp}
                }
            
            # Verify platform-specific measurements
            if tee_type == 'sgx':
                return self._verify_sgx_quote(quote, measurements)
            elif tee_type == 'sev':
                return self._verify_sev_quote(quote, measurements)
            elif tee_type == 'tdx':
                return self._verify_tdx_quote(quote, measurements)
            elif tee_type == 'azure':
                return self._verify_azure_quote(quote, measurements)
            elif tee_type == 'none':
                # Accept non-TEE quotes in development mode
                logger.warning("Accepting non-TEE quote in development mode")
                return {
                    'verified': True,
                    'tee_type': 'none',
                    'warning': 'Non-TEE mode - insecure for production'
                }
            else:
                return {
                    'verified': False,
                    'error': f'Unknown TEE type: {tee_type}'
                }
                
        except Exception as e:
            logger.error(f"Quote verification error: {e}")
            return {
                'verified': False,
                'error': f'Verification exception: {str(e)}'
            }
    
    def _verify_timestamp(self, timestamp: str) -> bool:
        """Verify timestamp is fresh"""
        try:
            ts = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
            age = datetime.utcnow() - ts.replace(tzinfo=None)
            return age < timedelta(minutes=5)
        except:
            return False
    
    def _verify_sgx_quote(self, quote: Dict, measurements: Dict) -> Dict:
        """Verify Intel SGX quote"""
        mrenclave = measurements.get('mrenclave')
        mrsigner = measurements.get('mrsigner')
        
        # Check against policy
        policy = self.config.measurement_policy
        if policy.get('sgx_mrenclave') and mrenclave not in policy['sgx_mrenclave']:
            return {
                'verified': False,
                'error': 'MRENCLAVE not in allow-list',
                'details': {'mrenclave': mrenclave}
            }
        
        if policy.get('sgx_mrsigner') and mrsigner not in policy['sgx_mrsigner']:
            return {
                'verified': False,
                'error': 'MRSIGNER not in allow-list',
                'details': {'mrsigner': mrsigner}
            }
        
        return {
            'verified': True,
            'tee_type': 'sgx',
            'measurements': measurements,
            'tcb_status': 'UpToDate'
        }
    
    def _verify_sev_quote(self, quote: Dict, measurements: Dict) -> Dict:
        """Verify AMD SEV-SNP quote"""
        measurement = measurements.get('measurement')
        
        policy = self.config.measurement_policy
        if policy.get('sev_measurement') and measurement not in policy['sev_measurement']:
            return {
                'verified': False,
                'error': 'SEV measurement not in allow-list',
                'details': {'measurement': measurement}
            }
        
        return {
            'verified': True,
            'tee_type': 'sev',
            'measurements': measurements,
            'tcb_status': 'UpToDate'
        }
    
    def _verify_tdx_quote(self, quote: Dict, measurements: Dict) -> Dict:
        """Verify Intel TDX quote"""
        mrtd = measurements.get('mrtd')
        
        policy = self.config.measurement_policy
        if policy.get('tdx_mrtd') and mrtd not in policy['tdx_mrtd']:
            return {
                'verified': False,
                'error': 'MRTD not in allow-list',
                'details': {'mrtd': mrtd}
            }
        
        return {
            'verified': True,
            'tee_type': 'tdx',
            'measurements': measurements,
            'tcb_status': 'UpToDate'
        }
    
    def _verify_azure_quote(self, quote: Dict, measurements: Dict) -> Dict:
        """Verify Azure Confidential Compute quote"""
        vm_id = measurements.get('vm_id')
        
        # Azure quotes are JWT-like, we'd verify the signature here
        # For mock, we accept if it has required fields
        if not vm_id:
            return {
                'verified': False,
                'error': 'Missing vm_id in Azure quote'
            }
        
        return {
            'verified': True,
            'tee_type': 'azure',
            'measurements': measurements,
            'tcb_status': 'UpToDate'
        }


class DecisionEngine:
    """Makes access control decisions based on verified attestation"""
    
    def __init__(self, config: EnclaveConfig):
        self.config = config
    
    def make_decision(self, verification_result: Dict, request_data: Dict) -> Dict:
        """
        Make access control decision
        
        Args:
            verification_result: Result from AttestationVerifier
            request_data: Original request data
            
        Returns:
            dict: Decision with allow/deny and metadata
        """
        if not verification_result.get('verified'):
            return {
                'allow': False,
                'reason': 'Attestation verification failed',
                'verification': verification_result
            }
        
        # In production, this would enforce complex policies
        # For mock, we allow all verified requests
        decision = {
            'allow': True,
            'reason': 'Attestation verified successfully',
            'tee_type': verification_result.get('tee_type'),
            'tcb_status': verification_result.get('tcb_status'),
            'timestamp': datetime.utcnow().isoformat() + 'Z'
        }
        
        # Sign the decision
        signature = self._sign_decision(decision)
        decision['signature'] = signature
        
        return decision
    
    def _sign_decision(self, decision: Dict) -> str:
        """Sign decision with enclave key"""
        # Create deterministic signature
        decision_json = json.dumps(decision, sort_keys=True)
        signature_input = decision_json.encode() + self.config.signing_key
        signature_hash = hashlib.sha256(signature_input).digest()
        return base64.b64encode(signature_hash).decode()


# Global instances
config = EnclaveConfig()
verifier = AttestationVerifier(config)
decision_engine = DecisionEngine(config)


# HTTP API Endpoints

@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'service': 'agentshield-enclave-mock',
        'mode': 'development',
        'timestamp': datetime.utcnow().isoformat() + 'Z'
    })


@app.route('/v1/verify', methods=['POST'])
def verify_attestation():
    """
    Verify attestation quote and return decision
    
    Request body:
        {
            "quote": {...},           # Attestation quote
            "request": {...}          # Original request data
        }
    
    Response:
        {
            "decision": {...},        # Access control decision
            "verification": {...}     # Verification details
        }
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'Invalid JSON'}), 400
        
        quote = data.get('quote')
        request_data = data.get('request', {})
        
        if not quote:
            return jsonify({'error': 'Missing quote'}), 400
        
        logger.info(f"Verifying attestation quote from {quote.get('tee_type', 'unknown')}")
        
        # Verify the quote
        verification_result = verifier.verify_quote(quote)
        
        # Make decision
        decision = decision_engine.make_decision(verification_result, request_data)
        
        return jsonify({
            'decision': decision,
            'verification': verification_result
        })
        
    except Exception as e:
        logger.error(f"Verification error: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/v1/measurements', methods=['GET'])
def get_measurements():
    """
    Get enclave's own measurements
    
    Response:
        {
            "measurements": {...},
            "public_key": "..."
        }
    """
    # In a real enclave, this would return the enclave's own measurements
    # For mock, return deterministic values
    measurements = {
        'mrenclave': hashlib.sha256(b"agentshield-mock-enclave").hexdigest(),
        'mrsigner': hashlib.sha256(b"agentshield-mock-signer").hexdigest(),
        'timestamp': datetime.utcnow().isoformat() + 'Z'
    }
    
    # Derive public key from signing key
    public_key_hash = hashlib.sha256(config.signing_key).hexdigest()
    
    return jsonify({
        'measurements': measurements,
        'public_key': public_key_hash
    })


@app.route('/v1/policy', methods=['GET', 'POST'])
def measurement_policy():
    """
    Get or update measurement policy
    
    GET: Returns current policy
    POST: Updates policy (body: {"policy": {...}})
    """
    if request.method == 'GET':
        return jsonify({
            'policy': config.measurement_policy
        })
    else:
        try:
            data = request.get_json()
            new_policy = data.get('policy')
            if new_policy:
                config.measurement_policy = new_policy
                logger.info("Measurement policy updated")
                return jsonify({'status': 'updated'})
            else:
                return jsonify({'error': 'Missing policy'}), 400
        except Exception as e:
            return jsonify({'error': str(e)}), 500


# vsock Transport (Optional)

class VsockServer:
    """vsock server for low-latency communication"""
    
    def __init__(self, config: EnclaveConfig):
        self.config = config
        self.running = False
    
    def start(self):
        """Start vsock server"""
        try:
            # Check if vsock is available
            if not hasattr(socket, 'AF_VSOCK'):
                logger.warning("AF_VSOCK not available, skipping vsock server")
                return
            
            self.running = True
            sock = socket.socket(socket.AF_VSOCK, socket.SOCK_STREAM)
            sock.bind((self.config.vsock_cid, self.config.vsock_port))
            sock.listen(5)
            
            logger.info(f"vsock server listening on CID {self.config.vsock_cid} port {self.config.vsock_port}")
            
            while self.running:
                try:
                    conn, addr = sock.accept()
                    Thread(target=self._handle_vsock_client, args=(conn,)).start()
                except Exception as e:
                    if self.running:
                        logger.error(f"vsock accept error: {e}")
                        
        except Exception as e:
            logger.error(f"Failed to start vsock server: {e}")
    
    def _handle_vsock_client(self, conn):
        """Handle a vsock client connection"""
        try:
            # Receive length-prefixed message
            length_data = conn.recv(4)
            if not length_data:
                return
            
            length = struct.unpack('!I', length_data)[0]
            message_data = b''
            while len(message_data) < length:
                chunk = conn.recv(min(length - len(message_data), 4096))
                if not chunk:
                    break
                message_data += chunk
            
            # Parse JSON message
            message = json.loads(message_data.decode())
            
            # Process like HTTP endpoint
            quote = message.get('quote')
            request_data = message.get('request', {})
            
            verification_result = verifier.verify_quote(quote)
            decision = decision_engine.make_decision(verification_result, request_data)
            
            response = {
                'decision': decision,
                'verification': verification_result
            }
            
            # Send response
            response_data = json.dumps(response).encode()
            conn.send(struct.pack('!I', len(response_data)))
            conn.send(response_data)
            
        except Exception as e:
            logger.error(f"vsock client error: {e}")
        finally:
            conn.close()
    
    def stop(self):
        """Stop vsock server"""
        self.running = False


def main():
    """Run the mock enclave service"""
    logger.info("=" * 60)
    logger.info("AgentShield Enclave Mock Service")
    logger.info("=" * 60)
    logger.info(f"HTTP Port: {config.http_port}")
    logger.info(f"vsock CID: {config.vsock_cid}, Port: {config.vsock_port}")
    logger.info(f"Measurement Policy: {len(config.measurement_policy)} entries")
    logger.info("=" * 60)
    
    # Start vsock server in background
    vsock_server = VsockServer(config)
    vsock_thread = Thread(target=vsock_server.start, daemon=True)
    vsock_thread.start()
    
    # Run HTTP server
    app.run(
        host='0.0.0.0',
        port=config.http_port,
        debug=False
    )


if __name__ == '__main__':
    main()
