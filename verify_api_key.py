#!/usr/bin/env python3
"""
Verify API Key utility
"""

import hashlib
import json
import os
import sys

def hash_api_key(api_key):
    """Create a secure hash of the API key"""
    return hashlib.sha256(api_key.encode()).hexdigest()

def verify_api_key(api_key):
    """Verify if an API key is valid"""
    keys_file = "api_keys.json"
    
    if not os.path.exists(keys_file):
        return False, "No API keys configured"
    
    with open(keys_file, 'r') as f:
        keys_data = json.load(f)
    
    key_hash = hash_api_key(api_key)
    
    for key in keys_data.get("keys", []):
        if key["hash"] == key_hash and key.get("active", True):
            return True, {
                "username": key.get("username"),
                "created_at": key.get("created_at"),
                "description": key.get("description")
            }
    
    return False, "Invalid API key"

def main():
    if len(sys.argv) < 2:
        print("Usage: python verify_api_key.py <api-key>")
        sys.exit(1)
    
    api_key = sys.argv[1]
    valid, result = verify_api_key(api_key)
    
    if valid:
        print("✅ Valid API Key")
        print(f"Username: {result['username']}")
        print(f"Created: {result['created_at']}")
        print(f"Description: {result.get('description', 'N/A')}")
    else:
        print(f"❌ {result}")
        sys.exit(1)

if __name__ == "__main__":
    main()
