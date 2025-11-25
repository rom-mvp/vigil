"""Tiny sample that shows how to point the official OpenAI SDK at Vigil."""

from __future__ import annotations

import os
from textwrap import dedent

from openai import OpenAI


def build_client() -> OpenAI:
    """Instantiate the OpenAI client with the Vigil gateway as the base URL."""
    base_url = os.getenv("VIGIL_GATEWAY_URL", "http://localhost:8000/v1")
    api_key = os.getenv("VIGIL_GATEWAY_KEY", "sk-demo")

    return OpenAI(
        base_url=base_url,
        api_key=api_key,
    )


def run_demo() -> None:
    """Send a canary request through the Vigil gateway so it reaches AgentShield."""
    client = build_client()
    tenant_id = os.getenv("VIGIL_TENANT_ID", "demo-enterprise")
    model = os.getenv("VIGIL_MODEL", "gpt-4o-mini")

    prompt = dedent(
        """
        My name is Jane Doe and I live in Paris. 
        Generate a short onboarding message for the AgentShield team.
        """
    ).strip()

    response = client.chat.completions.create(
        model=model,
        temperature=0.2,
        messages=[
            {"role": "system", "content": "You are an AI assistant secured by AgentShield."},
            {"role": "user", "content": prompt},
        ],
        extra_body={
            "metadata": {"tenant_id": tenant_id, "labels": ["demo", "agentshield"]},
            "shield": {"redact_pii": True, "capture_trace": True},
        },
    )

    print("Vigil gateway response:")
    print(response.choices[0].message.content)


if __name__ == "__main__":
    run_demo()
