#!/usr/bin/env python3
"""
Generate API Key for Vigil Gateway
Creates a new API key and stores it in api_keys.json
"""

import json
import secrets
import hashlib
import os
from datetime import datetime

def generate_api_key():
    """Generate a new API key with proper format."""
    # Generate cryptographically secure API key
    api_key = "vk-" + secrets.token_hex(32)
    
    # Hash the key for storage (in production, you'd store this in a database)
    key_hash = hashlib.sha256(api_key.encode()).hexdigest()
    
    # Create API key metadata
    key_data = {
        "created_at": datetime.now().isoformat(),
        "tenant_id": "default-tenant",
        "description": "Auto-generated API key",
        "active": True
    }
    
    # Load existing keys if file exists
    api_keys_file = "api_keys.json"
    if os.path.exists(api_keys_file):
        try:
            with open(api_keys_file, 'r') as f:
                all_keys = json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            all_keys = {}
    else:
        all_keys = {}
    
    # Add new key
    all_keys[key_hash] = key_data
    
    # Save to file
    with open(api_keys_file, 'w') as f:
        json.dump(all_keys, f, indent=2)
    
    print("=" * 70)
    print("✅ API Key Generated Successfully!")
    print("=" * 70)
    print(f"\n🔑 Your API Key (save this, it won't be shown again):\n")
    print(f"   {api_key}\n")
    print("=" * 70)
    print(f"\n📝 Key Details:")
    print(f"   Tenant ID: {key_data['tenant_id']}")
    print(f"   Created: {key_data['created_at']}")
    print(f"   Status: {'Active' if key_data['active'] else 'Inactive'}")
    print("\n💡 Usage:")
    print(f'   curl -H "Authorization: Bearer {api_key}" \\')
    print(f'        http://localhost:8000/v1/chat/completions')
    print("\n" + "=" * 70)
    
    return api_key

if __name__ == "__main__":
    generate_api_key()
