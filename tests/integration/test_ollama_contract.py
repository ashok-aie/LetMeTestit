"""
Phase 2 Integration Test: Ollama Local Model Contract
Verifies that the Ollama daemon is reachable, qwen2.5:7b is loaded,
and returns valid structured JSON matching our Pydantic schema contract.
"""
import pytest
from pydantic import BaseModel, Field
from typing import List

from app.agents.llm_client import OllamaClient


class MiniTestStep(BaseModel):
    action: str
    target: str
    description: str


class MiniTestCase(BaseModel):
    test_id: str
    title: str
    category: str
    steps: List[MiniTestStep]
    expected_result: str


@pytest.fixture
def client():
    return OllamaClient()


@pytest.mark.integration
def test_ollama_health_and_model_presence(client: OllamaClient):
    """Verify Ollama is reachable and qwen2.5:7b is available."""
    assert client.is_healthy() is True, "Ollama daemon is not reachable on localhost:11434"
    models = client.list_models()
    assert any("qwen2.5:7b" in m for m in models), f"Expected qwen2.5:7b in {models}"


@pytest.mark.integration
def test_ollama_structured_json_generation(client: OllamaClient):
    """
    Verify qwen2.5:7b generates valid JSON adhering to schema constraints
    within acceptable latency bounds (< 45s).
    """
    system_prompt = (
        "You are an expert QA Automation Engineer. "
        "You must respond ONLY with a valid JSON object matching this schema: "
        '{"test_id": "TC-01", "title": "...", "category": "positive", '
        '"steps": [{"action": "click", "target": "submit-button", "description": "..."}], '
        '"expected_result": "..."}'
    )
    user_prompt = "Generate a single positive test case for verifying a user can submit a task named 'Buy milk'."

    response = client.generate(
        prompt=user_prompt,
        system_prompt=system_prompt,
        json_mode=True,
    )

    # 1. Assert response metadata
    assert response.latency_seconds > 0
    assert response.latency_seconds < 45.0, f"Inference took too long: {response.latency_seconds}s"
    assert response.content, "Response content was empty"

    # 2. Parse JSON
    parsed_json = response.parse_json()
    assert isinstance(parsed_json, dict)

    # 3. Pydantic validation
    test_case = MiniTestCase.model_validate(parsed_json)
    assert test_case.test_id == "TC-01"
    assert len(test_case.steps) > 0
    assert "milk" in test_case.title.lower() or "task" in test_case.title.lower()

