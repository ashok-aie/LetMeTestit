# Requirements Traceability Matrix (RTM)
## Product Name: Let me TEST it....! (TestPilot AI Engine)
**Document Version:** 1.0.0  
**Status:** Approved Baseline  
**Date:** October 2026  

---

## 1. Traceability Mapping

| Business Objective / KPI | BRD Requirement | FRD Requirement | Technical Component | Target Implementation File | Verification Test Scenario | Acceptance Criteria |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **KPI-01 (Test Gen < 3m)** | BP-1, BP-3 | FR-JIRA-001, FR-JIRA-002, FR-REQ-001 | Requirement Hub & Normalizer | `app/jira/client.py`, `app/requirements/normalizer.py` | `tests/unit/test_jira_client.py` | Fetches Jira ADF and normalizes to clean markdown in < 5s |
| **KPI-02 (Acceptance $\ge 80\%$)** | BP-2 | FR-REQ-002, FR-GEN-001 | Requirement Analyzer & Test Designer | `app/test_design/generator.py` | `tests/unit/test_generator.py` | Generates Pydantic `TestSuite` conforming to ACs |
| **KPI-03 (Traceability 100%)** | BP-7 | FR-GEN-002 | Coverage Checker | `app/test_design/coverage.py` | `tests/unit/test_coverage.py` | Every generated test maps to a source `AC-XX` |
| **KPI-04 (Flakiness < 5%)** | BP-4 | FR-EXEC-002 | Playwright Action Dispatcher & Locators | `app/browser/executor.py`, `app/browser/locators.py` | `tests/integration/test_browser_executor.py` | Accessible locators with retries eliminate selector flakiness |
| **KPI-05 (Evidence 100%)** | BP-6 | FR-EXEC-001, FR-TEL-001 | Evidence Collector | `app/browser/evidence.py` | `tests/integration/test_evidence_capture.py` | Generates screenshot + trace.zip for every failed test |
| **KPI-06 (Zero Breaches)** | BP-8 | FR-ENV-001, NFR-SEC-02 | Policy & Guardrails Engine | `app/policies/guardrails.py` | `tests/safety/test_policy_guardrails.py` | Blocks unallowlisted URLs; halts immediately |
| **KPI-07 (HITL 100%)** | BP-8 | FR-HITL-001, FR-HITL-002 | Review Center & Approval Gate | `app/agents/nodes/human_review.py` | `tests/unit/test_approval_gate.py` | Execution blocked until valid cryptographic approval record signed |
| **KPI-08 (MTTD < 5m)** | BP-5 | FR-RES-001 | Results Classifier | `app/reporting/classifier.py` | `tests/unit/test_classifier.py` | Distinguishes app defect from locator/network error |
| **KPI-09 (Ollama < 45s)** | BP-3 | FR-GEN-001, NFR-PERF-01 | Ollama Local Adapter | `app/agents/llm_client.py` | `tests/integration/test_ollama_contract.py` | Ollama model completes test generation < 45s |
| **Defect Creation** | BP-7 | FR-DEF-001 | Jira Defect Assistant | `app/jira/defects.py` | `tests/integration/test_defect_creation.py` | Creates linked Jira bug only after explicit human approval click |
| **State Persistence** | BP-7 | FR-TEL-001 | SQLite Repository & Checkpointer | `app/persistence/repository.py` | `tests/unit/test_persistence.py` | Recovers workflow state upon resume without re-running LLM |

---

## 2. Verification Coverage Summary

- **Unit Tests:** Verify individual functions (ADF parser, prompt sanitization, secret redactor, Pydantic schemas, policy validator).
- **Integration Tests:** Verify component interactions (Ollama JSON generation, Jira mock API client, SQLite transactions).
- **Safety / Guardrail Tests:** Explicit negative tests attempting prompt injections, unallowlisted domain navigation, and unapproved execution.
- **End-to-End Tests:** Complete vertical slice against the local demo web application (`tests/end_to_end/test_full_workflow.py`).

