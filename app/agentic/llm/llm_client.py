"""
Multi-Provider LLM Client Adapter
Supports:
1. Local Ollama (e.g. qwen2.5:7b)
2. Groq Cloud API (e.g. qwen/qwen3.8-27b, openai/gpt-oss-120b)
3. Antigravity / Gemini Cloud API (e.g. gemini-3.5-flash, gemini-3.1-flash-lite)
Provides unified interface with timeout handling, latency measurement, and JSON enforcement.
"""
import time
import json
import re
from typing import Optional, Dict, Any, List
import httpx
from pydantic import BaseModel, Field

from app.config import settings

try:
    from langfuse import observe
except ImportError:
    def observe(*args, **kwargs):
        def decorator(f):
            return f
        return decorator


class LLMResponse(BaseModel):
    """Structured response from the LLM invocation."""
    content: str
    model: str
    latency_seconds: float
    total_tokens: Optional[int] = None
    raw_response: Dict[str, Any] = Field(default_factory=dict)

    def parse_json(self) -> Dict[str, Any]:
        """Safely parses content as JSON, stripping markdown code fences if present."""
        clean = self.content.strip()
        if clean.startswith("```"):
            clean = re.sub(r"^```(?:json)?\s*", "", clean)
            clean = re.sub(r"\s*```$", "", clean)
        return json.loads(clean.strip())


class LLMClientError(Exception):
    """Base exception for LLM client failures."""
    pass


class OllamaClientError(LLMClientError):
    """Base exception for Ollama client failures."""
    pass


class OllamaConnectionError(OllamaClientError):
    """Raised when Ollama daemon is unreachable."""
    pass


class OllamaTimeoutError(OllamaClientError):
    """Raised when Ollama inference exceeds the timeout."""
    pass


class OllamaClient:
    """Client for communicating with the local Ollama daemon."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        timeout: Optional[int] = None,
    ):
        self.base_url = (base_url or settings.ollama_base_url).rstrip("/")
        self.model = model or settings.ollama_model
        self.timeout = timeout or settings.ollama_timeout_seconds

    def is_healthy(self) -> bool:
        """Checks if the local Ollama daemon is active and responsive."""
        try:
            with httpx.Client(timeout=3.0) as client:
                res = client.get(f"{self.base_url}/api/tags")
                return res.status_code == 200
        except Exception:
            return False

    def list_models(self) -> List[str]:
        """Returns the list of installed model names."""
        try:
            with httpx.Client(timeout=3.0) as client:
                res = client.get(f"{self.base_url}/api/tags")
                res.raise_for_status()
                data = res.json()
                return [m.get("name") for m in data.get("models", []) if m.get("name")]
        except Exception as exc:
            raise OllamaConnectionError(f"Failed to list Ollama models: {exc}") from exc

    @observe(name="OllamaClient.generate", as_type="generation")
    def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        json_mode: bool = True,
        temperature: float = 0.1,
    ) -> LLMResponse:
        """Sends a generation request to Ollama and returns the structured LLMResponse."""
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": temperature,
            },
        }

        if json_mode:
            payload["format"] = "json"

        start_time = time.perf_counter()
        try:
            with httpx.Client(timeout=float(self.timeout)) as client:
                res = client.post(f"{self.base_url}/api/chat", json=payload)
                res.raise_for_status()
                data = res.json()
        except httpx.ConnectError as exc:
            raise OllamaConnectionError(
                f"Ollama server is unreachable at {self.base_url}. Ensure Ollama is running (`ollama serve`)."
            ) from exc
        except httpx.TimeoutException as exc:
            raise OllamaTimeoutError(
                f"Ollama inference timed out after {self.timeout} seconds for model '{self.model}'."
            ) from exc
        except Exception as exc:
            raise OllamaClientError(f"Ollama generation request failed: {exc}") from exc

        latency = time.perf_counter() - start_time
        message_content = data.get("message", {}).get("content", "")
        eval_count = data.get("eval_count")

        return LLMResponse(
            content=message_content,
            model=self.model,
            latency_seconds=round(latency, 3),
            total_tokens=eval_count,
            raw_response=data,
        )


class GroqClient:
    """Client for Groq Cloud API (fast inference via OpenAI-compatible API)."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "qwen/qwen3.8-27b",
        timeout: int = 60,
    ):
        self.api_key = (api_key or settings.groq_api_key or "").strip()
        self.model = model.strip()
        self.timeout = timeout
        self.base_url = "https://api.groq.com/openai/v1"

    def is_healthy(self) -> bool:
        try:
            with httpx.Client(timeout=4.0) as client:
                res = client.get(f"{self.base_url}/models", headers={"Authorization": f"Bearer {self.api_key}"})
                return res.status_code == 200
        except Exception:
            return False

    @observe(name="GroqClient.generate", as_type="generation")
    def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        json_mode: bool = True,
        temperature: float = 0.1,
    ) -> LLMResponse:
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}

        start_time = time.perf_counter()
        try:
            with httpx.Client(timeout=float(self.timeout)) as client:
                res = client.post(
                    f"{self.base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    json=payload,
                )
                res.raise_for_status()
                data = res.json()
        except Exception as exc:
            raise LLMClientError(f"Groq API generation failed: {exc}") from exc

        latency = time.perf_counter() - start_time
        choice = data.get("choices", [{}])[0]
        content = choice.get("message", {}).get("content", "")
        tokens = data.get("usage", {}).get("total_tokens")

        return LLMResponse(
            content=content,
            model=self.model,
            latency_seconds=round(latency, 3),
            total_tokens=tokens,
            raw_response=data,
        )


class AntigravityClient:
    """Client for Google Gemini / Antigravity Cloud API."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "gemini-3.5-flash",
        timeout: int = 60,
    ):
        self.api_key = (api_key or settings.antigravity_api_key or "").strip()
        self.model = model.strip()
        self.timeout = timeout
        self.base_url = "https://generativelanguage.googleapis.com/v1beta"

    def is_healthy(self) -> bool:
        try:
            with httpx.Client(timeout=4.0) as client:
                res = client.get(f"{self.base_url}/models?key={self.api_key}")
                return res.status_code == 200
        except Exception:
            return False

    @observe(name="AntigravityClient.generate", as_type="generation")
    def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        json_mode: bool = True,
        temperature: float = 0.1,
    ) -> LLMResponse:
        full_text = f"System Instructions:\n{system_prompt}\n\nTask:\n{prompt}" if system_prompt else prompt

        payload: Dict[str, Any] = {
            "contents": [{"parts": [{"text": full_text}]}],
            "generationConfig": {
                "temperature": temperature,
            },
        }
        if json_mode:
            payload["generationConfig"]["responseMimeType"] = "application/json"

        start_time = time.perf_counter()
        url = f"{self.base_url}/models/{self.model}:generateContent?key={self.api_key}"
        data = None
        max_attempts = 4
        last_exc = None
        for attempt in range(max_attempts):
            try:
                with httpx.Client(timeout=float(self.timeout)) as client:
                    res = client.post(url, json=payload)
                    if res.status_code in (429, 503, 500, 502):
                        wait_sec = (attempt + 1) * 2.5
                        logger.warning(
                            "Gemini API returned HTTP %s on attempt %d/%d; retrying in %.1fs...",
                            res.status_code,
                            attempt + 1,
                            max_attempts,
                            wait_sec,
                        )
                        time.sleep(wait_sec)
                        continue
                    res.raise_for_status()
                    data = res.json()
                    break
            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                last_exc = exc
                if attempt < max_attempts - 1:
                    wait_sec = (attempt + 1) * 2.0
                    logger.warning("Gemini network error on attempt %d: %s. Retrying in %.1fs...", attempt + 1, exc, wait_sec)
                    time.sleep(wait_sec)
                else:
                    raise LLMClientError(f"Antigravity/Gemini API request failed after {max_attempts} attempts: {exc}") from exc
            except Exception as exc:
                last_exc = exc
                if attempt < max_attempts - 1 and any(code in str(exc) for code in ["429", "503", "500", "502"]):
                    wait_sec = (attempt + 1) * 2.5
                    logger.warning("Gemini error %s on attempt %d. Retrying in %.1fs...", exc, attempt + 1, wait_sec)
                    time.sleep(wait_sec)
                else:
                    raise LLMClientError(f"Antigravity/Gemini API generation failed: {exc}") from exc

        if data is None:
            raise LLMClientError(f"Antigravity/Gemini API failed after {max_attempts} attempts: {last_exc}")

        latency = time.perf_counter() - start_time
        candidates = data.get("candidates", [{}])
        parts = candidates[0].get("content", {}).get("parts", [{}]) if candidates else [{}]
        content = parts[0].get("text", "")

        return LLMResponse(
            content=content,
            model=self.model,
            latency_seconds=round(latency, 3),
            total_tokens=data.get("usageMetadata", {}).get("totalTokenCount"),
            raw_response=data,
        )


def get_llm_client(
    provider: str = "Antigravity",
    model: Optional[str] = None,
    api_key: Optional[str] = None,
    timeout: int = 60,
):
    """Factory helper to construct the selected LLM client."""
    prov = (provider or "Antigravity").lower()
    if "groq" in prov:
        key = api_key or settings.groq_api_key
        mdl = model or "qwen/qwen3.8-27b"
        return GroqClient(api_key=key, model=mdl, timeout=timeout)
    elif "antigravity" in prov or "gemini" in prov:
        key = api_key or settings.antigravity_api_key
        mdl = model or "gemini-3.5-flash"
        return AntigravityClient(api_key=key, model=mdl, timeout=timeout)
    else:
        return OllamaClient(model=model, timeout=timeout)
