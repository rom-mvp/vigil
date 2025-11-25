import asyncio
import httpx

GATEWAY_URL = "http://localhost:8000/v1/chat/completions"  # your AgentShield gateway
AGENTSHIELD_API_KEY = "YOUR_AGENT_API_KEY"  # from identity-service


async def main():
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            GATEWAY_URL,
            headers={"Authorization": f"Bearer {AGENTSHIELD_API_KEY}"},
            json={
                "model": "gpt-4o-mini",
                "messages": [
                    {"role": "user", "content": "Hello from a secured agent via Vigil example"}
                ],
            },
        )
        print(resp.json())


if __name__ == "__main__":
    asyncio.run(main())
