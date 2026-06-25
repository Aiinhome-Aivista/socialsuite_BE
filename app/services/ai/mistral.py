"""
Unified Mistral interface.

MISTRAL_MODE=cloud -> official Mistral La Plateforme SDK
MISTRAL_MODE=local -> any OpenAI-compatible endpoint (Ollama, vLLM, mistral.rs)

Both paths expose the same `chat()` method so the rest of the app never
needs to know where the model runs.
"""
from __future__ import annotations

import httpx
from app.config import settings


class MistralClient:
    def __init__(self) -> None:
        self.mode = settings.MISTRAL_MODE.lower()

    # ---- public API ----
    def chat(self, system: str, user: str, temperature: float = 0.7, max_tokens: int = 800) -> str:
        if self.mode == "cloud":
            return self._chat_cloud(system, user, temperature, max_tokens)
        return self._chat_local(system, user, temperature, max_tokens)

    # ---- cloud (Mistral SDK) ----
    def _chat_cloud(self, system: str, user: str, temperature: float, max_tokens: int) -> str:
        from mistralai import Mistral  # imported lazily so local mode needs no key

        if not settings.MISTRAL_API_KEY:
            raise RuntimeError("MISTRAL_API_KEY not configured for cloud mode")
        client = Mistral(api_key=settings.MISTRAL_API_KEY)
        resp = client.chat.complete(
            model=settings.MISTRAL_CLOUD_MODEL,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return resp.choices[0].message.content.strip()

    # ---- local (OpenAI-compatible OR Ollama native) ----
    def _chat_local(self, system: str, user: str, temperature: float, max_tokens: int) -> str:
        base = settings.MISTRAL_LOCAL_URL or settings.MISTRAL_LOCAL_BASE_URL
        base = base.rstrip("/")
        
        is_ollama_native = "api/generate" in base
        
        if is_ollama_native:
            url = base
            payload = {
                "model": settings.MISTRAL_LOCAL_MODEL,
                "prompt": f"{system}\n\n{user}",
                "stream": False,
                "options": {
                    "temperature": temperature,
                    "num_predict": max_tokens
                }
            }
        else:
            if base.endswith("/v1"):
                url = base + "/chat/completions"
            elif base.endswith("/chat/completions"):
                url = base
            else:
                url = base + "/v1/chat/completions"

            payload = {
                "model": settings.MISTRAL_LOCAL_MODEL,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "temperature": temperature,
                "max_tokens": max_tokens,
            }

        with httpx.Client(timeout=120) as c:
            r = c.post(url, json=payload)
            if r.status_code != 200:
                raise RuntimeError(f"AI Server Error ({r.status_code}): {r.text}")
            data = r.json()
            
        if is_ollama_native:
            return data["response"].strip()
        else:
            return data["choices"][0]["message"]["content"].strip()


mistral = MistralClient()
