#!/usr/bin/env python3
"""
Interactive API key generator for Vigil Gateway.
Prompts for tenant/name/description, stores to api_keys.json, and writes to Redis if available.
"""

import json
import secrets
import hashlib
import os
from datetime import datetime

import redis


def prompt(prompt_text: str, default: str) -> str:
    try:
        value = input(f"{prompt_text} [{default}]: ").strip()
        return value or default
    except EOFError:
        return default


def connect_redis():
    url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
    try:
        client = redis.from_url(url, decode_responses=True, socket_timeout=1.0, socket_connect_timeout=1.0)
        client.ping()
        return client
    except Exception:
        return None


def generate_api_key():
    # Collect metadata
    tenant_id = prompt("Tenant ID", "default-tenant")
    name = prompt("Name", "default-user")
    description = prompt("Description", "Auto-generated API key")

    # Generate cryptographically secure API key (API requires vk_ prefix)
    api_key = "vk_" + secrets.token_hex(32)
    key_hash = hashlib.sha256(api_key.encode()).hexdigest()

    key_data = {
        "created_at": datetime.now().isoformat(),
        "tenant_id": tenant_id,
        "name": name,
        "description": description,
        "status": "active",
    }

    # Persist to local file (fallback / audit)
    api_keys_file = "api_keys.json"
    try:
        with open(api_keys_file, "r") as f:
            all_keys = json.load(f)
    except Exception:
        all_keys = {}
    all_keys[key_hash] = key_data
    with open(api_keys_file, "w") as f:
        json.dump(all_keys, f, indent=2)

    # Write to Redis so the gateway can validate
    redis_client = connect_redis()
    if redis_client:
        redis_key = f"api_keys:{api_key}"
        redis_client.hset(redis_key, mapping={
            "tenant_id": tenant_id,
            "tenant_name": name,
            "tier": "pro",
            "status": "active",
            "created_at": key_data["created_at"],
        })
        redis_client.persist(redis_key)
        redis_status = "stored in Redis"
    else:
        redis_status = "Redis unavailable; key stored only in api_keys.json"

    print("=" * 70)
    print("✅ API Key Generated Successfully!")
    print("=" * 70)
    print(f"\n🔑 Your API Key (save this, it won't be shown again):\n")
    print(f"   {api_key}\n")
    print("=" * 70)
    print("\n📝 Key Details:")
    print(f"   Tenant ID: {tenant_id}")
    print(f"   Name: {name}")
    print(f"   Description: {description}")
    print(f"   Created: {key_data['created_at']}")
    print(f"   Redis: {redis_status}")
    print("\n💡 Usage:")
    print(f'   curl -H "Authorization: Bearer {api_key}" \\\n        -H "Content-Type: application/json" \\\n        -d "{{\\"model\\":\\"gpt-4\\",\\"messages\\":[{{\\"role\\":\\"user\\",\\"content\\":\\"hi\\"}}]}}" \\\n        http://localhost:8000/v1/chat/completions')
    print("\n" + "=" * 70)

    return api_key


if __name__ == "__main__":
    generate_api_key()
