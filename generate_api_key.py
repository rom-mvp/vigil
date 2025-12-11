#!/usr/bin/env python3
"""
Vigil API Key Generator
Generates secure API keys for dashboard access
"""

import secrets
import hashlib
import json
import os
from datetime import datetime

def generate_api_key():
    """Generate a secure API key"""
    # Format: sk-vigil-<32 random hex characters>
    random_part = secrets.token_hex(32)
    api_key = f"sk-vigil-{random_part}"
    return api_key

def hash_api_key(api_key):
    """Create a secure hash of the API key for storage"""
    return hashlib.sha256(api_key.encode()).hexdigest()

def save_api_key(api_key, username="admin", description=""):
    """Save API key hash to file"""
    keys_file = "api_keys.json"
    
    # Load existing keys
    if os.path.exists(keys_file):
        with open(keys_file, 'r') as f:
            keys_data = json.load(f)
    else:
        keys_data = {"keys": []}
    
    # Add new key
    key_hash = hash_api_key(api_key)
    keys_data["keys"].append({
        "hash": key_hash,
        "username": username,
        "description": description,
        "created_at": datetime.utcnow().isoformat(),
        "active": True
    })
    
    # Save to file
    with open(keys_file, 'w') as f:
        json.dump(keys_data, f, indent=2)
    
    return key_hash

def main():
    print("🔐 Vigil API Key Generator\n")
    
    # Get user input
    username = input("Enter username (default: admin): ").strip() or "admin"
    description = input("Enter key description (optional): ").strip()
    
    # Generate key
    api_key = generate_api_key()
    key_hash = save_api_key(api_key, username, description)
    
    print("\n✅ API Key Generated Successfully!")
    print("=" * 60)
    print(f"API Key: {api_key}")
    print("=" * 60)
    print("\n⚠️  IMPORTANT: Save this key now! It won't be shown again.")
    print(f"\nKey Hash (stored): {key_hash[:16]}...")
    print(f"Username: {username}")
    print(f"Description: {description or 'N/A'}")
    print(f"\n💡 Use this key in the Authorization header:")
    print(f"   Authorization: Bearer {api_key}")
    print("\nOr set as environment variable:")
    print(f"   export VIGIL_API_KEY={api_key}")

if __name__ == "__main__":
    main()
