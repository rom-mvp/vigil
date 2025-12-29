#!/usr/bin/env python3
"""Vigil API Key Generator.

Generates API keys for Vigil. In SaaS mode keys are stored in Redis as the
source of truth; in other modes keys are hashed into api_keys.json."""

import secrets
import hashlib
import json
import os
import time
from datetime import datetime

import redis

def generate_api_key():
    """Generate a secure API key with vk_ prefix."""
    random_part = secrets.token_hex(32)
    api_key = f"vk_{random_part}"
    return api_key

def hash_api_key(api_key):
    """Create a secure hash of the API key for storage"""
    return hashlib.sha256(api_key.encode()).hexdigest()

def _save_key_file(api_key, username="admin", description=""):
    """Save API key hash to api_keys.json (non-SaaS)."""
    keys_file = "api_keys.json"

    if os.path.exists(keys_file):
        with open(keys_file, 'r') as f:
            keys_data = json.load(f)
    else:
        keys_data = {"keys": []}

    key_hash = hash_api_key(api_key)
    keys_data["keys"].append({
        "hash": key_hash,
        "username": username,
        "description": description,
        "created_at": datetime.utcnow().isoformat(),
        "active": True
    })

    with open(keys_file, 'w') as f:
        json.dump(keys_data, f, indent=2)

    return key_hash


def _save_key_redis(api_key, tenant_id, username="admin"):
    """Store raw key in Redis (SaaS mode)."""
    redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
    client = redis.from_url(redis_url, decode_responses=True)
    client.hset(
        f"api_keys:{api_key}",
        mapping={
            "tenant_id": tenant_id,
            "username": username,
            "active": "true",
            "created_at": str(int(time.time())),
        },
    )
    client.sadd(f"tenant:{tenant_id}:keys", api_key)


def save_api_key(api_key, username="admin", description="", tenant_id=None):
    """Persist API key depending on mode."""
    saas_mode = os.environ.get("VIGIL_MODE", "").lower() == "saas"
    if saas_mode:
        if not tenant_id:
            raise ValueError("tenant_id is required in SaaS mode")
        _save_key_redis(api_key, tenant_id, username)
        return api_key

    # Non-SaaS path: keep legacy file-based storage (hashed)
    return _save_key_file(api_key, username, description)

def main():
    print("🔐 Vigil API Key Generator\n")
    
    # Get user input
    username = input("Enter username (default: admin): ").strip() or "admin"
    description = input("Enter key description (optional): ").strip()

    saas_mode = os.environ.get("VIGIL_MODE", "").lower() == "saas"
    tenant_id = None
    if saas_mode:
        tenant_id = input("Enter tenant_id (required for SaaS): ").strip()
        if not tenant_id:
            raise SystemExit("tenant_id is required in SaaS mode")
    
    # Generate key
    api_key = generate_api_key()
    key_identifier = save_api_key(api_key, username, description, tenant_id=tenant_id)
    
    print(f"\n✅ API Key Generated Successfully!")
    print("=" * 60)
    print(f"API Key: {api_key}")
    print("=" * 60)
    print("\n⚠️  IMPORTANT: Save this key now! It won't be shown again.")
    if saas_mode:
        print("\nStored in Redis as raw key (vk_ prefix).")
    else:
        print(f"\nKey Hash (stored): {key_identifier[:16]}...")
    print(f"Username: {username}")
    if tenant_id:
        print(f"Tenant ID: {tenant_id}")
    print(f"Description: {description or 'N/A'}")
    print(f"\n💡 Use this key in the Authorization header:")
    print(f"   Authorization: Bearer {api_key}")
    print("\nOr set as environment variable:")
    print(f"   export VIGIL_API_KEY={api_key}")

if __name__ == "__main__":
    main()
