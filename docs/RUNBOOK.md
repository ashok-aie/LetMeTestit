# Operational Runbook & Troubleshooting Guide
## Product Name: Let me TEST it....! (TestPilot AI Engine)
**Document Version:** 1.0.0  
**Status:** Approved Baseline  
**Date:** October 2026  

---

## 1. Quick Start Commands (macOS)

### 1.1 Prerequisites
- macOS Sonoma or newer (Apple Silicon M1/M2/M3/M4 or Intel Core i7+)
- Python 3.11+
- Homebrew installed
- Ollama installed (`brew install ollama`)

### 1.2 Initial Setup
```bash
# 1. Navigate to workspace
cd /Users/mutyala/Documents/AAI/AAI-LAB/LetMeTestIt

# 2. Create and activate virtual environment
python3 -m venv .venv
source .venv/bin/activate

# 3. Install Python dependencies
pip install --upgrade pip
pip install -r requirements.txt

# 4. Install Playwright browser binaries
playwright install chromium

# 5. Copy and configure environment variables
cp .env.example .env
# Edit .env with your Jira Cloud credentials and settings
```

### 1.3 Starting Local Services
In **Terminal 1** (Ollama Server):
```bash
ollama serve
# Verify or pull recommended model
ollama pull qwen2.5:7b
```

In **Terminal 2** (Local Demo Target App):
```bash
source .venv/bin/activate
python demo_app/main.py
# Verify running on http://localhost:8000
```

In **Terminal 3** (Let me TEST it....! Streamlit UI):
```bash
source .venv/bin/activate
streamlit run app/ui.py
# Opens automatically on http://localhost:8501
```

---

## 2. Troubleshooting & Diagnostics

### 2.1 Ollama / LLM Issues
- **Symptom:** UI displays "Ollama connection refused on http://localhost:11434".
  - **Fix:** Ensure `ollama serve` is running in an active terminal. Run `curl http://localhost:11434/api/tags` to verify.
- **Symptom:** Test generation is very slow or Mac memory is swapping heavily.
  - **Fix:** If using an Intel Mac or low memory, switch model from `qwen2.5:7b` to `qwen2.5:3b` in `.env` (`OLLAMA_MODEL=qwen2.5:3b`).

### 2.2 Playwright Browser Issues
- **Symptom:** `Executable doesn't exist at .../ms-playwright/chromium-...`
  - **Fix:** Run `playwright install chromium` inside your active virtual environment.
- **Symptom:** Browser fails to open in headed mode on Mac.
  - **Fix:** Verify Terminal has accessibility permissions or toggle to Headless mode in the UI.

### 2.3 Jira Cloud Connection Issues
- **Symptom:** HTTP 401 Unauthorized when fetching an issue.
  - **Fix:** Verify `JIRA_USER_EMAIL` is your Atlassian login email and `JIRA_API_TOKEN` is an active token created at [id.atlassian.com](https://id.atlassian.com/manage-profile/security/api-tokens).
- **Symptom:** HTTP 404 Not Found.
  - **Fix:** Confirm the issue key exists and your account has project view permissions.

### 2.4 Langfuse Observability Issues
- **Symptom:** Traces are not showing in Langfuse Cloud dashboard.
  - **Fix:** Verify `LANGFUSE_PUBLIC_KEY` and `LANGFUSE_SECRET_KEY` in `.env`. Ensure `LANGFUSE_HOST=https://cloud.langfuse.com` is accessible.

### 2.5 Windows Remote Desktop & SAP Fiori Execution
- **Symptom:** SAP login rejected from external network ("Client, name, or password is not correct").
  - **Fix:** Run the platform directly inside the Remote Desktop VM using `setup_and_run.bat` to leverage the internal network trust.
- **Symptom:** Playwright test scripts location.
  - **Fix:** All test scripts and recordings are stored in `app/browser/test_scripts/`. Run directly using `pytest app/browser/test_scripts/` or through the UI.

---

## 3. Maintenance & Housekeeping

### 3.1 Trace & Screenshot Artifact Cleanup
Artifacts are saved in `artifacts/runs/{run_id}/`. To clear previous run artifacts and free disk space:
```bash
rm -rf artifacts/runs/*
```

### 3.2 Database Reset
To reset run history and start from a clean SQLite state:
```bash
rm -f testpilot.db
```
The database will automatically reinitialize on next app launch.

