# Playwright Test Scripts Repository

This directory (`app/browser/test_scripts/`) is the centralized storage location for all automated Playwright test scripts within **Let me TEST it....!**.

## What is stored here:
1. **Interactive Codegen Recordings:** Scripts recorded using `npx playwright codegen` via the UI Review Center.
2. **Exported Test Suites:** Standalone, runnable Python/Playwright test scripts generated from synthesized Jira requirements.
3. **Manual Custom Scripts:** Custom automated test workflows written for SAP S/4HANA Fiori, CRM, ERP, and Web portals.

## How to execute any test script directly:
```bash
# Run with Python
python app/browser/test_scripts/<script_name>.py

# Or run with Pytest
pytest app/browser/test_scripts/<script_name>.py -v -s
```

