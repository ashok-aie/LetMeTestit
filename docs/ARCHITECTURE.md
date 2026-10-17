# System Architecture & Diagrams
## Product Name: Let me TEST it....! (TestPilot AI Engine)
**Document Version:** 1.0.0  
**Status:** Approved Baseline  
**Date:** October 2026  

---

## 1. System Context Diagram (C4 Level 1)

This diagram visualizes how **Let me TEST it....!** interfaces with external systems, human actors, local runtimes, and target environments.

```mermaid
graph TD
    User["QA Engineer / Approver<br/>(Human-in-the-Loop)"]
    
    subgraph LocalMac["Local Workstation (macOS 16GB RAM)"]
        App["Let me TEST it....!<br/>(Streamlit UI + LangGraph + Playwright)"]
        Ollama["Ollama Runtime<br/>(Local LLM: Qwen2.5 / Qwen3)"]
        SQLiteDB[("SQLite DB & File Artifacts<br/>(Runs, Traces, Screenshots, Audit Logs)")]
        LocalDemoApp["Local Demo Web App<br/>(FastAPI / Streamlit Target App)"]
    end
    
    subgraph ExternalSystems["External SaaS Services"]
        JiraCloud["Atlassian Jira Cloud<br/>(Requirements & Defect Management)"]
        TestStagingEnv["Remote Test / Staging App<br/>(Allowlisted Target Environment)"]
    end
    
    User -->|"Configures, Reviews, Edits & Approves Tests"| App
    App -->|"Fetch Stories & Post Approved Defects"| JiraCloud
    App -->|"Sends Prompt & Receives Pydantic JSON"| Ollama
    App -->|"Persists State, Traces & Audit Trails"| SQLiteDB
    App -->|"Executes Allowlisted Actions via Playwright"| LocalDemoApp
    App -.->|"Optional: Executes against allowlisted domain"| TestStagingEnv
```

---

## 2. Component Architecture Diagram (C4 Level 2)

This diagram illustrates the internal modular structure of the Python application.

```mermaid
graph TD
    subgraph UI_Layer["User Interface Layer (Streamlit)"]
        DashboardView["Dashboard & KPI View"]
        JiraHubView["Jira Requirement Hub"]
        ReviewCenterView["Review Center (HITL Gate)"]
        ExecMonitorView["Execution Monitor & Console"]
        EvidenceView["Evidence & Trace Viewer"]
        DefectView["Jira Defect Assistant"]
    end

    subgraph Core_Engine["Core Engine & Agent Orchestrator"]
        StateGraphEngine["LangGraph StateGraph Engine<br/>(Interrupts, Routing & Checkpoints)"]
        ReqAnalyzer["Requirement Analyzer & Quality Scorer"]
        TestDesigner["Test Designer Agent (LLM Prompting)"]
        ApprovalValidator["Approval & Checksum Validator"]
        ResultsClassifier["Results Classifier & Error Categorizer"]
    end

    subgraph Execution_Layer["Execution & Automation Layer"]
        PolicyEngine["Policy & URL Guardrails Engine"]
        BrowserEngine["Playwright Execution Engine"]
        ActionDispatcher["Deterministic Action Dispatcher"]
        EvidenceCollector["Evidence Collector (Trace & Screenshot)"]
    end

    subgraph Integration_Data_Layer["Integration & Data Layer"]
        JiraClient["Jira Cloud REST Client"]
        OllamaClient["Ollama Local HTTP Client"]
        SQLiteRepo["SQLite Repository & Checkpointer"]
        AuditLedger["JSONL Audit Ledger"]
    end

    UI_Layer --> Core_Engine
    Core_Engine --> Execution_Layer
    Core_Engine --> Integration_Data_Layer
    Execution_Layer --> Integration_Data_Layer
```

---

## 3. Data-Flow Diagram (DFD)

This diagram tracks how data transforms from a Jira requirement into an approved test execution and resulting defect.

```mermaid
flowchart LR
    JiraIssue["Jira Cloud Issue<br/>(ADF JSON)"] -->|"1. Fetch & Normalize"| ReqObject["JiraRequirement<br/>(Clean Text)"]
    ReqObject -->|"2. Extract & Score"| ACs["Acceptance Criteria<br/>+ Quality Score"]
    ACs -->|"3. Prompt LLM"| RawLLM["Ollama JSON Stream"]
    RawLLM -->|"4. Pydantic Validate"| TestSuiteObj["Staged TestSuite<br/>(Pydantic Object)"]
    TestSuiteObj -->|"5. Human Edit & Sign"| ApprovedSuite["Approved TestSuite<br/>+ SHA256 Approval Record"]
    ApprovedSuite -->|"6. Guardrail Check"| AllowlistCheck{"URL in<br/>Allowlist?"}
    AllowlistCheck -->|No| SecurityError["Security Block Event"]
    AllowlistCheck -->|Yes| PlaywrightExec["Playwright Engine<br/>Context Execution"]
    PlaywrightExec -->|"7. Collect Evidence"| Artifacts["Traces, Screenshots<br/>& Execution Logs"]
    Artifacts -->|"8. Classify Outcome"| RunSummary["ExecutionRun<br/>(PASS / FAIL / ERROR)"]
    RunSummary -->|"9. If Failed: Propose Defect"| DefectDraftObj["DefectDraft<br/>(Markdown Bug Ticket)"]
    DefectDraftObj -->|"10. Human Sign-off"| JiraDefect["Jira Cloud Defect<br/>(BUG-XXX Created)"]
```

---

## 4. LangGraph Workflow State Diagram

This state diagram details the exact cyclic graph, conditional edges, retry loops, and human-in-the-loop interruption gates.

```mermaid
flowchart TD
    START([Start]) --> FetchReq[fetch_requirement]
    FetchReq --> NormalizeReq[normalize_requirement]
    NormalizeReq --> AssessCompleteness[assess_completeness]
    AssessCompleteness --> GenerateTests[generate_test_cases]
    GenerateTests --> ValidateSchema{validate_test_cases<br/>Valid Pydantic?}
    
    ValidateSchema -->|Invalid & Retries < 2| RetryGen[Increment Retry Count<br/>Add Error Feedback]
    RetryGen --> GenerateTests
    
    ValidateSchema -->|Invalid & Retries >= 2| FailState[handle_failure: Schema Error]
    
    ValidateSchema -->|Valid| HumanReview([human_review<br/>INTERRUPT GATE / PAUSE])
    
    HumanReview --> CheckDecision{Human Decision?}
    CheckDecision -->|Rejected| EndRejection([Halt: Suite Rejected])
    CheckDecision -->|Edited & Approved| ValidateApproval[validate_approval_checksum]
    
    ValidateApproval --> CheckPolicy{Policy Check<br/>URL Allowlisted?}
    CheckPolicy -->|Disallowed| SecurityHalt([Halt: Security Policy Violation])
    
    CheckPolicy -->|Allowed| ExecuteTests[execute_test_suite<br/>Playwright Execution]
    
    ExecuteTests --> ClassifyResults[classify_results]
    ClassifyResults --> GenerateReport[generate_report & save_artifacts]
    
    GenerateReport --> CheckFailures{Any Failures?}
    CheckFailures -->|No Failures| FinalizeRun[finalize_run & persist]
    CheckFailures -->|Has Failures| PrepareDefect[prepare_defect_drafts]
    
    PrepareDefect --> HumanDefectGate([human_approve_defect<br/>INTERRUPT GATE])
    HumanDefectGate --> CreateJiraDefect[create_jira_defect]
    CreateJiraDefect --> FinalizeRun
    
    FinalizeRun --> END([End / Idle])
```

---

## 5. Sequence Diagram: Primary End-to-End Use Case

This sequence diagram illustrates the complete execution flow from requirement input to Playwright automation and reporting.

```mermaid
sequenceDiagram
    autonumber
    actor QA as QA Engineer
    participant UI as Streamlit UI
    participant Graph as LangGraph Orchestrator
    participant Jira as Jira Cloud REST API
    participant Ollama as Local Ollama (Qwen)
    participant PW as Playwright Browser Engine
    participant Target as Target Web App
    participant Store as SQLite & Disk Storage

    QA->>UI: Enter Issue Key ("PROJ-101") & Click "Fetch"
    UI->>Graph: Trigger Workflow (fetch_requirement)
    Graph->>Jira: GET /rest/api/3/issue/PROJ-101
    Jira-->>Graph: Return ADF Issue JSON
    Graph->>Graph: Normalize ADF & Extract Acceptance Criteria
    Graph->>Ollama: POST /api/generate (System Prompt + ACs + Pydantic Schema)
    Ollama-->>Graph: Return TestSuite JSON
    Graph->>Graph: Validate TestSuite Schema
    Graph->>Store: Save Checkpoint State
    Graph-->>UI: PAUSE at human_review interrupt gate
    
    UI->>QA: Display Generated Test Cases for Inspection
    QA->>UI: Edit Step 3 assertion, Enter Name & Click "Approve Suite"
    UI->>Graph: Resume Workflow with ApprovalRecord
    Graph->>Graph: Validate Suite Hash & URL Allowlist
    
    Graph->>PW: Initialize BrowserContext & Start Tracing
    PW->>Target: Navigate to target URL
    loop For Each Approved Test Step
        PW->>Target: Perform allowlisted action (click/fill)
        PW->>Target: Evaluate deterministic assertion
    end
    PW->>Store: Save trace.zip & screenshot.png
    PW-->>Graph: Return Execution Results
    
    Graph->>Graph: Classify Outcomes (PASS / FAIL)
    Graph->>Store: Record ExecutionRun & AuditEvent
    Graph-->>UI: Emit Complete Report & Trace links
    UI->>QA: Display Results Dashboard with Screenshots & Traces
```

---

## 6. Local Mac Deployment Diagram

This deployment diagram details the process boundaries, memory budgets, and local network ports on macOS.

```mermaid
graph TD
    subgraph MacSystem["Local macOS Workstation (Apple Silicon / Intel - 16 GB RAM)"]
        
        subgraph Terminal1["Streamlit Process (Python 3.11 venv) - Port 8501"]
            UIProcess["Streamlit App<br/>Memory: ~250 MB RAM"]
            OrchestratorThread["LangGraph Engine & SQLite Checkpointer"]
        end
        
        subgraph Terminal2["Ollama Process (Local Inference Server) - Port 11434"]
            OllamaServer["Ollama Daemon<br/>Model: qwen2.5:7b-instruct-q4_K_M<br/>Memory: ~5.2 GB RAM (Metal / CPU)"]
        end
        
        subgraph Terminal3["Local Demo Target Application - Port 8000"]
            TargetApp["Task Management Web App<br/>Memory: ~100 MB RAM"]
        end
        
        subgraph HeadlessWorker["Playwright Subprocess"]
            ChromiumWorker["Chromium Headless / Headed<br/>Memory: ~350 MB RAM"]
        end
        
        subgraph StorageDir["File System Storage"]
            DBFile[("testpilot.db (SQLite)")]
            ArtifactsDir["artifacts/<br/>traces/*.zip<br/>screenshots/*.png<br/>logs/audit.jsonl"]
        end
        
    end

    UIProcess -->|"HTTP localhost:11434"| OllamaServer
    UIProcess -->|"IPC / Driver"| ChromiumWorker
    ChromiumWorker -->|"HTTP localhost:8000"| TargetApp
    UIProcess --> DBFile
    ChromiumWorker --> ArtifactsDir
```

