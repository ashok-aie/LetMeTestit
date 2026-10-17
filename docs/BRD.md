# Business Requirements Document (BRD)
## Product Name: Let me TEST it....! (TestPilot AI Engine)
**Tagline:** From requirements to verified results.  
**Document Version:** 1.0.0  
**Status:** Approved Baseline  
**Date:** October 2026  

---

## 1. Executive Summary

### 1.1 Product Vision & Description
**Let me TEST it....!** (internally powered by the **TestPilot AI** core engine) is an enterprise-grade Agentic Quality Engineering Platform. It bridges the gap between agile product requirements (managed in Jira Cloud) and deterministic, resilient automated test execution in real web browsers via Playwright.

Unlike conventional test automation suites that rely on static, manually written script repositories—or naive "autonomous LLM agents" that hallucinate locators, execute arbitrary untrusted code, and wander across web domains—**Let me TEST it....!** implements a controlled, policy-governed agentic workflow. It couples:
1. **LLM-assisted Requirement Intelligence:** Synthesizing acceptance criteria, identifying ambiguities, and generating structured test cases with Pydantic validation.
2. **Mandatory Human-in-the-Loop (HITL) Governance:** Strict approval gates where human QA engineers review, refine, and sign off on test suites before any browser action occurs.
3. **Deterministic, Allowlisted Browser Execution:** Playwright execution using explicit, typed page objects and locators, strict timeout bounds, and deterministic assertions (no LLM in the runtime assertion loop).
4. **Rich Diagnostic Evidence & Traceability:** Automatic generation of video/trace/screenshot artifacts, structured telemetry, failure classification, and optional human-approved Jira defect creation.

### 1.2 Target Audience & Stakeholders
- **QA Engineers & Automation Engineers:** Drastically reduce test design time and eliminate brittle locator boilerplate.
- **QA Leads & Engineering Managers:** Gain end-to-end traceability from user stories to execution runs with audit trails.
- **Product Managers & Business Analysts:** Rapidly uncover ambiguous requirements and gaps in acceptance criteria early in the sprint.
- **Developers:** Receive reproducible, evidence-backed defect reports with exact network traces, console logs, and failure screenshots.

### 1.3 Key Differentiators vs Conventional Frameworks
| Capability | Conventional Playwright / Selenium | Uncontrolled "Autonomous" AI Web Agents | **Let me TEST it....!** |
| :--- | :--- | :--- | :--- |
| **Test Case Authoring** | 100% Manual scripting in TS/Python | Ad-hoc, freeform prompt generation | Structured Pydantic test cases generated from Jira ACs |
| **Execution Safety** | Deterministic scripts; static maintenance burden | High risk: arbitrary clicks, potential data destruction, prompt injection | Strict URL allowlists, sandboxed tools, no arbitrary code eval |
| **Human Governance** | Code review via PRs | Often absent; black-box decision making | Native HITL approval gates in LangGraph workflow |
| **Locator Strategy** | Hardcoded XPath/CSS selectors | Raw multimodal pixel coordinates (fragile) | Accessible ARIA roles, text, semantic test-IDs with fallback |
| **Defect Creation** | Manual Jira ticket logging by QA | Hallucinated or spam automated tickets | Structured defect drafts requiring explicit human approval |
| **Data Privacy** | Code is local; SaaS reporting risks | Uncontrolled data egress to cloud LLMs | Local LLM inference (Ollama/Qwen) with private telemetry |

---

## 2. Business Problems and Opportunities

| # | Business Problem in QA | Proposed Solution in Let me TEST it....! | Business Value |
| :--- | :--- | :--- | :--- |
| **BP-1** | **Manual Requirement Interpretation:** QA engineers spend hours parsing Jira stories; acceptance criteria are often incomplete or misconstrued. | LLM-driven Requirement Analyzer extracts explicit ACs, identifies ambiguities, and prompts for clarification before testing. | Reduces test planning cycle time by 60%; eliminates sprint misunderstandings. |
| **BP-2** | **Incomplete & Inconsistent Test Coverage:** Engineers rush to test happy paths, neglecting edge cases, boundaries, and validation scenarios. | Test Designer automatically synthesizes Positive, Negative, Boundary, and Validation suites mapped to each AC. | Increases requirement test coverage to 100% of defined acceptance criteria. |
| **BP-3** | **High Script Authoring Overhead:** Writing boilerplate Playwright/Selenium scripts takes days for every new feature. | Automated translation of approved test steps into structured, allowlisted browser tool calls. | Accelerates automation ramp-up from days to minutes per story. |
| **BP-4** | **Brittle Locators & Flaky Tests:** UI changes break brittle CSS/XPath selectors, creating high maintenance overhead. | Priority-based locator resolution (Accessible Role -> Text -> Semantic Test-ID) with retry backoffs and uniqueness validation. | Reduces locator flakiness by >75%. |
| **BP-5** | **Difficulty Distinguishing Defects from Test Flakes:** Teams waste hours debugging test script issues that look like application bugs. | Automated Failure Classifier categorizes outcomes into Application Defect, Locator Failure, Network/Timeout, or Data Issue. | Cuts Mean Time to Diagnose (MTTD) from hours to under 5 minutes. |
| **BP-6** | **Missing or Fragmented Evidence:** QA reports lack console logs, network traffic, or step-by-step visual proofs. | Comprehensive Evidence Manager packages DOM snapshots, console logs, network har, Playwright traces, and screenshots. | Provides developers with instant root-cause clarity; eliminates "cannot reproduce" tickets. |
| **BP-7** | **Traceability Deficit:** Audit teams cannot trace a failed test back to the exact Jira requirement version. | Bi-directional traceability: Jira Issue Key <-> Acceptance Criterion <-> Test Case ID <-> Execution Run <-> Defect. | 100% audit compliance for regulated engineering standards. |
| **BP-8** | **AI Safety & Uncontrolled Actions:** Autonomous agents can submit live payments, alter production data, or wander off-site. | Strict sandboxed execution engine with domain allowlists, destructive action blocking, and mandatory approval before write operations. | Zero risk of unauthorized external navigation or destructive transactions. |

---

## 3. Business Objectives and Success Metrics (KPIs)

| Metric ID | KPI Name | Formula / Measurement Method | Baseline (Traditional QA) | MVP Target | Frequency |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **KPI-01** | **Test Generation Cycle Time** | Time from entering Jira Key to reviewable Test Suite generated in UI. | 120 - 240 mins (Manual) | **< 3 minutes** | Per Jira Story |
| **KPI-02** | **Reviewer Acceptance Rate** | $\frac{\text{Approved Test Cases}}{\text{Total Generated Test Cases}} \times 100$ | N/A | **$\ge 80\%$** | Weekly / Per Release |
| **KPI-03** | **Traceability Coverage** | $\frac{\text{Acceptance Criteria with Associated Tests}}{\text{Total Extracted Acceptance Criteria}} \times 100$ | ~70% (Manual tracking) | **100%** | Per Test Run |
| **KPI-04** | **Execution Pass / Flakiness Ratio** | $\frac{\text{Flaky Runs}}{\text{Total Runs}} \times 100$ (Flaky = passes on retry without code change) | 15% - 25% | **< 5%** | Monthly aggregate |
| **KPI-05** | **Diagnostic Evidence Completeness** | $\frac{\text{Failed Tests with Screenshot + Trace + Log}}{\text{Total Failed Tests}} \times 100$ | ~40% | **100%** | Per Execution Run |
| **KPI-06** | **Unsafe Action Rejection Rate** | $\frac{\text{Blocked Unallowlisted Actions}}{\text{Attempted Unallowlisted Actions}} \times 100$ | N/A | **100% (Zero breaches)** | Continuous audit |
| **KPI-07** | **HITL Governance Compliance** | $\frac{\text{Runs with Validated Human Approval}}{\text{Total Execution Runs}} \times 100$ | N/A | **100%** | Continuous audit |
| **KPI-08** | **Mean Time to Diagnose (MTTD)** | Average time for an engineer to review failure evidence and identify root cause. | 45 minutes | **< 5 minutes** | Per defect |
| **KPI-09** | **Local LLM Inference Latency** | Time taken by local Ollama model to generate structured Pydantic test suite. | N/A | **< 45 seconds** (on Apple M-series / 16GB) | Per generation |
| **KPI-10** | **Local Resource Footprint** | Peak RAM consumption of combined Streamlit + LangGraph + Ollama + Playwright. | N/A | **< 12 GB RAM** | Continuous monitoring |

---

## 4. Scope of the System

### 4.1 In-Scope for Minimum Viable Product (MVP)
1. **Jira Cloud Integration:** Read issue by key (e.g. `PROJ-123`), parse rich-text / Atlassian Document Format (ADF), extract summary, description, labels, and acceptance criteria.
2. **Requirement Quality Assessment:** Detect ambiguities, missing preconditions, and unstated assumptions; flag quality score.
3. **Structured Test Generation:** Local LLM (Ollama with Qwen2.5/Qwen3) generates strictly typed Pydantic test suites containing Positive, Negative, Boundary, and Validation scenarios.
4. **Human Review & Approval (HITL):** Interactive Streamlit UI allowing QA engineers to edit titles, steps, and expected results, and approve or reject the suite.
5. **Environment & Safety Controls:** Configurable environments (`local`, `test`, `staging`) with strict URL allowlists and environment-variable-backed credentials (never passed to the LLM).
6. **Playwright Execution Engine:** Headless/headed Playwright execution using allowlisted actions (`goto`, `click`, `fill`, `assert_text`, `assert_url`, `wait_for`).
7. **Deterministic Assertions:** Verification handled via deterministic Playwright assertions (`expect(locator).to_have_text(...)`), not LLM guessing.
8. **Evidence Artifact Collection:** Automatic recording of Playwright traces (`.zip`), high-res failure screenshots (`.png`), and structured JSON execution logs.
9. **Interactive Dashboard & Telemetry:** Execution outcome reporting (PASS, FAIL, BLOCKED, ERROR, CANCELLED) with inline trace and screenshot viewers.
10. **Human-Approved Jira Defect Logging:** Generation of structured markdown defect drafts with auto-attached evidence summaries, requiring explicit human sign-off before API submission.
11. **Local Deterministic Demo Application:** A self-contained FastAPI/Streamlit Task Management web app used as a verified target application for safe, reproducible testing.

### 4.2 Out-of-Scope (Future Releases)
1. Unrestricted autonomous web browsing across arbitrary public internet sites.
2. Direct execution of arbitrary Python scripts generated on the fly by an LLM without static compilation.
3. Automated destructive database modifications or payment gateway executions in production environments.
4. Autonomous creation of Jira defects without human review and confirmation.
5. Multi-tenant enterprise SaaS infrastructure, user management, and enterprise SSO (Phase 2).
6. Universal automation of arbitrary legacy Flash/Canvas/WebGL applications.

---

## 5. Stakeholders and Personas

| Persona | Role | Primary Goal | Permissions & Responsibilities | Major Workflows |
| :--- | :--- | :--- | :--- | :--- |
| **QA Engineer (Alex)** | Primary Operator | Generate, inspect, execute, and verify test cases for sprint user stories. | Edit generated tests, trigger test runs, view evidence, draft defect tickets. | Jira lookup -> Review tests -> Approve -> Run -> Inspect evidence -> File defect. |
| **QA Lead / Manager (Sarah)** | Governance & Oversight | Ensure testing standards, review team metrics, audit test coverage. | View all runs, review audit trails, approve environment allowlists, configure policies. | Review dashboard metrics, audit trace logs, sign off on major release suites. |
| **Business Analyst / PO (David)** | Requirement Author | Validate that acceptance criteria are testable and clear. | View requirement ambiguity reports and coverage matrices. | Review requirement quality score; update Jira tickets with missing details. |
| **Software Developer (Elena)** | Defect Resolver | Quickly reproduce and fix bugs discovered by automated tests. | Read-only access to execution reports, traces, and defect drafts. | Inspect Playwright trace and failure screenshot in Jira defect ticket; verify fix. |
| **Platform / Security Admin (Marcus)** | Infrastructure & SecOps | Ensure secret isolation, zero data leakage, and system availability. | Manage `.env`, configure Ollama models, maintain URL allowlists and local disk quotas. | Configure Ollama runtime; rotate Jira API tokens; review security logs. |

---

## 6. End-to-End Business Processes and Use Cases

### UC-01: Fetch Jira Requirement
- **Actor:** QA Engineer
- **Preconditions:** Jira API credentials configured in `.env`; issue exists in Jira.
- **Trigger:** User enters Jira Issue Key (e.g. `TEST-101`) and clicks "Fetch Requirement".
- **Main Flow:**
  1. System queries Jira Cloud REST API (`GET /rest/api/3/issue/{key}`).
  2. System parses ADF or markdown description into plain text and structured fields.
  3. System renders summary, description, status, and issue metadata in UI.
- **Alternate / Exception Flow:**
  - *Network failure / Invalid Token:* System displays sanitized error message: "Failed to connect to Jira API. Verify credentials in `.env`."
  - *Issue Not Found:* System prompts user to verify the issue key.
- **Postconditions:** Jira requirement cached in session state.

### UC-02: Analyze Acceptance Criteria
- **Actor:** System (Agent Orchestrator)
- **Preconditions:** Requirement successfully fetched.
- **Trigger:** Automatic upon fetch or user clicks "Analyze Requirements".
- **Main Flow:**
  1. LLM parses requirement text to segment discrete Acceptance Criteria (AC-1, AC-2, etc.).
  2. System checks for ambiguity, missing edge cases, and preconditions.
  3. System outputs a structured Requirement Quality Assessment.
- **Postconditions:** Acceptance criteria list populated with traceability IDs.

### UC-03: Identify Ambiguous Requirements
- **Actor:** QA Engineer & Business Analyst
- **Preconditions:** Requirement analyzed.
- **Trigger:** Ambiguity score exceeds warning threshold (e.g., missing validation rules).
- **Main Flow:**
  1. System highlights ambiguous phrases (e.g., "system should be fast", "valid user").
  2. System prompts QA engineer with suggested clarifying questions for the PO.
  3. Engineer can add manual clarifying notes directly in the UI before generation.

### UC-04: Generate Structured Test Suite
- **Actor:** System (Test Designer Agent)
- **Preconditions:** Valid acceptance criteria identified.
- **Trigger:** User clicks "Generate Test Suite".
- **Main Flow:**
  1. Agent formats prompt with system guardrails and Pydantic JSON schema constraints.
  2. Ollama local LLM generates JSON response.
  3. System validates response against `TestSuite` Pydantic model.
  4. System categorizes tests: Positive, Negative, Boundary, Validation.
  5. System validates 100% AC traceability.
- **Alternate / Exception Flow:**
  - *JSON Syntax / Validation Error:* System initiates bounded self-correction retry (max 2 retries) with schema error feedback.
  - *Ollama down:* System prompts: "Local LLM service is unreachable on `localhost:11434`."
- **Postconditions:** Validated test suite staged for human review.

### UC-05: Review and Edit Test Cases
- **Actor:** QA Engineer
- **Preconditions:** Test suite generated and staged.
- **Trigger:** User navigates to Review Center tab.
- **Main Flow:**
  1. User inspects individual test cases, action steps, locators, and assertions.
  2. User modifies step parameters, adds missing assertions, or deletes invalid tests.
  3. System re-validates edited models against Pydantic schema in real time.
- **Postconditions:** Updated test suite saved in session state.

### UC-06: Approve or Reject Test Suite
- **Actor:** QA Engineer / Reviewer
- **Preconditions:** Review complete.
- **Trigger:** User clicks "Approve Suite" or "Reject Suite".
- **Main Flow:**
  1. If approved, system creates an immutable `ApprovalRecord` with reviewer ID, timestamp, and suite checksum.
  2. Workflow transitions from `staged` to `approved` state.
  3. If rejected, user enters rejection comments, and the workflow halts or allows re-generation.
- **Postconditions:** Approval gate cleared; execution engine unlocked.

### UC-07: Select Environment and Test Data
- **Actor:** QA Engineer
- **Preconditions:** Test suite approved.
- **Trigger:** User selects target environment profile (`local`, `test`, `staging`).
- **Main Flow:**
  1. System checks target URL against configured `ALLOWED_DOMAINS` allowlist.
  2. System injects synthetic test credentials from secure `.env` mapping.
  3. If domain is unapproved, execution is strictly blocked with security alert.
- **Postconditions:** Target environment verified and bound to execution session.

### UC-08: Execute Approved Tests
- **Actor:** System (Browser Execution Engine)
- **Preconditions:** Suite approved, environment allowlist verified.
- **Trigger:** User clicks "Start Test Execution".
- **Main Flow:**
  1. Engine initializes Playwright Chromium context with video and trace recording enabled.
  2. For each test case, engine runs setup steps, user actions (`fill`, `click`), and deterministic assertions.
  3. Real-time execution logs stream to the Streamlit UI.
  4. Context is cleanly closed and trace files are persisted to disk.
- **Postconditions:** All test cases executed; artifacts stored in `/artifacts/{run_id}`.

### UC-09: Recover from Browser or Locator Failure
- **Actor:** System (Browser Execution Engine)
- **Preconditions:** An element is not immediately interactable.
- **Trigger:** Element interaction timeout (e.g. 5000ms).
- **Main Flow:**
  1. Engine pauses and checks for loading spinners or pending network requests.
  2. Fallback locator strategy attempts secondary accessible locator (Role -> Name -> Test-ID).
  3. If still unresolvable, captures emergency DOM snapshot and failure screenshot, and raises classified error.
- **Postconditions:** Clean failure classification recorded without hung process.

### UC-10: Classify Execution Results
- **Actor:** System (Results Analyzer)
- **Preconditions:** Test run completed.
- **Trigger:** Test execution terminates.
- **Main Flow:**
  1. System inspects failure exceptions:
     - `AssertionError` -> Classified as **Application Defect**.
     - `TimeoutError / LocatorNotFound` -> Classified as **Locator / UI Change**.
     - `ConnectionRefused` -> Classified as **Infrastructure / Environment**.
  2. Outputs structured outcome: PASS, FAIL, BLOCKED, ERROR, CANCELLED.
- **Postconditions:** Standardized results attached to `ExecutionRun`.

### UC-11: Review Screenshots, Traces, and Logs
- **Actor:** QA Engineer
- **Preconditions:** Execution completed.
- **Trigger:** User navigates to Evidence Viewer tab.
- **Main Flow:**
  1. UI displays failure gallery with full-resolution screenshots.
  2. UI provides Playwright Trace download link and command to open via `playwright show-trace`.
  3. User reviews step-by-step logs and actual vs. expected values.
- **Postconditions:** QA engineer has full diagnostic proof of the run.

### UC-12: Create Jira Defect After Human Approval
- **Actor:** QA Engineer
- **Preconditions:** At least one test case failed with classified Application Defect.
- **Trigger:** User clicks "Generate Defect Draft".
- **Main Flow:**
  1. System synthesizes structured Defect Draft: steps to reproduce, expected vs actual, environment, and evidence links.
  2. User reviews draft in UI, edits description, and clicks "Approve & Submit to Jira".
  3. System calls Jira REST API (`POST /rest/api/3/issue`) linking to the parent requirement.
  4. Returns new Jira Defect Key (e.g. `BUG-402`).
- **Alternate Flow:** User discards draft; no Jira API call made.
- **Postconditions:** Defect logged in Jira with 100% audit trail.

### UC-13: View Run History and Quality Metrics
- **Actor:** QA Lead / Engineer
- **Preconditions:** Previous runs recorded.
- **Trigger:** User navigates to Dashboard / Run History tab.
- **Main Flow:**
  1. System queries SQLite run repository.
  2. Displays pass/fail trends, flakiness rate, average latency, and AC coverage charts.
- **Postconditions:** Historical reporting visualized.

### UC-14: Cancel or Safely Stop an Execution
- **Actor:** QA Engineer
- **Preconditions:** Test execution in progress.
- **Trigger:** User clicks "Stop Run".
- **Main Flow:**
  1. System sends cancellation signal to active Playwright context.
  2. Engine safely flushes ongoing traces, saves screenshots, closes browser process.
  3. Marks remaining tests as `CANCELLED`.
- **Postconditions:** Zero orphaned browser processes; clean state restored.

### UC-15: Resume Interrupted Workflow After Human Approval
- **Actor:** QA Engineer
- **Preconditions:** Workflow persisted at `human_review` checkpoint.
- **Trigger:** User returns to application after closing browser or session timeout.
- **Main Flow:**
  1. LangGraph loads checkpoint state from SQLite checkpointer.
  2. UI detects pending approval state and displays exact pending suite.
  3. User approves; workflow continues without re-running LLM generation.
- **Postconditions:** Seamless resumption with zero duplicate LLM invocations.

---

## 7. Business Rules and Risk Register

### 7.1 Business Rules
- **BR-01 (Mandatory Approval):** Under no circumstance shall any browser automation action execute without an explicit, cryptographically verifiable `ApprovalRecord` signed by a human operator.
- **BR-02 (Domain Isolation):** The execution engine shall reject any URL navigation that does not match the configured `ALLOWED_DOMAINS` allowlist for the selected environment.
- **BR-03 (Credential Redaction):** Usernames, passwords, tokens, and cookies shall never be passed into LLM prompts, logged to disk, or displayed in UI test steps.
- **BR-04 (No Code Injection):** The test execution engine shall only interpret strongly-typed JSON action steps. Direct `eval()` or execution of raw Python code strings generated by an LLM is strictly prohibited.
- **BR-05 (Bounded Execution):** Every test step has a strict 10-second timeout; every test case has a 60-second timeout; entire suites cannot exceed 10 minutes.
- **BR-06 (Defect Approval):** Automated bug logging into Jira Cloud must require an explicit, individual confirmation click from a human user.

### 7.2 Risk Register
| Risk ID | Risk Description | Likelihood | Impact | Mitigation Strategy | Owner |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **RSK-01** | **Local LLM Hallucination:** Model invents non-existent UI elements or false acceptance criteria. | Medium | Medium | Strict Pydantic schema validation, AC traceability checks, and mandatory human review before execution. | AI Engineer |
| **RSK-02** | **RAM / Hardware Exhaustion:** Running Ollama 8B + Playwright + Streamlit on 16GB Mac causes swap thrashing. | Medium | High | Recommend Qwen2.5:3B/7B quantized (Q4_K_M); implement sequential execution; monitor memory limits. | DevOps / SysArch |
| **RSK-03** | **Prompt Injection via Jira:** Malicious actor puts prompt injection instructions into Jira description to execute attacks. | Low | Critical | Defense-in-depth: Treat Jira text as untrusted data; enclose in structural XML delimiters; system instructions take precedence; allowlisted tools only. | Security Engineer |
| **RSK-04** | **Unintended Destruction in Test Env:** Test runs perform destructive actions (e.g., delete user) on shared staging environment. | Low | High | Restrict execution profiles to safe local/demo environments by default; forbid destructive commands without special flags. | QA Lead |
| **RSK-05** | **Jira Cloud API Rate Limiting:** Rapid polling or large batch fetches hit Atlassian rate limits (HTTP 429). | Low | Medium | Implement exponential backoff, client-side caching of requirement payloads, and bounded retries. | Python Engineer |

---

## 8. Business Acceptance Criteria & MVP Exit Criteria

### 8.1 Business Acceptance Criteria
1. The platform must connect to Jira Cloud via REST API v3 using user email and API token, successfully fetching stories and converting rich descriptions into clean text.
2. The platform must generate structured, schema-compliant test cases from Jira requirements using local Ollama models with $\ge 80\%$ reviewer acceptance.
3. The platform must enforce a strict human approval gate before triggering any browser automation.
4. The platform must execute approved tests deterministically against the local demo application via Playwright without crashes.
5. The platform must produce high-resolution screenshots, Playwright trace files, and structured logs for 100% of failed executions.
6. The platform must allow human-approved, one-click defect creation back to Jira Cloud with linked evidence.

### 8.2 MVP Exit Criteria Checklist
- [ ] Complete documentation package created (`BRD.md`, `FRD.md`, `TECHNICAL_SPECIFICATION.md`, `ARCHITECTURE.md`, `SECURITY.md`, `TRACEABILITY_MATRIX.md`, `ROADMAP.md`).
- [ ] Phase 1 local development environment and virtualenv configured and verified.
- [ ] Phase 2 Ollama local runtime verified with structured Pydantic output.
- [ ] Phase 3 local deterministic demo Task Management web application operational.
- [ ] Phase 4-11 Playwright automation engine and LangGraph workflow operational with HITL gates.
- [ ] Phase 12 security guardrails and URL allowlists verified against negative penetration tests.
- [ ] Phase 13-16 end-to-end vertical slice from Jira fetch to execution and defect drafting verified.
- [ ] All unit and integration test suites passing with zero critical security defects.

