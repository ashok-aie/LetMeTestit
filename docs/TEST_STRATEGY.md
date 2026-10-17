# Test Strategy & Agent Evaluation
## Product Name: Let me TEST it....! (TestPilot AI Engine)
**Document Version:** 1.0.0  
**Status:** Approved Baseline  
**Date:** October 2026  

---

## 1. Multi-Tiered Testing Strategy

To guarantee that **Let me TEST it....!** is rock-solid and enterprise-grade, we establish a 6-layer testing pyramid:

```
                      / \
                     / E2E \           (Full Vertical Slice with Playwright & Demo App)
                    /-------\
                   / Security\         (Penetration, Prompt Injection & Allowlist Tests)
                  /-----------\
                 / Integration \       (Ollama Schema Contracts & Jira API Mock Adapters)
                /---------------\
               /   Component     \     (LangGraph State Transitions & Checkpointing)
              /-------------------\
             /     Unit Tests      \   (ADF Normalizer, Secret Redactor, Pydantic Models)
            /-----------------------\
```

### 1.1 Layer Breakdown
1. **Unit Tests (`tests/unit/`):**
   - Pure, deterministic, zero-network tests executing in `< 2 seconds`.
   - Tests: Atlassian Document Format (ADF) parser, prompt sanitization, secret redaction filter, Pydantic schema validation, and URL allowlist logic.
2. **Component Tests (`tests/component/`):**
   - Test LangGraph nodes in isolation.
   - Verify interrupt gates pause execution, SQLite checkpointer stores and restores graph state, and approval hash mismatches are caught.
3. **Integration Tests (`tests/integration/`):**
   - Test interactions with external sub-systems.
   - Ollama local contract test: Verifies that the local model generates schema-valid JSON without hallucinating invalid action types.
   - Jira API adapter tests: Verifies HTTP 200, 401, 404, and 429 rate limit backoff using mocked responses (`respx` or `pytest-mock`).
4. **Security & Guardrail Tests (`tests/safety/`):**
   - Explicit negative security suites.
   - Injection of prompt overrides in Jira fields: Ensures XML delimiters prevent instruction hijack.
   - Navigation to non-allowlisted domains: Verifies `SecurityPolicyViolation` is raised and browser is not launched.
   - Secret leakage tests: Asserts that API tokens and passwords never appear in logs or error traces.
5. **Browser Integration Tests (`tests/browser/`):**
   - Test Playwright execution engine against the local deterministic Task Management demo application (`http://localhost:8000`).
   - Verifies accessible locator resolution, explicit wait times, deterministic text assertions, and screenshot/trace artifact generation.
6. **End-to-End Vertical Slice (`tests/end_to_end/`):**
   - Exercises the entire pipeline: Input Jira story -> Extract ACs -> Generate tests -> Simulate human approval -> Execute in Playwright -> Classify results -> Generate defect draft.

---

## 2. Agent Quality & LLM Evaluation Framework

Unlike traditional software where unit tests either pass or fail, AI agent systems require continuous quality evaluation on non-deterministic language generation.

### 2.1 Evaluation Dataset (`tests/evals/dataset.json`)
We maintain a curated evaluation benchmark of 20 realistic Jira user stories across four tiers:
- **Tier 1: Clean Stories:** Clear summary, well-formatted Given-When-Then acceptance criteria.
- **Tier 2: Ambiguous Stories:** Vague criteria ("must be fast", missing error cases).
- **Tier 3: Complex Stories:** Multi-step workflows with tables, edge cases, and authorization constraints.
- **Tier 4: Adversarial Stories:** Injected prompt instructions, suspicious URLs, and malformed ADF trees.

### 2.2 Quantitative Agent Evaluation Metrics
| Metric | Formula | Target Threshold |
| :--- | :--- | :--- |
| **Schema Adherence Rate** | $\frac{\text{Valid Pydantic Outputs on 1st Attempt}}{\text{Total Generation Runs}} \times 100$ | **$\ge 90\%$** |
| **AC Traceability Coverage** | $\frac{\text{Extracted ACs with Valid Tests}}{\text{Total Extracted ACs}} \times 100$ | **$100\%$** |
| **Acceptance Rate** | $\frac{\text{Approved Test Cases}}{\text{Total Proposed Test Cases}} \times 100$ | **$\ge 80\%$** |
| **Hallucination Rate** | $\frac{\text{Tests with non-existent UI elements}}{\text{Total Generated Tests}} \times 100$ | **$\le 5\%$** |
| **Adversarial Rejection Rate**| $\frac{\text{Blocked Injections}}{\text{Attempted Injections}} \times 100$ | **$100\%$** |
| **Generation Latency** | Duration from prompt submission to validated Pydantic model | **$\le 45$ seconds** |

---

## 3. Failure & Chaos Scenarios Testing Matrix

| Chaos Scenario | Simulated Condition | Expected System Behavior |
| :--- | :--- | :--- |
| **Ollama Offline** | `localhost:11434` connection refused | Graceful error in UI: "Ollama is not running. Please run `ollama serve`." No crash. |
| **Jira Rate Limit (HTTP 429)** | Jira API returns 429 with `Retry-After: 3` | Client waits 3 seconds and retries (max 3 retries). Emits warning log. |
| **Target Web App Down** | Target demo app (`localhost:8000`) is offline | Playwright fails fast; classifies result as `BLOCKED (Environment Issue)`. |
| **Locator Ambiguity** | Multiple elements match the specified text | Engine detects multi-match; attempts Role disambiguation; if unresolved, fails with `ERROR (Locator Ambiguity)`. |
| **Mid-Workflow Crash / Restart** | User closes browser tab during execution | SQLite checkpoint preserves state; upon re-open, user can view logs or re-trigger run without losing generated tests. |

