# Functional Requirements Document (FRD)
## Product Name: Let me TEST it....! (TestPilot AI Engine)
**Document Version:** 1.0.0  
**Status:** Approved Baseline  
**Date:** October 2026  

---

## 1. Functional Architecture & Module Decomposition

The platform is structured into **14 discrete, decoupled functional modules**:

```
+----------------------------------------------------------------------------------------+
|                                    STREAMLIT UI                                        |
|  [Dashboard] [Jira Hub] [Req Analyzer] [Test Review] [Execution Monitor] [Evidence]    |
+----------------------------------------------------------------------------------------+
         |                        |                     |                    |
         v                        v                     v                    v
+------------------+    +-------------------+   +---------------+   +--------------------+
| 1. REQUIREMENT   |    | 2. REQUIREMENT    |   | 3. TEST       |   | 4. REVIEW          |
|    HUB           |--->|    ANALYZER       |-->|    DESIGNER   |-->|    CENTER (HITL)   |
| (Jira REST API)  |    | (AC Parsing & QG) |   | (Ollama LLM)  |   | (Pydantic Editor)  |
+------------------+    +-------------------+   +---------------+   +--------------------+
                                                                             |
                                                                             v
+----------------------------------------------------------------------------------------+
| 7. AGENT ORCHESTRATOR (LangGraph Workflow with StateGraph, Checkpoints & Interrupts)   |
+----------------------------------------------------------------------------------------+
         |                          |                         |
         v                          v                         v
+------------------+       +-------------------+     +------------------+
| 5. ENVIRONMENT   |       | 8. BROWSER        |     | 9. POLICY &      |
|    MANAGER       |       |    EXECUTION      |     |    GUARDRAILS    |
| (Profiles/URLs)  |       |    ENGINE         |     | (Allowlists,     |
+------------------+       | (Playwright/Tools)|     |  Safety Bounds)  |
         |                 +-------------------+     +------------------+
         v                          |                         |
+------------------+                v                         v
| 6. TEST DATA     |       +-------------------+     +------------------+
|    MANAGER       |       | 10. EVIDENCE      |     | 14. AUDIT        |
| (Synthetic Data) |       |     MANAGER       |     |     MANAGER      |
+------------------+       | (Traces/Screens)  |     | (JSONL Ledger)   |
                           +-------------------+     +------------------+
                                    |
                                    v
                           +-------------------+     +------------------+
                           | 11. RESULTS &     |---->| 12. DEFECT       |
                           |     REPORTING     |     |     ASSISTANT    |
                           | (Classification)  |     | (Jira Cloud Bug) |
                           +-------------------+     +------------------+
                                    |
                                    v
                           +-------------------+
                           | 13. QUALITY       |
                           |     MONITOR       |
                           | (SQLite Telemetry)|
                           +-------------------+
```

---

## 2. Detailed Functional Requirements

### Area A: Jira Integration

#### FR-JIRA-001: Jira Cloud REST Authentication & Connectivity
- **Description:** Securely connect to Jira Cloud using Atlassian API token and basic auth headers.
- **Business Rationale:** Automated requirement retrieval without requiring manual copy-pasting.
- **Actor:** System / Platform Administrator.
- **Preconditions:** `JIRA_BASE_URL`, `JIRA_USER_EMAIL`, and `JIRA_API_TOKEN` configured in environment.
- **Inputs:** Base URL, email, token.
- **Processing Rules:** Authenticate via HTTP Basic Auth (`base64(email:token)`). Check endpoint `/rest/api/3/myself`. Timeout after 5000ms.
- **Outputs:** Connection status (Authenticated / Unauthorized).
- **Error Handling:** Catch 401/403 (Invalid credentials), 429 (Rate limiting with retry-after header), 5xx (Jira service down).
- **Permissions:** Admin / QA Engineer.
- **Acceptance Criteria:** Successfully returns authenticated user profile or actionable error message without leaking token in logs.
- **Priority:** Must.
- **Test Scenarios:** Valid credentials pass; wrong token returns 401; missing token returns configuration error.

#### FR-JIRA-002: Issue Fetching & Rich Text (ADF) Normalization
- **Description:** Retrieve a Jira issue by key (e.g. `PROJ-101`) and convert Atlassian Document Format (ADF) into clean Markdown/text.
- **Business Rationale:** Jira Cloud uses ADF JSON trees for descriptions; downstream LLM requires clean structured text.
- **Actor:** QA Engineer.
- **Preconditions:** Jira connection active.
- **Inputs:** `issue_key` (String matching regex `^[A-Z][A-Z0-9]+-[0-9]+$`).
- **Processing Rules:** Query `GET /rest/api/3/issue/{issue_key}?fields=summary,description,status,labels,issuetype`. Recursively traverse ADF nodes (`paragraph`, `bulletList`, `text`, `codeBlock`) to produce normalized markdown string.
- **Outputs:** `JiraRequirement` object containing `key`, `summary`, `description_raw`, `description_text`, `status`, `labels`.
- **Error Handling:** If issue not found (404), return clear error: "Jira issue {key} not found".
- **Priority:** Must.
- **Test Scenarios:** Fetch simple issue; fetch issue with complex ADF tables and nested lists; fetch non-existent key.

---

### Area B: Requirement Analysis & Acceptance Criteria Extraction

#### FR-REQ-001: Structured Acceptance Criteria Extraction
- **Description:** Parse requirement text to extract discrete, atomic Acceptance Criteria (ACs).
- **Business Rationale:** Ensures every generated test traces back to a specific verifiable business condition.
- **Actor:** System (Requirement Analyzer).
- **Preconditions:** Valid `JiraRequirement` object loaded.
- **Inputs:** `summary`, `description_text`.
- **Processing Rules:** 
  1. Identify explicit "Given-When-Then" or bulleted acceptance criteria.
  2. Assign each a unique ID (`AC-01`, `AC-02`, ...).
  3. Classify requirement type: Functional, UI Validation, Authorization, Business Logic.
- **Outputs:** `List[AcceptanceCriterion]` containing `id`, `text`, `type`, `explicit`.
- **Priority:** Must.
- **Test Scenarios:** Standard Given/When/Then text; unstructured bulleted text; free-form paragraph without bullets.

#### FR-REQ-002: Requirement Quality & Ambiguity Assessment
- **Description:** Evaluate requirement completeness, detect ambiguous phrases, and score requirement testability.
- **Business Rationale:** Unclear requirements cause flawed tests; catching ambiguities early saves engineering hours.
- **Actor:** System (Requirement Analyzer).
- **Inputs:** `List[AcceptanceCriterion]`.
- **Processing Rules:**
  1. Scan for vague words: "fast", "user-friendly", "appropriate error", "seamless", "etc.".
  2. Flag missing error scenarios, unstated boundary values, or missing user roles.
  3. Compute `QualityScore` (0-100) and generate `clarification_questions`.
- **Outputs:** `RequirementQualityReport` with score, detected ambiguities, and suggestions.
- **Priority:** Should.
- **Test Scenarios:** Well-defined story scores $\ge 90$; vague story scores $< 60$ with highlighted ambiguity tags.

---

### Area C: Test Case Generation

#### FR-GEN-001: Pydantic-Constrained Structured Test Suite Generation
- **Description:** Utilize local Ollama LLM to synthesize a comprehensive test suite validated against strict Pydantic schemas.
- **Business Rationale:** Eliminates freeform hallucinations; produces machine-executable, strongly typed test structures.
- **Actor:** System (Test Designer Agent).
- **Preconditions:** `AcceptanceCriterion` list ready; Ollama server reachable.
- **Inputs:** Structured requirement context, target Pydantic schema, allowed action types.
- **Processing Rules:**
  1. Generate test cases covering Positive (Happy Path), Negative (Error Paths), Boundary, and UI Validation.
  2. Each test case must have: `id`, `title`, `objective`, `category`, `source_ac_id`, `preconditions`, `test_data`, `steps`, `expected_result`.
  3. Every step must map to an approved action type (`navigate`, `click`, `fill`, `assert_text`, `assert_url`, `wait`).
  4. Parse LLM JSON output directly into `TestSuite` Pydantic model.
- **Outputs:** Validated `TestSuite` object.
- **Error Handling:** If output violates Pydantic schema, trigger bounded recovery (max 2 retries) passing validation error back to prompt.
- **Priority:** Must.
- **Test Scenarios:** Happy path generation; schema validation failure followed by successful auto-correction.

#### FR-GEN-002: Traceability & Coverage Verification
- **Description:** Verify that 100% of extracted Acceptance Criteria are covered by at least one generated test case.
- **Business Rationale:** Prevents coverage gaps and unverified business rules.
- **Actor:** System (Test Designer Agent).
- **Processing Rules:** Check $\forall ac \in ACs, \exists tc \in TestSuite \text{ s.t. } tc.source\_ac\_id = ac.id$.
- **Outputs:** `TraceabilityReport` highlighting mapped vs unmapped criteria.
- **Priority:** Must.
- **Test Scenarios:** Full coverage passes; missing AC triggers generation of additional targeted test cases.

---

### Area D: Human Review & Approval (HITL)

#### FR-HITL-001: Interactive Test Suite Review & Editing
- **Description:** Render generated test cases in Streamlit UI allowing QA engineers to inspect, modify, add, or delete test steps.
- **Business Rationale:** AI proposes; humans verify. Guarantees safety and alignment with business reality.
- **Actor:** QA Engineer.
- **Preconditions:** `TestSuite` generated.
- **Inputs:** User edits to titles, locators, input values, and assertion expectations.
- **Processing Rules:** Real-time Pydantic re-validation on form submit to ensure user edits maintain valid schema structure.
- **Outputs:** Updated `TestSuite` in session state.
- **Priority:** Must.
- **Test Scenarios:** User edits test step text; user changes expected assertion; user deletes redundant test case.

#### FR-HITL-002: Cryptographic-Style Approval Gate & Audit Record
- **Description:** Require explicit human approval action before unlocking the execution engine.
- **Business Rationale:** Prevents accidental or automated execution of unreviewed test suites.
- **Actor:** QA Engineer / Reviewer.
- **Inputs:** User approval button click (`Approve Suite`), Reviewer Name, Comments.
- **Processing Rules:**
  1. Generate SHA-256 hash of the final approved `TestSuite` JSON.
  2. Create `ApprovalRecord` containing `suite_hash`, `reviewer_name`, `timestamp`, `decision` (APPROVED/REJECTED), `comments`.
  3. Transition LangGraph state from `human_review` to `execution_ready`.
- **Outputs:** Immutable `ApprovalRecord` saved to persistence store.
- **Priority:** Must.
- **Test Scenarios:** Approval succeeds and unlocks execution; rejection halts execution; tampering with suite after approval invalidates hash.

---

### Area E: Environment & Credentials

#### FR-ENV-001: Environment Profiles & Domain Allowlists
- **Description:** Support named environment profiles (`local`, `test`, `staging`) with strict URL allowlists.
- **Business Rationale:** Prevents test engine from wandering to unauthorized domains or production systems.
- **Actor:** QA Engineer / Administrator.
- **Processing Rules:**
  - `local`: `http://localhost:*`, `http://127.0.0.1:*`
  - `test`: Specific pre-approved internal domains.
  - Production environments explicitly disabled in MVP.
  - Reject navigation if target domain $\notin ALLOWED\_DOMAINS$.
- **Outputs:** Verified target URL for execution.
- **Priority:** Must.
- **Test Scenarios:** Localhost navigation allowed; external URL (e.g. `https://google.com`) blocked with `SecurityPolicyViolation`.

#### FR-ENV-002: Secure Credential Injection & Isolation
- **Description:** Inject authentication credentials into Playwright sessions without exposing secrets to the LLM or UI logs.
- **Business Rationale:** Zero secret leakage in agent prompts, logs, or reports.
- **Actor:** System.
- **Processing Rules:** Credentials fetched directly from `.env` by execution engine during test execution; redacted in all logs with `***REDACTED***`.
- **Priority:** Must.
- **Test Scenarios:** Test logs contain redacted tokens; LLM prompt context contains no secret tokens.

---

### Area F: Browser Automation Execution

#### FR-EXEC-001: Sandboxed Playwright Context Lifecycle
- **Description:** Manage isolated Playwright browser contexts for each test suite run with clean cookies, storage, and tracing.
- **Business Rationale:** Ensures test isolation, avoids cross-test contamination, and prevents hung browser processes.
- **Actor:** System (Browser Execution Engine).
- **Processing Rules:**
  1. Launch Chromium in headless or headed mode based on configuration.
  2. Create fresh `BrowserContext` with viewport 1280x720.
  3. Start Playwright Tracing (`screenshots=True`, `snapshots=True`, `sources=True`).
  4. Upon completion or failure, stop tracing, export zip, and close context.
- **Outputs:** Trace file path (`/artifacts/{run_id}/trace.zip`), context lifecycle logs.
- **Priority:** Must.
- **Test Scenarios:** Clean launch and shutdown; forced abort cleanly closes browser.

#### FR-EXEC-002: Deterministic Action Dispatcher & Locators
- **Description:** Execute strongly typed browser actions with priority-based accessible locators.
- **Business Rationale:** Eliminates fragile XPath; prioritizes accessible ARIA semantics.
- **Actor:** System (Browser Execution Engine).
- **Supported Actions:**
  - `navigate(url)`: Load approved URL with network-idle wait.
  - `click(selector_role, name)`: Click accessible role or selector.
  - `fill(selector, value)`: Clear field and type value.
  - `assert_text(selector, expected_text)`: Deterministic text verification.
  - `assert_url(expected_pattern)`: Verify page URL regex.
  - `wait(milliseconds)`: Bounded wait (max 5000ms).
- **Processing Rules:** Prioritize locators: `page.get_by_role()`, `page.get_by_text()`, `page.get_by_test_id()`. Validate element uniqueness.
- **Priority:** Must.
- **Test Scenarios:** Successful form fill and submit; element ambiguity handled; timeout handled gracefully.

---

### Area G: Results & Defect Management

#### FR-RES-001: Execution Outcome Classification
- **Description:** Standardize test outcomes into PASS, FAIL, BLOCKED, ERROR, CANCELLED with root-cause categorization.
- **Business Rationale:** Cuts debugging time by distinguishing application defects from infrastructure flakiness.
- **Actor:** System (Results Classifier).
- **Classification Rules:**
  - **PASS:** All assertions passed.
  - **FAIL (Application Defect):** Assertions failed on visible content or state.
  - **ERROR (Locator/Automation):** Element not found or selector ambiguous.
  - **BLOCKED (Environment/Network):** Target server unreachable or connection reset.
  - **CANCELLED:** Run halted by user.
- **Outputs:** Standardized `TestResult` object with error classification.
- **Priority:** Must.
- **Test Scenarios:** Assert failure -> FAIL; timeout on button -> ERROR; server down -> BLOCKED.

#### FR-DEF-001: Human-Approved Jira Defect Creation
- **Description:** Generate structured markdown bug drafts for failed tests and post to Jira Cloud upon human confirmation.
- **Business Rationale:** Eliminates manual bug ticket writing while preventing duplicate or spam bug tickets.
- **Actor:** QA Engineer.
- **Preconditions:** At least one test in FAIL status; Jira credentials valid.
- **Inputs:** Failed `TestResult`, parent `issue_key`.
- **Processing Rules:**
  1. Synthesize Bug Title: `[TestPilot AI Bug] {test_title} - {brief_failure}`.
  2. Synthesize Steps to Reproduce, Expected vs Actual, Environment, and Evidence summary.
  3. Present draft in UI for engineer review and edit.
  4. Submit to Jira API (`POST /rest/api/3/issue`) only when user clicks "Submit to Jira".
- **Outputs:** Jira Defect Key (e.g. `BUG-304`).
- **Priority:** Must.
- **Test Scenarios:** Draft generated correctly; user modifies steps; bug submitted; duplicate submission prevented.

---

### Area H: Reporting & Telemetry

#### FR-TEL-001: SQLite Persistence & Structured JSONL Audit Logging
- **Description:** Persist all requirement snapshots, test suites, approval records, execution runs, and audit logs.
- **Business Rationale:** Complete regulatory traceability and persistent historical reporting across sessions.
- **Actor:** System.
- **Processing Rules:** Store relational entities in SQLite (`testpilot.db`); write immutable audit events to `audit.jsonl`.
- **Priority:** Must.
- **Test Scenarios:** Restart application; past runs and approval records remain accessible.

---

## 3. User Interface Specification (Streamlit)

### Screen 1: Executive Dashboard
- **Purpose:** High-level metrics, recent runs, pass/fail rates, system health indicators (Ollama, Jira).
- **UI Elements:**
  - Status Pills: Ollama Status (Online/Offline), Jira Status (Connected/Disconnected).
  - KPI Cards: Total Test Runs, Overall Pass Rate, Traceability Coverage, MTTD.
  - Historical Run Trend Chart: Line/bar chart of recent executions.

### Screen 2: Jira Requirement Hub
- **Purpose:** Input Jira key, preview requirement summary and description.
- **UI Elements:**
  - Input: Jira Issue Key (`text_input`).
  - Action: "Fetch from Jira" button.
  - Display: Status badge, Issue Type, Summary, Formatted Markdown Description, Raw ADF expander.

### Screen 3: Requirement Quality & AC Explorer
- **Purpose:** View extracted Acceptance Criteria and Ambiguity Quality Score.
- **UI Elements:**
  - Quality Score Meter (0-100).
  - Detected Ambiguity Alert Box with clarifying questions.
  - Table of extracted Acceptance Criteria with category tags.

### Screen 4: Test Suite Generator & Designer
- **Purpose:** Configure generation parameters and trigger Ollama LLM test design.
- **UI Elements:**
  - Model Selector (`qwen2.5:7b`, `qwen2.5:3b`, etc.).
  - Scenario Toggles: Positive, Negative, Boundary, Validation.
  - Action: "Generate Test Suite" button with spinner.
  - Generation Telemetry: Model latency, token count, schema retry counter.

### Screen 5: Review Center (HITL Gate)
- **Purpose:** Inspect generated test cases, edit steps, and record approval/rejection.
- **UI Elements:**
  - Test Case Accordion: Expandable list of test cases.
  - Editable data fields: Title, Preconditions, Step Actions, Locators, Assertion text.
  - Action Buttons: "Approve Suite (Unlock Execution)" (Green), "Reject Suite" (Red).
  - Reviewer inputs: Reviewer Name, Comments.
  - Approval Badge: Displays "APPROVED - Hash: abc12..." once signed off.

### Screen 6: Environment & Execution Monitor
- **Purpose:** Select environment, run approved tests, and view real-time execution logs.
- **UI Elements:**
  - Environment Profile Selector: Local Demo App (`http://localhost:8000`), Custom Test URL.
  - Headless / Headed browser checkbox.
  - Action: "Execute Approved Suite" button (disabled until approved).
  - Real-time Console Log Box: Streaming output of Playwright actions.
  - Progress Bar: Percentage of test cases executed.

### Screen 7: Execution Results & Reporting
- **Purpose:** View pass/fail status, duration, and root cause classification for every test.
- **UI Elements:**
  - Status Summary Bar: Count of PASS, FAIL, ERROR, BLOCKED, CANCELLED.
  - Detailed Results Table with failure classification tags.
  - Step-by-step Execution Log for selected test case.

### Screen 8: Evidence Viewer & Playwright Traces
- **Purpose:** Inspect visual proof, screenshots, and Playwright trace archives.
- **UI Elements:**
  - Failure Screenshot Gallery: High-resolution images of failure state.
  - Playwright Trace Downloader: Download `trace.zip` button.
  - Terminal command helper: `playwright show-trace /path/to/trace.zip`.

### Screen 9: Defect Assistant (Jira Bug Logger)
- **Purpose:** Review auto-generated bug drafts for failed tests and post to Jira.
- **UI Elements:**
  - Dropdown of failed tests.
  - Markdown editor populated with auto-generated defect draft.
  - Action: "Submit Defect to Jira Cloud" button with confirmation modal.
  - Success Alert with clickable link to created Jira issue.

### Screen 10: Run History & Audit Trail
- **Purpose:** Browse past execution runs, view approval records and audit events.
- **UI Elements:**
  - Run History Dataframe with date filters.
  - Audit Log Viewer: Filterable events (`SUITE_GENERATED`, `SUITE_APPROVED`, `RUN_STARTED`, `DEFECT_CREATED`).

---

## 4. Non-Functional Requirements (NFRs)

| NFR ID | Category | Requirement Specification | Verification Method |
| :--- | :--- | :--- | :--- |
| **NFR-SEC-01** | Security | Zero credentials passed to LLM prompts or logged to disk. Secrets redacted with `***REDACTED***`. | Automated log inspection and unit tests. |
| **NFR-SEC-02** | Security | Navigation strictly limited to configured `ALLOWED_DOMAINS` allowlist. | Penetration test attempting unallowlisted navigation. |
| **NFR-SEC-03** | Security | No arbitrary Python code evaluation (`eval`/`exec`) permitted anywhere in the agent pipeline. | Code scan / AST validation. |
| **NFR-REL-01** | Reliability | Browser context crashes or element timeouts must not crash the Streamlit server; process terminates cleanly with classified error. | Chaos/failure injection tests. |
| **NFR-PERF-01**| Performance | Local LLM test generation for a standard story must complete within 45 seconds on Apple Silicon (M-series / 16GB). | Benchmark script on standard story. |
| **NFR-PERF-02**| Performance | Playwright step execution latency must not exceed 200ms overhead beyond network wait. | Playwright trace timing analysis. |
| **NFR-RES-01** | Resource Usage | Total peak memory consumption of Ollama + Streamlit + Playwright must remain under 12 GB RAM to prevent OS swapping. | macOS `activitymonitor` / `psutil` profiling. |
| **NFR-OBS-01** | Observability | 100% of failed test executions must generate a screenshot and a Playwright trace archive. | Verification script on test runs. |
| **NFR-AUD-01** | Auditability | All human review actions and suite approvals must record reviewer, timestamp, and SHA-256 hash in SQLite and JSONL. | Audit trail inspection test. |
| **NFR-PORT-01**| Portability | Application runs identically on macOS (Apple Silicon & Intel) using Python virtualenv and Playwright. | Cross-platform compatibility check. |

