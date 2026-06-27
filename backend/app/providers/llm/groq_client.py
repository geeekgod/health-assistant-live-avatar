import json
import httpx
from app.config import settings

class GroqClient:
    def __init__(self):
        self.base_url = "https://api.groq.com/openai/v1"
        self.api_key = settings.GROQ_API_KEY
        self.model = "llama-3.3-70b-versatile"

    async def complete_json(self, prompt: str) -> dict:
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.3,
            "max_tokens": 500,
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{self.base_url}/chat/completions",
                json=payload,
                headers=headers,
            )
            response.raise_for_status()
            data = response.json()

        content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
        if not content:
            return {}

        content = content.strip()
        if content.startswith("```json"):
            content = content.replace("```json", "").replace("```", "").strip()
        elif content.startswith("```"):
            content = content.replace("```", "").strip()

        try:
            return json.loads(content)
        except json.JSONDecodeError:
            return {}
