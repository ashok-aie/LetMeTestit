# Let me TEST it....!
> **Agentic Quality Engineering Platform**  
> *From requirements to verified results.*

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Playwright](https://img.shields.io/badge/tested%20with-Playwright-green.svg)](https://playwright.dev/python/)
[![LangGraph](https://img.shields.io/badge/orchestration-LangGraph-orange.svg)](https://langchain-ai.github.io/langgraph/)
[![Langfuse](https://img.shields.io/badge/observability-Langfuse-purple.svg)](https://langfuse.com/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

---

## 🎯 What is "Let me TEST it....!"?

**Let me TEST it....!** is an enterprise agentic quality engineering platform that converts Jira requirements and user stories into deterministic, human-approved Playwright automated test suites. 

It pairs multi-model LLM intelligence (Local Ollama, Groq, Antigravity API) with strict human-in-the-loop sign-off governance, robust domain guardrails, and automated browser execution against both modern web applications and enterprise **SAP S/4HANA Fiori** systems.

---

## 🏗️ Architecture & Core Components

```
                ┌──────────────────────────────────────────────────┐
                │             Let me TEST it....! UI               │
                │        Streamlit Dashboard (Port 8501)           │
                └────────────────────────┬─────────────────────────┘
                                         │
        ┌────────────────────────────────┼────────────────────────────────┐
        ▼                                ▼                                ▼
┌─────────────────┐            ┌───────────────────┐            ┌───────────────────┐
│ Jira Ingestion  │            │  Test Designer    │            │ Review Center     │
│ & Normalization │            │  Synthesis Engine │            │ (Human-in-Loop)   │
└─────────────────┘            └─────────┬─────────┘            └─────────┬─────────┘
                                         │                                │
                                         ▼                                ▼
┌─────────────────┐            ┌───────────────────┐            ┌───────────────────┐
│ Langfuse Cloud  │◄───────────┤ LLM Observability │            │ Approved Suite    │
│ Tracing/Metrics │            │ & Token Telemetry │            │ (SHA-256 Hash)    │
└─────────────────┘            └───────────────────┘            └─────────┬─────────┘
                                                                          │
                                                                          ▼
                                                                ┌───────────────────┐
                                                                │ Playwright Engine │
                                                                │   app/browser/    │
                                                                └─────────┬─────────┘
                                                                          │
                                         ┌────────────────────────────────┴────────────────────────────────┐
                                         ▼                                                                 ▼
                              ┌───────────────────────┐                                         ┌─────────────────────┐
                              │  Local Demo ERP App   │                                         │  Live SAP S/4HANA   │
                              │ (http://localhost:8000)│                                         │   Fiori Launchpad   │
                              └───────────────────────┘                                         └─────────────────────┘
```

---

## 📁 Repository & Playwright Organization

All browser automation logic and test scripts are centralized inside the `app/browser/` package:

* **`app/browser/context.py`**: Browser context manager, Chromium launch configurations, DNS resolution, and CDP remote debugging.
* **`app/browser/executor.py`**: Step-by-step test execution engine with screenshot capture, assertions, and SAP auto-login handling.
* **`app/browser/locators.py`**: Heuristic and deterministic DOM locator resolver (data-testid, role, text, CSS).
* **`app/browser/recorder.py`**: Interactive browser session recorder using `npx playwright codegen`.
* **`app/browser/exporter.py`**: Exports approved test suites into standalone runnable Python Playwright test scripts.
* **`app/browser/test_scripts/`**: **Centralized repository for all test scripts.**
  * Recorded user journeys (`recorded_test.py`)
  * Exported standalone test scripts (`test_<suite_id>.py`)
  * Runnable directly via `pytest app/browser/test_scripts/` or `python`.

---

## 🔭 Observability & Telemetry (Langfuse)

The platform uses **Langfuse** for enterprise LLM observability, agent tracing, token counts, and execution metrics:

1. Create a free account at [Langfuse Cloud](https://cloud.langfuse.com) (or self-host).
2. Configure your credentials in `.env`:
   ```bash
   LANGFUSE_ENABLED=true
   LANGFUSE_PUBLIC_KEY=pk-lf-...
   LANGFUSE_SECRET_KEY=sk-lf-...
   LANGFUSE_HOST=https://cloud.langfuse.com
   ```
3. Real-time traces for requirement analysis, test synthesis, and browser execution are automatically captured in your Langfuse dashboard.

---

## 🚀 Quick Start

### 🍏 Option A: Running on macOS / Linux

#### 1. Setup Virtual Environment
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
```

#### 2. Configure Environment
```bash
cp .env.example .env
# Edit .env with your Jira, LLM, and Langfuse keys
```

#### 3. Run Application
```bash
# Terminal 1 (Optional Demo App):
python demo_app/main.py

# Terminal 2: Let me TEST it....! Platform UI
streamlit run app/ui.py
```

---

### 🪟 Option B: Running on Windows / Remote Desktop

To run directly inside an internal Windows Remote Desktop machine (e.g. for SAP network trust):

1. Clone or pull the repository:
   ```cmd
   git clone <repo-url>
   cd LetMeTestIt
   ```
2. Double-click the included 1-click launcher:
   👉 **`setup_and_run.bat`**
3. The script automatically sets up the virtual environment, installs dependencies, downloads Playwright Chromium, and starts the platform at `http://localhost:8501`.

---

## 🏢 SAP S/4HANA Fiori Automated Testing

* **Target URL Support:** Configurable in `.env` (`SAP_FIORI_URL`) and directly in the UI.
* **Automated Logon:** Detects the SAP Fiori Logon screen and injects credentials (`#USERNAME_FIELD-inner`, `#PASSWORD_FIELD-inner`, `#LANGUAGE_SELECT`, `#LOGIN_LINK`).
* **Zero Network Friction:** When executed locally or inside the Remote Desktop VM, tests run with full internal domain trust.

---

## 📚 Documentation Index

Detailed architectural and functional specifications are located in the `docs/` folder:

1. [Business Requirements Document (BRD)](file:///Users/mutyala/Documents/AAI/AAI-LAB/LetMeTestIt/docs/BRD.md)
2. [Functional Requirements Document (FRD)](file:///Users/mutyala/Documents/AAI/AAI-LAB/LetMeTestIt/docs/FRD.md)
3. [Technical Specification Document (TSD)](file:///Users/mutyala/Documents/AAI/AAI-LAB/LetMeTestIt/docs/TECHNICAL_SPECIFICATION.md)
4. [System Architecture & State Graphs](file:///Users/mutyala/Documents/AAI/AAI-LAB/LetMeTestIt/docs/ARCHITECTURE.md)
5. [Security & Guardrails Specification](file:///Users/mutyala/Documents/AAI/AAI-LAB/LetMeTestIt/docs/SECURITY.md)
6. [Operational Runbook & Troubleshooting](file:///Users/mutyala/Documents/AAI/AAI-LAB/LetMeTestIt/docs/RUNBOOK.md)
