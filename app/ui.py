"""
Let me TEST it....!
Agentic Quality Engineering Platform
Features:
- Multi-Model LLM Test Synthesis (Antigravity API / Groq API / Local Ollama)
- Live Jira Cloud Ingestion & ADF Normalization
- Human-in-the-Loop Review Center & Interactive Playwright Recording
- In-Card Test Case Editing and Deletion Controls
- In-Tab Browser Automation Execution (Playwright Headed / Headless Mode)
- Real-Time Action Items Stream with Direct Evidence Navigation
- Automated Executive PDF Report (Consistent Headers) & Jira Defect Assistant
"""
import os
import sys
import re
import time
import urllib.request
import threading
from pathlib import Path
from typing import Optional, List, Dict, Any

import streamlit as st

# Configure Streamlit page layout and branding
st.set_page_config(
    page_title="Let me TEST it....!",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# Ensure application modules can be resolved
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import settings
from app.jira.client import JiraClient, JiraClientError
from app.jira.normalizer import ADFNormalizer
from app.agents.llm_client import get_llm_client, OllamaClient, GroqClient, AntigravityClient
from app.test_design.generator import TestDesigner
from app.models.requirements import JiraRequirement, AcceptanceCriterion
from app.models.test_suite import TestSuite, TestCase, TestStep, ActionType, LocatorStrategy, TestCategory
from app.models.execution import (
    ApprovalRecord,
    ApprovalDecision,
    ExecutionRun,
    TestOutcome,
    FailureClassification,
)
from app.models.defects import DefectDraft
from app.browser.executor import TestExecutor
from app.browser.recorder import (
    record_playwright_session,
    parse_recorded_script,
    create_test_case_from_recording,
)
from app.policies.guardrails import PolicyEngine
from app.reporting.reporter import ExecutionReportGenerator


# ==============================================================================
# Background Demo App Helper (Ensures http://127.0.0.1:8000 is always responsive)
# ==============================================================================
def is_demo_app_active(url: str = "http://127.0.0.1:8000/") -> bool:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "LetMeTestIt-Health"})
        with urllib.request.urlopen(req, timeout=1.5) as resp:
            return resp.status == 200
    except Exception:
        return False


def start_demo_app_background():
    """Starts the local SAP S/4HANA FastAPI demo app in an embedded daemon thread."""
    if not is_demo_app_active():
        import uvicorn
        from demo_app.main import app as demo_fastapi_app

        def _run():
            uvicorn.run(demo_fastapi_app, host="127.0.0.1", port=8000, log_level="error")

        server_thread = threading.Thread(target=_run, daemon=True)
        server_thread.start()
        time.sleep(1.0)


# Initialize demo app in background
start_demo_app_background()


# ==============================================================================
# Session State Initialization
# ==============================================================================
if "jira_requirement" not in st.session_state:
    st.session_state.jira_requirement = None
if "acceptance_criteria" not in st.session_state:
    st.session_state.acceptance_criteria = []
if "test_suite" not in st.session_state:
    st.session_state.test_suite = None
if "approval_record" not in st.session_state:
    st.session_state.approval_record = None
if "execution_run" not in st.session_state:
    st.session_state.execution_run = None
if "action_logs" not in st.session_state:
    st.session_state.action_logs = []
if "defect_drafts" not in st.session_state:
    st.session_state.defect_drafts = []
if "created_jira_defects" not in st.session_state:
    st.session_state.created_jira_defects = []
if "recorded_script_raw" not in st.session_state:
    st.session_state.recorded_script_raw = None
if "main_tab_selector" not in st.session_state:
    st.session_state.main_tab_selector = "1. Ingest & Design"
if "synthesis_logs" not in st.session_state:
    st.session_state.synthesis_logs = []


# ==============================================================================
# Custom CSS Styling (Completely hide sidebar and provide clean modern UI)
# ==============================================================================
st.markdown(
    """
    <style>
    /* Completely hide the left sidebar and its collapse control */
    [data-testid="stSidebar"], [data-testid="collapsedControl"] {
        display: none !important;
    }

    :root {
        --primary: #0284c7;
        --primary-dark: #0369a1;
        --primary-light: #f0f9ff;
        --border-color: #e2e8f0;
        --text-main: #0f172a;
        --text-muted: #64748b;
    }

    .main-title {
        font-size: 2.2rem;
        font-weight: 700;
        color: #0f172a;
        margin-bottom: 0.1rem;
        letter-spacing: -0.5px;
    }
    .sub-title {
        font-size: 1.0rem;
        color: #64748b;
        margin-bottom: 0.8rem;
        font-weight: 400;
    }
    .step-log-item {
        padding: 0.5rem 0.8rem;
        margin: 0.25rem 0;
        border-radius: 6px;
        background-color: #f8fafc;
        border-left: 3px solid #0284c7;
        font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
        font-size: 0.85rem;
        color: #1e293b;
        box-shadow: 0 1px 2px rgba(0,0,0,0.02);
    }
    .badge-pass {
        display: inline-block;
        padding: 2px 8px;
        font-size: 0.75rem;
        font-weight: 600;
        color: #15803d;
        background-color: #dcfce7;
        border: 1px solid #bbf7d0;
        border-radius: 9999px;
    }
    .badge-fail {
        display: inline-block;
        padding: 2px 8px;
        font-size: 0.75rem;
        font-weight: 600;
        color: #b91c1c;
        background-color: #fee2e2;
        border: 1px solid #fecaca;
        border-radius: 9999px;
    }
    div[data-testid="stRadio"] > div[role="radiogroup"] {
        gap: 8px;
        margin-bottom: 1rem;
    }
    div[data-testid="stRadio"] > div[role="radiogroup"] > label {
        background-color: #f8fafc;
        border: 1px solid #e2e8f0;
        padding: 8px 18px;
        border-radius: 6px;
        cursor: pointer;
        font-weight: 600;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# ==============================================================================
# Header with Right-Side Three-Dot Menu (Replacing Left Sidebar)
# ==============================================================================
header_col1, header_col2 = st.columns([11, 1])

with header_col1:
    st.markdown('<div class="main-title">Let me TEST it....!</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-title">Agentic Quality Engineering Platform</div>', unsafe_allow_html=True)

with header_col2:
    with st.popover("⋮", use_container_width=True):
        st.markdown("### System Diagnostics")
        jira_client = JiraClient()
        is_jira_ok = jira_client.is_connected()
        if is_jira_ok:
            st.success(f"**Jira Cloud:** Connected\n- `{settings.jira_base_url}`\n- User: `{settings.jira_user_email}`")
        else:
            st.warning("**Jira Cloud:** Disconnected / Token needed")

        demo_online = is_demo_app_active()
        if demo_online:
            st.success("**Target ERP:** Online (Port 8000)")
        else:
            st.error("**Target ERP:** Offline")
            if st.button("Start SAP Demo App", key="menu_start_demo_app"):
                start_demo_app_background()
                st.rerun()

        st.markdown("---")
        st.markdown("### Observability & Telemetry")
        lf_pub_key = getattr(settings, "langfuse_public_key", "") or os.getenv("LANGFUSE_PUBLIC_KEY", "")
        lf_host = getattr(settings, "langfuse_host", "") or os.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com")
        if lf_pub_key:
            st.success(
                f"**Langfuse:** Connected\n"
                f"- Host: `{lf_host}`\n"
                f"- Tracing: `Active`"
            )
            st.markdown(f"[Open Langfuse Console ↗]({lf_host})")
        else:
            st.info(
                f"**Langfuse Telemetry:** Configured (`{lf_host}`)\n\n"
                "To stream live LLM, test generation & agent traces to Langfuse, set `LANGFUSE_PUBLIC_KEY` and `LANGFUSE_SECRET_KEY` in `.env`."
            )
            st.markdown(f"[Open Langfuse Console ↗]({lf_host})")

        # In-App Runtime Performance Telemetry
        st.markdown("---")
        st.markdown("### Runtime Telemetry")
        if st.session_state.test_suite:
            pos_tcs = sum(1 for t in st.session_state.test_suite.test_cases if t.category == TestCategory.POSITIVE)
            neg_tcs = len(st.session_state.test_suite.test_cases) - pos_tcs
            st.markdown(f"**Active Test Suite:** `{st.session_state.test_suite.suite_id}`\n- Scenarios: `{len(st.session_state.test_suite.test_cases)}` (`{pos_tcs}` Pos / `{neg_tcs}` Neg)")
        if st.session_state.execution_run:
            duration_s = (st.session_state.execution_run.finished_at - st.session_state.execution_run.started_at).total_seconds() if st.session_state.execution_run.finished_at else 0
            st.markdown(
                f"**Last Execution Run:**\n"
                f"- Duration: `{duration_s:.1f}s`\n"
                f"- Passed: `{st.session_state.execution_run.passed_tests}`\n"
                f"- Failed: `{st.session_state.execution_run.failed_tests}`"
            )

        st.markdown("---")
        if st.button("Reset Demo Database", key="menu_reset_demo_db"):
            try:
                req = urllib.request.Request("http://127.0.0.1:8000/reset", data=b"", method="POST")
                with urllib.request.urlopen(req) as resp:
                    st.success("Database reset to clean seed state.")
            except Exception as e:
                st.error(f"Reset failed: {e}")


# ==============================================================================
# Seamless Tab Navigation
# ==============================================================================
def navigate_to_tab(tab_name: str) -> None:
    st.session_state["main_tab_selector"] = tab_name

nav_tabs = ["1. Ingest & Design", "2. Review Center", "3. Evidence & Jira Defects"]
selected_nav = st.radio(
    "Navigation Tabs",
    options=nav_tabs,
    horizontal=True,
    label_visibility="collapsed",
    key="main_tab_selector",
)


# ==============================================================================
# TAB 1: Setup, Model Selection & Jira Requirements Ingestion
# ==============================================================================
if selected_nav == "1. Ingest & Design":
    # --------------------------------------------------------------------------
    # Platform Configuration: Model Selection, Jira User, Browser Settings
    # --------------------------------------------------------------------------
    with st.expander("Agent & Browser Execution Configuration", expanded=True):
        cfg_col1, cfg_col2, cfg_col3, cfg_col4 = st.columns(4)

        with cfg_col1:
            provider_choice = st.selectbox(
                "LLM Provider:",
                options=["Antigravity API", "Groq API", "Local Ollama"],
                index=0,
                key="cfg_provider_choice",
            )

        with cfg_col2:
            if provider_choice == "Antigravity API":
                model_options = ["gemini-3.5-flash", "gemini-3.1-flash-lite", "gemini-3-flash-preview"]
            elif provider_choice == "Groq API":
                model_options = ["qwen/qwen3.8-27b", "openai/gpt-oss-120b", "openai/gpt-oss-20b"]
            else:
                model_options = ["qwen2.5:7b", "llama3.2"]

            selected_model = st.selectbox(
                "Model Choice:",
                options=model_options,
                index=0,
                key=f"cfg_model_choice_{provider_choice}",
            )

        with cfg_col3:
            jira_user_input = st.text_input(
                "Jira User Email:",
                value=settings.jira_user_email,
                key="cfg_jira_user_input",
            )

        with cfg_col4:
            view_mode_choice = st.radio(
                "View Mode:",
                options=["Headed (Watch on Screen)", "Headless (Background)"],
                index=0,
                key="cfg_view_mode",
            )

    # --------------------------------------------------------------------------
    # Target Environment & Remote Execution (Option 2: Remote Windows Chrome via CDP)
    # --------------------------------------------------------------------------
    with st.expander("Target Environment & Remote Execution (Option 2: Remote Chrome CDP)", expanded=True):
        env_choice = st.radio(
            "Execution Target Application:",
            options=["Local Demo ERP (Port 8000)", "Remote Windows Desktop Chrome (SAP Fiori via CDP)"],
            index=1,
            key="cfg_env_target",
            horizontal=True,
        )
        if "Remote Windows" in env_choice:
            st.info("Directing browser execution to Chrome running inside the Remote Desktop VM (`183.82.97.234`).")
            cdp_col1, cdp_col2 = st.columns([3, 1])
            with cdp_col1:
                cdp_url = st.text_input(
                    "Remote Chrome CDP Endpoint URL:",
                    value=settings.cdp_endpoint_url or "http://183.82.97.234:9222",
                    help="URL of remote Chrome debugging port (e.g. http://183.82.97.234:9222 or your tunnel URL)",
                    key="cdp_url_input",
                )
            with cdp_col2:
                st.write("")
                st.write("")
                test_cdp_btn = st.button("Test CDP Connection", key="btn_test_cdp")
            
            if test_cdp_btn and cdp_url:
                try:
                    from playwright.sync_api import sync_playwright
                    with sync_playwright() as p:
                        b = p.chromium.connect_over_cdp(cdp_url.strip(), timeout=5000)
                        st.success(f"Connected to Remote Chrome successfully! Open contexts: {len(b.contexts)}")
                        b.close()
                except Exception as cdp_err:
                    st.error(f"Could not connect to Remote Chrome at {cdp_url}: {cdp_err}")

    st.markdown("---")
    st.subheader("Jira Requirement Ingestion")

    col1, col2 = st.columns([2, 1])
    with col1:
        issue_key_input = st.text_input(
            "Jira Issue Key",
            value="",
            placeholder="",
            help="Enter Jira issue key from your project",
            key="jira_issue_key_field",
        )
    with col2:
        st.write("")
        st.write("")
        fetch_btn = st.button("Ingest Story & Synthesize Tests", type="primary", use_container_width=True)

    synthesize_negative = st.checkbox(
        "Synthesize Negative & Boundary Scenarios (Mandatory Fields, Plant Limits, Error Banners)",
        value=True,
        help="Synthesizes negative test scenarios alongside positive flows to verify application validation rules and error banners.",
        key="chk_synthesize_negative",
    )

    # Synthesis Execution
    if fetch_btn and issue_key_input:
        st.session_state.synthesis_logs = []

        # Step 1: Fetching requirement
        st.markdown("**Step 1:** Fetching requirement from Jira Cloud...")
        try:
            requirement = jira_client.get_issue(issue_key_input.strip())
            st.session_state.jira_requirement = requirement
            st.write(f"Ingested: **{requirement.key}** — *{requirement.summary}*")
        except Exception as e:
            st.error(f"Could not fetch issue '{issue_key_input}': {e}")
            st.stop()

        # Step 2: Extracting Acceptance Criteria
        st.markdown("**Step 2:** Normalizing text and extracting Acceptance Criteria...")
        lines = [l.strip() for l in requirement.description_text.splitlines() if l.strip()]
        ac_list = []
        for idx, line in enumerate(lines, start=1):
            clean_l = line.strip()
            lower = clean_l.lower()
            is_ac = (
                "ac-" in lower or "ac:" in lower or
                lower.startswith(("-", "*", "given", "when", "then", "scenario")) or
                re.match(r"^(\d+[\.\)]|#|•)\s+", clean_l)
            )
            if is_ac and len(clean_l) > 6:
                ac_text = re.sub(r"^(\d+[\.\)]|[-*•#]|ac[:\-\d]*)\s*", "", clean_l, flags=re.IGNORECASE).strip()
                if ac_text:
                    ac_list.append(AcceptanceCriterion(id=f"AC-{len(ac_list)+1:02d}", text=ac_text))

        if not ac_list:
            ac_list.append(AcceptanceCriterion(id="AC-01", text=f"Positive Flow: Verify valid order creation for {requirement.summary}"))

        if synthesize_negative:
            has_negative_ac = any(
                any(w in ac.text.lower() for w in ["invalid", "without", "missing", "error", "exceed", "blank", "cannot", "fail", "reject", "negative", "boundary", "mandatory", "zero", "limit"])
                for ac in ac_list
            )
            if not has_negative_ac:
                ac_list.append(AcceptanceCriterion(
                    id=f"AC-{len(ac_list)+1:02d}",
                    text="Negative Validation: Rejects submission and displays error when mandatory Sold-to Party (Customer ID) is missing",
                ))
                ac_list.append(AcceptanceCriterion(
                    id=f"AC-{len(ac_list)+1:02d}",
                    text="Negative Boundary: Rejects submission and displays error when order quantity exceeds plant limit (max 500)",
                ))
                ac_list.append(AcceptanceCriterion(
                    id=f"AC-{len(ac_list)+1:02d}",
                    text="Negative Validation: Rejects submission and displays error when order quantity is zero or negative",
                ))

        requirement.acceptance_criteria = ac_list
        st.session_state.acceptance_criteria = ac_list
        pos_count = sum(1 for ac in ac_list if not any(w in ac.text.lower() for w in ["invalid", "without", "missing", "error", "exceed", "blank", "cannot", "fail", "reject", "negative", "boundary", "mandatory", "zero", "limit"]))
        neg_count = len(ac_list) - pos_count
        st.write(f"Extracted **{len(ac_list)}** Acceptance Criteria (**{pos_count}** Positive, **{neg_count}** Negative / Boundary).")

        # Show Requirement Description AND Extracted Acceptance Criteria together right here after Step 1
        with st.expander(f"Requirement Details: `{requirement.key}` — {requirement.summary}", expanded=True):
            st.markdown(requirement.description_text)
            st.markdown("#### Extracted Acceptance Criteria")
            for ac in requirement.acceptance_criteria:
                is_neg_ac = any(w in ac.text.lower() for w in ["invalid", "without", "missing", "error", "exceed", "blank", "cannot", "fail", "reject", "negative", "boundary", "mandatory", "zero", "limit"])
                ac_badge = '<span class="badge-fail" style="background:#fef3c7; color:#92400e; border-color:#fde68a;">NEGATIVE</span>' if is_neg_ac else '<span class="badge-pass">POSITIVE</span>'
                st.markdown(f"**[{ac.id}]** {ac_badge} {ac.text}", unsafe_allow_html=True)

        # Step 3: Synthesis
        st.markdown(f"**Step 3:** Synthesizing test cases using {provider_choice} ({selected_model})...")
        p_bar = st.progress(0.0)
        p_text = st.empty()

        def on_progress(curr, total, msg):
            pct = min(curr / max(total, 1), 1.0)
            p_bar.progress(pct)
            status_msg = f"Scenario [{curr}/{total}] ({int(pct*100)}%): {msg}"
            p_text.markdown(f"**{status_msg}**")
            st.session_state.synthesis_logs.append(status_msg)

        try:
            active_llm = get_llm_client(
                provider=provider_choice,
                model=selected_model,
            )
            target_app_url = settings.sap_fiori_url if "Remote Windows" in env_choice else "http://127.0.0.1:8000"
            designer = TestDesigner(llm_client=active_llm)
            suite = designer.generate_suite(
                requirement=requirement,
                target_base_url=target_app_url,
                progress_callback=on_progress,
            )
            st.session_state.test_suite = suite
            st.session_state.approval_record = None
            st.session_state.execution_run = None
            st.session_state.action_logs = []
            p_bar.progress(1.0)
            st.success("Synthesis Complete. Review your test suite.")
        except Exception as e:
            st.error(f"Test generation error: {e}")
            st.stop()

    # Retain synthesis steps log if present
    if st.session_state.synthesis_logs:
        st.markdown("#### Generation Step Log")
        for log in st.session_state.synthesis_logs[-5:]:
            st.markdown(f'<div class="step-log-item">{log}</div>', unsafe_allow_html=True)

    # Navigation button to Review Center
    if st.session_state.test_suite:
        st.markdown("---")
        st.button(
            "Proceed to Review Center →",
            type="primary",
            use_container_width=True,
            key="btn_goto_review_center",
            on_click=navigate_to_tab,
            args=("2. Review Center",),
        )


# ==============================================================================
# TAB 2: Review Center, Per-Test Case Edit/Delete, & Browser Execution
# ==============================================================================
elif selected_nav == "2. Review Center":
    st.subheader("Review Center")
    suite: Optional[TestSuite] = st.session_state.test_suite

    if not suite:
        st.info("No test suite staged for review. Ingest a Jira requirement in Tab 1 first.")
    else:
        header_col1, header_col2, header_col3 = st.columns([2.5, 1.2, 1.2])
        with header_col1:
            st.markdown(f"**Staged Suite:** `{suite.suite_id}` | **Total Scenarios:** `{len(suite.test_cases)}`")
        with header_col2:
            with st.popover("Record a New Test", use_container_width=True):
                st.markdown("**Record a New Test (npx playwright codegen)**")
                st.caption("Launches interactive browser recorder to capture clicks, inputs, and navigations.")
                rec_title = st.text_input(
                    "Scenario Title:",
                    value=f"Recorded Flow {len(suite.test_cases) + 1}",
                    key="rec_pop_title",
                )
                rec_url = st.text_input(
                    "Target URL:",
                    value="http://127.0.0.1:8000/",
                    key="rec_pop_url",
                )
                if st.button("Launch Recorder", type="primary", use_container_width=True, key="btn_launch_rec_pop"):
                    with st.spinner("Launching npx playwright codegen... Perform your actions in Chromium and close the browser window when finished."):
                        try:
                            recorded_code = record_playwright_session(target_url=rec_url.strip())
                            st.session_state.recorded_script_raw = recorded_code
                            if recorded_code.strip():
                                parsed_steps = parse_recorded_script(recorded_code, default_url=rec_url.strip())
                                next_id = f"TC-{len(suite.test_cases) + 1:02d}"
                                new_tc = create_test_case_from_recording(
                                    title=rec_title.strip() or f"Recorded Scenario {next_id}",
                                    steps=parsed_steps,
                                    requirement_key=suite.requirement_key,
                                    tc_id=next_id,
                                )
                                suite.test_cases.append(new_tc)
                                st.session_state.approval_record = None
                                st.success(f"Recorded test case '{new_tc.id}: {new_tc.title}' successfully captured and added to the suite.")
                                st.rerun()
                            else:
                                st.warning("No interactions were recorded or the browser was closed before any actions.")
        with header_col3:
            if st.button("Export Script 💾", use_container_width=True, help="Exports standalone Playwright script into app/browser/test_scripts/"):
                from app.browser.exporter import export_suite_to_playwright_script
                exported_path = export_suite_to_playwright_script(suite)
                st.success(f"Exported: `{exported_path.name}` in `app/browser/test_scripts/`")

        approval: Optional[ApprovalRecord] = st.session_state.approval_record
        is_approved = approval is not None and approval.decision == ApprovalDecision.APPROVED

        if is_approved:
            st.success(f"**APPROVED & SIGNED** by `{approval.reviewer}` on `{approval.timestamp.strftime('%Y-%m-%d %H:%M:%S UTC')}`")
        elif approval and approval.decision == ApprovalDecision.REJECTED:
            st.error(f"**REJECTED** by `{approval.reviewer}`. Comments: {approval.comments}")
        else:
            st.warning("Pending Human Review: Review test steps below, edit or record new scenarios, then approve.")

        # ----------------------------------------------------------------------
        # Test Scenarios with Edit & Delete Buttons at the Right Side of Objective
        # ----------------------------------------------------------------------
        for tc in suite.test_cases:
            with st.container():
                st.markdown("---")
                col_meta, col_actions = st.columns([4, 1.4])
                with col_meta:
                    is_neg_tc = tc.category == TestCategory.NEGATIVE
                    cat_badge = '<span class="badge-fail" style="background:#fef3c7; color:#92400e; border-color:#fde68a;">NEGATIVE VALIDATION</span>' if is_neg_tc else '<span class="badge-pass">POSITIVE FLOW</span>'
                    st.markdown(f"#### **[{tc.id}]** {tc.title} &nbsp;{cat_badge}", unsafe_allow_html=True)
                    st.markdown(f"**Objective:** {tc.objective}")
                    st.caption(f"Category: `{tc.category.value.upper()}` | Priority: `{tc.priority}` | Steps: `{len(tc.steps)}`")

                with col_actions:
                    btn_edit_col, btn_del_col = st.columns([1, 1])
                    with btn_edit_col:
                        is_editing = st.session_state.get(f"editing_{tc.id}", False)
                        if st.button("Edit Steps" if not is_editing else "Close", key=f"btn_edit_tc_{tc.id}", use_container_width=True):
                            st.session_state[f"editing_{tc.id}"] = not is_editing
                            st.rerun()
                    with btn_del_col:
                        if st.button("Delete", key=f"btn_del_tc_{tc.id}", use_container_width=True):
                            suite.test_cases = [c for c in suite.test_cases if c.id != tc.id]
                            for idx, c in enumerate(suite.test_cases, start=1):
                                c.id = f"TC-{idx:02d}"
                            st.session_state.approval_record = None
                            st.success(f"Scenario {tc.id} deleted and suite re-indexed.")
                            st.rerun()

                # Step table or inline step editor
                if not st.session_state.get(f"editing_{tc.id}", False):
                    step_data = []
                    for s in tc.steps:
                        step_data.append({
                            "Step #": s.step_number,
                            "Action": s.action.value.upper(),
                            "Strategy": s.locator_strategy.value if s.locator_strategy else "—",
                            "Target Selector": s.selector_value or "—",
                            "Input / Expected": s.input_value or s.expected_value or "—",
                            "Description": s.description,
                        })
                    st.dataframe(step_data, use_container_width=True)
                else:
                    with st.expander(f"Editing Steps for {tc.id}: {tc.title}", expanded=True):
                        step_nums = [s.step_number for s in tc.steps]
                        e_col1, e_col2 = st.columns([1, 1])
                        with e_col1:
                            selected_step_num = st.selectbox(
                                "Select Step to Edit:",
                                options=step_nums,
                                format_func=lambda snum: f"Step {snum}: {next((s.action.value.upper() for s in tc.steps if s.step_number == snum), '')} - {next((s.description for s in tc.steps if s.step_number == snum), '')[:35]}",
                                key=f"step_picker_{tc.id}",
                            )
                            current_step = next((s for s in tc.steps if s.step_number == selected_step_num), tc.steps[0])

                        with e_col2:
                            action_options = [a.value for a in ActionType]
                            curr_act = current_step.action.value
                            current_action_idx = action_options.index(curr_act) if curr_act in action_options else 0
                            new_action = st.selectbox(
                                "Action Type:",
                                options=action_options,
                                index=current_action_idx,
                                key=f"edit_act_{tc.id}_{selected_step_num}",
                            )

                        f_col1, f_col2 = st.columns([1, 1])
                        with f_col1:
                            strategy_options = ["test_id", "role", "text", "css"]
                            curr_strat = current_step.locator_strategy.value if current_step.locator_strategy else "test_id"
                            curr_strat_idx = strategy_options.index(curr_strat) if curr_strat in strategy_options else 0
                            new_strategy = st.selectbox(
                                "Locator Strategy:",
                                options=strategy_options,
                                index=curr_strat_idx,
                                key=f"edit_strat_{tc.id}_{selected_step_num}",
                            )
                        with f_col2:
                            new_selector = st.text_input(
                                "Target Selector / TestID:",
                                value=current_step.selector_value or "",
                                key=f"edit_sel_{tc.id}_{selected_step_num}",
                            )

                        g_col1, g_col2 = st.columns([1, 1])
                        with g_col1:
                            new_val = st.text_input(
                                "Input / Expected Value:",
                                value=current_step.input_value or current_step.expected_value or "",
                                key=f"edit_val_{tc.id}_{selected_step_num}",
                            )
                        with g_col2:
                            new_desc = st.text_input(
                                "Step Description:",
                                value=current_step.description or "",
                                key=f"edit_desc_{tc.id}_{selected_step_num}",
                            )

                        act_col1, act_col2, act_col3 = st.columns([1, 1, 1])
                        with act_col1:
                            if st.button("Save Step Modification", type="primary", use_container_width=True, key=f"btn_save_{tc.id}_{selected_step_num}"):
                                current_step.action = ActionType(new_action)
                                current_step.locator_strategy = LocatorStrategy(new_strategy) if new_strategy else None
                                current_step.selector_value = new_selector if new_selector else None
                                if new_action.startswith("assert"):
                                    current_step.expected_value = new_val
                                    current_step.input_value = None
                                else:
                                    current_step.input_value = new_val
                                    current_step.expected_value = None
                                current_step.description = new_desc
                                st.session_state.approval_record = None
                                st.success(f"Step {selected_step_num} for {tc.id} saved.")
                                st.rerun()

                        with act_col2:
                            if st.button("Add New Step", use_container_width=True, key=f"btn_add_{tc.id}"):
                                next_num = len(tc.steps) + 1
                                new_step = TestStep(
                                    step_number=next_num,
                                    action=ActionType.ASSERT_TEXT,
                                    locator_strategy=LocatorStrategy.TEST_ID,
                                    selector_value="success-banner",
                                    expected_value="created successfully",
                                    description=f"Assertion step {next_num}",
                                )
                                tc.steps.append(new_step)
                                st.session_state.approval_record = None
                                st.success(f"Step {next_num} added to {tc.id}.")
                                st.rerun()

                        with act_col3:
                            if st.button("Delete Selected Step", use_container_width=True, key=f"btn_del_{tc.id}_{selected_step_num}") and len(tc.steps) > 1:
                                tc.steps = [s for s in tc.steps if s.step_number != selected_step_num]
                                for idx, s in enumerate(tc.steps, start=1):
                                    s.step_number = idx
                                st.session_state.approval_record = None
                                st.warning(f"Step {selected_step_num} deleted from {tc.id}.")
                                st.rerun()

        # ----------------------------------------------------------------------
        # Feature: Human Sign-Off Governance (Hidden once approved)
        # ----------------------------------------------------------------------
        if not is_approved:
            st.markdown("---")
            st.markdown("### Human Sign-Off Governance")
            r_col1, r_col2 = st.columns([1, 2])
            with r_col1:
                reviewer_name = st.text_input("Reviewer Name / Email", value=settings.jira_user_email)
            with r_col2:
                reviewer_notes = st.text_input("Review Comments", value="Verified against acceptance criteria.")

            b_col1, b_col2, _ = st.columns([1, 1, 2])
            with b_col1:
                if st.button("Approve Suite", type="primary", use_container_width=True):
                    rec = ApprovalRecord(
                        approval_id=f"APP-{suite.requirement_key}",
                        suite_id=suite.suite_id,
                        suite_hash=suite.compute_hash(),
                        reviewer=reviewer_name,
                        decision=ApprovalDecision.APPROVED,
                        comments=reviewer_notes,
                    )
                    st.session_state.approval_record = rec
                    try:
                        from app.browser.exporter import export_suite_to_playwright_script
                        export_suite_to_playwright_script(suite)
                    except Exception:
                        pass
                    st.success("Suite approved and synchronized to `app/browser/test_scripts/`. You can now execute the tests in the browser.")
                    st.rerun()

            with b_col2:
                if st.button("Reject Suite", use_container_width=True):
                    rec = ApprovalRecord(
                        approval_id=f"REJ-{suite.requirement_key}",
                        suite_id=suite.suite_id,
                        suite_hash=suite.compute_hash(),
                        reviewer=reviewer_name,
                        decision=ApprovalDecision.REJECTED,
                        comments=reviewer_notes,
                    )
                    st.session_state.approval_record = rec
                    st.error("Suite rejected.")
                    st.rerun()
        else:
            rev_col1, _ = st.columns([1, 3])
            with rev_col1:
                if st.button("Revoke Sign-Off / Re-open Review", use_container_width=True):
                    st.session_state.approval_record = None
                    st.rerun()

        # ----------------------------------------------------------------------
        # Feature: In-Tab Browser Automation Execution
        # ----------------------------------------------------------------------
        if is_approved:
            st.markdown("---")
            st.markdown("### Run Approved Tests in Browser")

            view_mode_str = st.session_state.get("cfg_view_mode", "Headed (Watch on Screen)")
            is_headed_exec = "Headed" in view_mode_str

            exec_col1, exec_col2 = st.columns([2, 1])
            with exec_col1:
                st.markdown(f"**Execution Mode:** `{view_mode_str}`")
            with exec_col2:
                run_btn = st.button("Run Approved Tests in Browser", type="primary", use_container_width=True)

            progress_bar = st.progress(0.0)
            status_text = st.empty()

            if run_btn and suite and approval:
                current_hash = suite.compute_hash()
                if current_hash != approval.suite_hash:
                    st.error("Security Alert: Cryptographic suite hash mismatch. Suite was modified after sign-off.")
                    st.stop()

                policy = PolicyEngine()
                for tc in suite.test_cases:
                    for s in tc.steps:
                        if s.action == ActionType.NAVIGATE and s.input_value:
                            try:
                                policy.validate_navigation_url(s.input_value)
                            except Exception as err:
                                st.error(f"Security Alert: Navigation URL blocked by policy: {err}")
                                st.stop()

                st.session_state.action_logs = []
                total_steps = sum(len(tc.steps) for tc in suite.test_cases)
                tracker = {"completed": 0}

                def step_stream_callback(test_case: TestCase, step: TestStep, step_res):
                    if step_res is None:
                        status_text.markdown(f"**Executing:** `[{test_case.id}] Step {step.step_number}`: *{step.description}*")
                    else:
                        tracker["completed"] += 1
                        progress_bar.progress(min(tracker["completed"] / max(total_steps, 1), 1.0))
                        outcome_tag = "PASS" if step_res.passed else "FAIL"
                        log_entry = (
                            f"[{outcome_tag}] `[{test_case.id}] Step {step.step_number}` **{step.action.value.upper()}** "
                            f"`{step.selector_value or ''}` | {step_res.duration_ms}ms"
                        )
                        if not step_res.passed:
                            log_entry += f" — Error: {step_res.error_message}"
                        st.session_state.action_logs.append(log_entry)

                with st.spinner("Executing browser automation..."):
                    use_cdp = "Remote Windows" in st.session_state.get("cfg_env_target", "")
                    cdp_ep = st.session_state.get("cdp_url_input", "").strip() if use_cdp else None
                    target_exec_url = settings.sap_fiori_url if use_cdp else "http://127.0.0.1:8000"

                    executor = TestExecutor(
                        headless=not is_headed_exec,
                        slow_mo_ms=300 if is_headed_exec else 0,
                        cdp_url=cdp_ep,
                    )
                    run = executor.execute_suite(
                        suite=suite,
                        target_url=target_exec_url,
                        step_callback=step_stream_callback,
                    )
                    st.session_state.execution_run = run

                progress_bar.progress(1.0)
                status_text.success(f"Execution Complete: {run.passed_tests}/{run.total_tests} Tests Passed.")

            # Action Items Stream
            st.markdown("#### Action Items Stream")
            if st.session_state.action_logs:
                for log in st.session_state.action_logs:
                    st.markdown(f'<div class="step-log-item">{log}</div>', unsafe_allow_html=True)
            else:
                st.caption("No execution actions recorded yet. Click 'Run Approved Tests in Browser' to begin.")

            # Navigation Button to Evidence & Jira Defects (Item 8)
            if st.session_state.execution_run:
                st.markdown("---")
                st.button(
                    "Proceed to Evidence & Jira Defects →",
                    type="primary",
                    use_container_width=True,
                    key="btn_goto_evidence_defects",
                    on_click=navigate_to_tab,
                    args=("3. Evidence & Jira Defects",),
                )


# ==============================================================================
# TAB 3: Evidence Viewer & Jira Defect Assistant
# ==============================================================================
elif selected_nav == "3. Evidence & Jira Defects":
    st.subheader("Execution Evidence & Jira Defect Assistant")
    exec_run: Optional[ExecutionRun] = st.session_state.execution_run

    if not exec_run:
        st.info("No execution runs recorded yet. Execute tests in Tab 2 to view results.")
    else:
        # KPI Summary Cards
        k1, k2, k3, k4 = st.columns(4)
        k1.metric("Total Tests", exec_run.total_tests)
        k2.metric("Passed", exec_run.passed_tests)
        k3.metric("Failed", exec_run.failed_tests)
        duration_s = (exec_run.finished_at - exec_run.started_at).total_seconds() if exec_run.finished_at else 0
        k4.metric("Total Duration", f"{duration_s:.1f}s")

        st.markdown("---")
        st.markdown("#### Test Case Outcomes")
        for res in exec_run.results:
            is_pass = res.outcome == TestOutcome.PASS
            status_label = "PASS" if is_pass else "FAIL"
            matching_tc = next((t for t in (st.session_state.test_suite.test_cases if st.session_state.test_suite else []) if t.id == res.test_case_id), None)
            tc_title_part = f" — {matching_tc.title} ({matching_tc.category.value.upper()})" if matching_tc else ""
            with st.expander(f"[{status_label}] **{res.test_case_id}**{tc_title_part} ({res.duration_seconds}s)", expanded=not is_pass):
                if not is_pass:
                    c_fail_info, c_fail_btn = st.columns([4, 1])
                    with c_fail_info:
                        st.error(f"**Failure Diagnosis:** {res.failure_message}")
                        st.caption(f"Classification: `{res.classification.value}`")
                    with c_fail_btn:
                        if res.screenshot_path and Path(res.screenshot_path).resolve().exists():
                            with st.popover("View Error Evidence", use_container_width=True):
                                st.image(str(Path(res.screenshot_path).resolve()), caption=f"Error Evidence: {res.test_case_id}", use_container_width=True)

                # Step-by-Step Execution Verification
                st.markdown("##### Step-by-Step Execution Verification")
                for s in res.step_results:
                    sc1, sc2, sc3, sc4, sc5 = st.columns([1, 2, 4, 1.5, 1.5])
                    with sc1:
                        st.markdown(f"**Step {s.step_number}**")
                    with sc2:
                        st.markdown(f"`{s.action.value.upper()}`")
                    with sc3:
                        st.caption(s.error_message or "Execution verified successfully")
                    with sc4:
                        st.markdown('<span class="badge-pass">Pass</span>' if s.passed else '<span class="badge-fail">Fail</span>', unsafe_allow_html=True)
                    with sc5:
                        shot_path = getattr(s, "screenshot_path", None)
                        if shot_path and Path(shot_path).resolve().exists():
                            with st.popover("View Screenshot", use_container_width=True):
                                st.image(str(Path(shot_path).resolve()), caption=f"Step {s.step_number}: {s.action.value.upper()}", use_container_width=True)
                        else:
                            st.caption("—")

        # Jira Report Synchronization
        target_issue_key = st.session_state.jira_requirement.key if st.session_state.jira_requirement else ""
        st.markdown("---")
        if not target_issue_key:
            st.info("Ingest a Jira requirement in Tab 1 to enable report synchronization and defect linking.")
        else:
            st.markdown(f"### Jira Report Synchronization (`{target_issue_key}`)")
            rep_col1, rep_col2 = st.columns([1, 1])
            with rep_col1:
                if st.button(f"Attach Executive PDF Report to Jira ({target_issue_key})", type="primary", use_container_width=True):
                    with st.spinner("Compiling publication-ready PDF audit report and uploading to Jira Cloud..."):
                        try:
                            fresh_jira_client = JiraClient()
                            pdf_path = ExecutionReportGenerator.save_pdf_report(
                                run=exec_run,
                                suite=st.session_state.test_suite,
                                requirement=st.session_state.jira_requirement,
                                approval=st.session_state.approval_record,
                            )
                            md_path = ExecutionReportGenerator.save_report_file(
                                run=exec_run,
                                suite=st.session_state.test_suite,
                                requirement=st.session_state.jira_requirement,
                                approval=st.session_state.approval_record,
                            )
                            fresh_jira_client.attach_file(target_issue_key, str(pdf_path), filename=f"Execution_Report_{exec_run.run_id}.pdf")
                            fresh_jira_client.attach_file(target_issue_key, str(md_path), filename=f"Execution_Report_{exec_run.run_id}.md")
                            fresh_jira_client.add_comment(
                                target_issue_key,
                                f"Automated Playwright Test Suite execution complete for {target_issue_key}.\n"
                                f"• Total Scenarios: {exec_run.total_tests}\n"
                                f"• Passed: {exec_run.passed_tests}\n"
                                f"• Failed: {exec_run.failed_tests}\n"
                                f"Detailed audit PDF report attached: [Execution_Report_{exec_run.run_id}.pdf]."
                            )
                            st.success(f"PDF Audit Report `{pdf_path.name}` attached and comment posted to Jira `{target_issue_key}`. View at: {settings.jira_base_url}/browse/{target_issue_key}")
                        except Exception as rep_err:
                            st.error(f"Failed to attach PDF report to Jira: {rep_err}")

            with rep_col2:
                try:
                    pdf_dl_path = Path("artifacts/reports").resolve() / f"Execution_Report_{exec_run.run_id}.pdf"
                    if not pdf_dl_path.exists():
                        pdf_dl_path = ExecutionReportGenerator.save_pdf_report(
                            run=exec_run,
                            suite=st.session_state.test_suite,
                            requirement=st.session_state.jira_requirement,
                            approval=st.session_state.approval_record,
                        )
                    with open(pdf_dl_path, "rb") as f:
                        st.download_button(
                            label="Download Audit PDF Report",
                            data=f.read(),
                            file_name=f"Execution_Report_{exec_run.run_id}.pdf",
                            mime="application/pdf",
                            use_container_width=True,
                        )
                except Exception:
                    pass

        # Defect Assistant (If there are failures)
        if exec_run.failed_tests > 0:
            st.markdown("---")
            st.markdown("### Jira Defect Assistant")
            for res in exec_run.results:
                if res.outcome == TestOutcome.FAIL:
                    evidence_shots = [
                        str(Path(s.screenshot_path).resolve()) for s in res.step_results
                        if getattr(s, "screenshot_path", None) and Path(s.screenshot_path).resolve().exists()
                    ]
                    if not evidence_shots and res.screenshot_path and Path(res.screenshot_path).resolve().exists():
                        evidence_shots = [str(Path(res.screenshot_path).resolve())]

                    raw_msg = (res.failure_message or "Assertion failed").splitlines()[0].strip()
                    if len(raw_msg) > 160:
                        raw_msg = raw_msg[:157] + "..."
                    defect_summary = f"[Defect] Test Failure in {res.test_case_id}: {raw_msg}"

                    repro_steps = []
                    if st.session_state.test_suite:
                        matching_tc = next((tc for tc in st.session_state.test_suite.test_cases if tc.id == res.test_case_id), None)
                        if matching_tc:
                            repro_steps = [f"{s.action.value.upper()} ({s.selector_value or s.input_value or ''}): {s.description}" for s in matching_tc.steps]

                    defect = DefectDraft(
                        draft_id=f"DRAFT-{res.test_case_id}",
                        parent_issue_key=target_issue_key or "",
                        test_case_id=res.test_case_id,
                        summary=defect_summary,
                        steps_to_reproduce=repro_steps,
                        expected_result="Test assertion should pass on target application.",
                        actual_result=res.failure_message or "Assertion failed",
                        evidence_paths=evidence_shots,
                    )

                    st.markdown(f"**Proposed Bug Ticket for `{res.test_case_id}`:**")
                    st.code(defect.to_markdown_description(), language="markdown")

                    if evidence_shots:
                        st.markdown("**Defect Evidence Captured:**")
                        shot_cols = st.columns(min(len(evidence_shots), 3))
                        for idx, shot in enumerate(evidence_shots):
                            with shot_cols[idx % len(shot_cols)]:
                                st.image(shot, caption=f"Evidence {idx+1}", use_container_width=True)

                    if st.button(f"Submit Defect for {res.test_case_id} to Jira Cloud", key=f"btn_bug_{res.test_case_id}", type="primary"):
                        with st.spinner("Creating defect ticket in Jira Cloud and uploading failure evidence..."):
                            try:
                                fresh_jira_client = JiraClient()
                                primary_shot = evidence_shots[0] if evidence_shots else None
                                issue_proj = target_issue_key.split("-")[0] if "-" in target_issue_key else "KAN"
                                created_bug_key = fresh_jira_client.create_defect(
                                    project_key=issue_proj,
                                    summary=defect.summary,
                                    description_text=defect.to_markdown_description(),
                                    parent_issue_key=target_issue_key or None,
                                    screenshot_path=primary_shot,
                                )
                                if len(evidence_shots) > 1:
                                    for extra_shot in evidence_shots[1:]:
                                        try:
                                            fresh_jira_client.attach_file(created_bug_key, extra_shot)
                                        except Exception:
                                            pass
                                st.success(f"Jira Defect Ticket `{created_bug_key}` created successfully and linked to `{target_issue_key}`. View at: {settings.jira_base_url}/browse/{created_bug_key}")
                            except Exception as bug_err:
                                st.error(f"Failed to create defect in Jira: {bug_err}")
