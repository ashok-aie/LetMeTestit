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
from datetime import datetime
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
from app.policies.guardrails import PolicyEngine, is_credential_step, mask_step_credential_display
from app.reporting.reporter import ExecutionReportGenerator
from app.storage.repository import (
    save_regression_suite,
    list_regression_suites,
    load_regression_suite,
    delete_regression_suite,
    get_cached_suite_for_requirement,
    list_reusable_flows,
    get_reusable_flow_steps,
    save_reusable_flow,
    get_learned_selectors,
    save_learned_selector,
    list_execution_runs,
    save_golden_example,
    list_golden_examples,
    save_correction,
    list_corrections,
    get_testing_standards,
)




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
if "pending_tab" not in st.session_state:
    st.session_state.pending_tab = None
if "main_tab_selector" not in st.session_state:
    st.session_state.main_tab_selector = "1. Ingest & Design"
if "synthesis_logs" not in st.session_state:
    st.session_state.synthesis_logs = []


# ==============================================================================
# Custom CSS Styling (Johnson & Johnson Red & White Theme)
# ==============================================================================
st.markdown(
    """
    <style>
    /* Completely hide the left sidebar and its collapse control */
    [data-testid="stSidebar"], [data-testid="collapsedControl"] {
        display: none !important;
    }

    :root {
        --primary: #D51900;           /* Signature J&J Scarlet Red */
        --primary-dark: #B81500;      /* Deep Crimson */
        --primary-light: #FFF1F0;     /* Soft warm white / light crimson tint */
        --primary-border: #FFCCC7;    /* Subtle red border */
        --border-color: #E5E7EB;
        --text-main: #111827;
        --text-muted: #64748B;
    }

    /* Johnson & Johnson Header Banner */
    .jnj-banner {
        background: #FFFFFF;
        border: 1px solid #E5E7EB;
        border-top: 4px solid #D51900;
        border-radius: 10px;
        padding: 0.95rem 1.4rem;
        margin-bottom: 0.75rem;
        box-shadow: 0 4px 14px rgba(213, 25, 0, 0.06);
    }
    .jnj-brand-row {
        display: flex;
        align-items: center;
        margin-bottom: 0.35rem;
    }
    .jnj-badge {
        background-color: #D51900;
        color: #FFFFFF;
        font-size: 0.78rem;
        font-weight: 600;
        padding: 3px 10px;
        border-radius: 4px;
        letter-spacing: 0.2px;
        text-transform: none;
        display: inline-block;
        font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    }
    .jnj-banner-title {
        font-size: 2.15rem;
        font-weight: 800;
        color: #111827;
        margin: 0;
        line-height: 1.2;
        letter-spacing: -0.5px;
    }
    .jnj-highlight {
        color: #D51900;
        font-style: italic;
        font-weight: 900;
    }
    .step-log-item {
        padding: 0.5rem 0.8rem;
        margin: 0.25rem 0;
        border-radius: 0 6px 6px 0;
        background-color: #FFFFFF;
        border: 1px solid #F3F4F6;
        border-left: 3px solid #D51900;
        font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
        font-size: 0.85rem;
        color: #1E293B;
        box-shadow: 0 1px 2px rgba(0,0,0,0.02);
    }
    .badge-pass {
        display: inline-block;
        padding: 2px 8px;
        font-size: 0.75rem;
        font-weight: 600;
        color: #15803D;
        background-color: #DCFCE7;
        border: 1px solid #BBF7D0;
        border-radius: 9999px;
    }
    .badge-fail {
        display: inline-block;
        padding: 2px 8px;
        font-size: 0.75rem;
        font-weight: 600;
        color: #B91C1C;
        background-color: #FEE2E2;
        border: 1px solid #FECACA;
        border-radius: 9999px;
    }

    /* Tabs styling - Johnson & Johnson Red & White pills */
    div[data-testid="stRadio"] div[role="radiogroup"] {
        gap: 10px !important;
        margin-bottom: 1.2rem !important;
        flex-wrap: wrap !important;
    }
    div[data-testid="stRadio"] label {
        background-color: #FFFFFF !important;
        border: 1px solid #E5E7EB !important;
        padding: 8px 18px !important;
        border-radius: 8px !important;
        cursor: pointer !important;
        font-weight: 600 !important;
        color: #374151 !important;
        transition: all 0.2s ease-in-out !important;
        box-shadow: 0 1px 3px rgba(0, 0, 0, 0.04) !important;
    }
    div[data-testid="stRadio"] label:hover {
        border-color: #D51900 !important;
        background-color: #FFF1F0 !important;
        color: #D51900 !important;
        transform: translateY(-1px);
    }
    div[data-testid="stRadio"] label:has(input:checked) {
        background-color: #D51900 !important;
        border-color: #D51900 !important;
        color: #FFFFFF !important;
        box-shadow: 0 3px 10px rgba(213, 25, 0, 0.3) !important;
    }
    div[data-testid="stRadio"] label:has(input:checked) p {
        color: #FFFFFF !important;
        font-weight: 700 !important;
    }
    div[data-testid="stRadio"] div[role="radiogroup"] label > div > div:first-child {
        display: none !important;
    }

    /* Popover Settings Button */
    div[data-testid="stPopover"] > button {
        border-radius: 8px !important;
        border: 1px solid #D51900 !important;
        color: #D51900 !important;
        background-color: #FFFFFF !important;
        font-weight: 700 !important;
        box-shadow: 0 2px 6px rgba(213, 25, 0, 0.08) !important;
        transition: all 0.2s ease-in-out !important;
    }
    div[data-testid="stPopover"] > button:hover {
        background-color: #FFF1F0 !important;
        border-color: #B81500 !important;
        color: #B81500 !important;
    }

    /* Buttons styling - Johnson & Johnson Primary Red */
    button[kind="primary"], .stButton > button[type="primary"] {
        background-color: #D51900 !important;
        border-color: #D51900 !important;
        color: #FFFFFF !important;
        font-weight: 600 !important;
        border-radius: 6px !important;
        box-shadow: 0 2px 5px rgba(213, 25, 0, 0.22) !important;
        transition: all 0.2s ease-in-out !important;
    }
    button[kind="primary"]:hover, .stButton > button[type="primary"]:hover {
        background-color: #B81500 !important;
        border-color: #B81500 !important;
        box-shadow: 0 4px 12px rgba(213, 25, 0, 0.35) !important;
    }
    button[kind="secondary"], .stButton > button[kind="secondary"] {
        background-color: #FFFFFF !important;
        border: 1px solid #D51900 !important;
        color: #D51900 !important;
        font-weight: 600 !important;
        border-radius: 6px !important;
    }
    button[kind="secondary"]:hover, .stButton > button[kind="secondary"]:hover {
        background-color: #FFF1F0 !important;
        border-color: #B81500 !important;
        color: #B81500 !important;
    }

    /* Expanders styling */
    div[data-testid="stExpander"] {
        background-color: #FFFFFF !important;
        border: 1px solid #E5E7EB !important;
        border-radius: 8px !important;
    }
    div[data-testid="stExpander"]:hover {
        border-color: #FFCCC7 !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# ==============================================================================
# Header with Right-Side Three-Dot Menu (Replacing Left Sidebar)
# ==============================================================================
header_col1, header_col2 = st.columns([11, 1], vertical_alignment="center")

with header_col1:
    st.markdown(
        """
        <div class="jnj-banner">
            <div class="jnj-banner-title">
                Let me <span class="jnj-highlight">TEST</span> it....!
            </div>
            <div class="jnj-brand-row" style="margin-top: 0.4rem; margin-bottom: 0;">
                <span class="jnj-badge">Agentic Quality Engineering Platform</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

with header_col2:
    with st.popover("⋮", use_container_width=True):
        st.markdown("### System Diagnostics")
        jira_client = JiraClient()
        is_jira_ok = jira_client.is_connected()
        if is_jira_ok:
            st.success(f"**Jira Cloud:** Connected\n- `{settings.jira_base_url}`\n- User: `{settings.jira_user_email}`")
        else:
            st.warning("**Jira Cloud:** Disconnected / Token needed")

        st.success(
            f"**Target System:** SAP S/4HANA\n"
            f"- Host: `{settings.sap_host_domain}`\n"
            f"- Client: `{settings.sap_client}` | User: `{settings.sap_username or 'MYRAR1'}`"
        )

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


# ==============================================================================
# Seamless Tab Navigation
# ==============================================================================
def navigate_to_tab(tab_name: str) -> None:
    st.session_state.pending_tab = tab_name

if st.session_state.get("pending_tab"):
    st.session_state["main_tab_selector"] = st.session_state.pop("pending_tab")

nav_tabs = ["1. Ingest & Design", "2. Review Center", "3. Evidence & Jira Defects", "4. Regression Repository", "5. Admin"]
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
    with st.expander("Agent Model & Jira Configuration", expanded=True):
        cfg_col1, cfg_col2, cfg_col3 = st.columns(3)

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

    st.markdown("---")
    st.subheader("Test Design & Requirements Ingestion")

    if st.session_state.test_suite:
        st_suite = st.session_state.test_suite
        st.info(
            f"📌 **Active Staged Suite:** `{st_suite.suite_id}` ({len(st_suite.test_cases)} scenarios) | "
            f"Requirement: `{st_suite.requirement_key}` — *New test cases or recordings will be appended to this suite.*"
        )

    col1, col2 = st.columns([2, 1])
    with col1:
        issue_key_input = st.text_input(
            "JIRA ID",
            value="",
            placeholder="e.g. SAP-101, KAN-10, KA-23",
            help="Enter Jira issue key from your project",
            key="jira_issue_key_field",
        )
    with col2:
        st.write("")
        st.write("")
        fetch_btn = st.button("Read User Story & Create Test Scripts", type="primary", use_container_width=True)

    st.markdown("##### Or Design Directly Without / Alongside Jira:")
    direct_col1, direct_col2 = st.columns(2)
    with direct_col1:
        with st.popover("➕ New Test Case", use_container_width=True):
            st.markdown("**Create New Test Case (Manual Steps)**")
            st.caption("Define a test scenario and enter manual browser steps without touching Playwright code.")
            curr_suite = st.session_state.test_suite
            curr_cnt = len(curr_suite.test_cases) if curr_suite else 0
            new_tc_title = st.text_input(
                "Scenario Title:",
                value=f"Manual Scenario {curr_cnt + 1}",
                key="t1_new_tc_pop_title",
            )
            new_tc_obj = st.text_input(
                "Objective:",
                value="Verify user action on SAP screen",
                key="t1_new_tc_pop_obj",
            )
            new_tc_cat = st.selectbox(
                "Category:",
                options=["positive", "negative", "boundary", "validation"],
                index=0,
                key="t1_new_tc_pop_cat",
            )
            new_tc_expected = st.text_input(
                "Expected Result:",
                value="Action completed successfully without errors",
                key="t1_new_tc_pop_expected",
            )
            new_tc_group = st.text_input(
                "Functional Group / Module:",
                value="General",
                key="t1_new_tc_pop_group",
                placeholder="e.g. Authentication, Quotations, Orders",
            )
            include_sap_logon = st.checkbox(
                "Include standard SAP Fiori Logon & Logoff lifecycle",
                value=True,
                key="t1_new_tc_pop_include_sap",
            )
            new_tc_persist_reg = st.checkbox(
                "Persist directly into Regression Suite Repository",
                value=True,
                key="t1_new_tc_pop_persist_reg",
                help="Automatically saves or updates the suite in data/cases/ upon creation",
            )

            if st.button("Create Test Case & Add Steps", type="primary", use_container_width=True, key="t1_btn_create_manual_tc"):
                curr_suite = st.session_state.test_suite
                next_tc_num = (len(curr_suite.test_cases) + 1) if curr_suite else 1
                next_id = f"TC-{next_tc_num:02d}"
                req_k = curr_suite.requirement_key if curr_suite else (issue_key_input.strip() if issue_key_input.strip() else "MANUAL-01")
                if include_sap_logon:
                    init_steps = [
                        TestStep(step_number=1, action=ActionType.NAVIGATE, input_value=settings.sap_fiori_url, description="Open SAP Fiori Logon screen"),
                        TestStep(step_number=2, action=ActionType.FILL, locator_strategy=LocatorStrategy.CSS, selector_value="#USERNAME_FIELD-inner", input_value=(settings.sap_username or "MYRAR1").strip(), description="Enter SAP username"),
                        TestStep(step_number=3, action=ActionType.FILL, locator_strategy=LocatorStrategy.CSS, selector_value="#PASSWORD_FIELD-inner", input_value=(settings.sap_password or "Pass23#$").strip(), description="Enter SAP password"),
                        TestStep(step_number=4, action=ActionType.CLICK, locator_strategy=LocatorStrategy.CSS, selector_value="#LOGIN_LINK", description="Click Log On button"),
                        TestStep(step_number=5, action=ActionType.ASSERT_TEXT, locator_strategy=LocatorStrategy.CSS, selector_value="body", expected_value="Home", description="Assert SAP Fiori Launchpad loaded"),
                        TestStep(step_number=6, action=ActionType.CLICK, locator_strategy=LocatorStrategy.CSS, selector_value="#userActionsMenuHeaderButton, #meAreaHeaderButton", description="Click User Profile Avatar Menu"),
                        TestStep(step_number=7, action=ActionType.CLICK, locator_strategy=LocatorStrategy.CSS, selector_value="button:has-text('Sign Out'), text='Sign Out'", description="Click Sign Out"),
                        TestStep(step_number=8, action=ActionType.CLICK, locator_strategy=LocatorStrategy.CSS, selector_value="button:has-text('OK'), text='OK'", description="Confirm Sign Out dialog"),
                        TestStep(step_number=9, action=ActionType.ASSERT_TEXT, locator_strategy=LocatorStrategy.CSS, selector_value="body", expected_value="logged off", description="Verify returned to Logoff screen"),
                    ]
                else:
                    init_steps = [
                        TestStep(step_number=1, action=ActionType.NAVIGATE, input_value=settings.sap_fiori_url, description="Open SAP target screen"),
                    ]
                new_tc = TestCase(
                    id=next_id,
                    requirement_key=req_k,
                    source_ac_id=f"AC-MANUAL-{next_tc_num}",
                    title=new_tc_title.strip() or f"Manual Scenario {next_id}",
                    objective=new_tc_obj.strip() or "Manual test scenario",
                    expected_result=new_tc_expected.strip() or "Success",
                    category=TestCategory(new_tc_cat),
                    group=new_tc_group.strip() or "General",
                    steps=init_steps,
                )
                if not st.session_state.test_suite:
                    st.session_state.test_suite = TestSuite(
                        suite_id=f"SUITE-{req_k}-{datetime.now().strftime('%Y%m%d%H%M')}",
                        requirement_key=req_k,
                        target_application="SAP S/4HANA Fiori",
                        test_cases=[new_tc],
                    )
                else:
                    st.session_state.test_suite.test_cases.append(new_tc)
                suite = st.session_state.test_suite

                if new_tc_persist_reg:
                    try:
                        save_regression_suite(suite, last_run_status="Manual Draft")
                    except Exception:
                        pass

                st.session_state[f"editing_{new_tc.id}"] = True
                st.session_state.approval_record = None
                st.session_state.flash_success = f"Scenario '{new_tc.id}: {new_tc.title}' created and grouped under '{new_tc.group}'! Step customization opened below."
                navigate_to_tab("2. Review Center")
                st.rerun()

    with direct_col2:
        with st.popover("Record via Browser", use_container_width=True):
            st.markdown("**Record a New Test (Playwright Codegen)**")
            st.caption("Launches interactive browser recorder to capture clicks, inputs, and navigations.")
            curr_suite = st.session_state.test_suite
            curr_cnt = len(curr_suite.test_cases) if curr_suite else 0
            rec_title = st.text_input(
                "Scenario Title:",
                value=f"Recorded Flow {curr_cnt + 1}",
                key="t1_rec_pop_title",
            )
            rec_url = st.text_input(
                "Target URL:",
                value=settings.sap_fiori_url,
                key="t1_rec_pop_url",
            )
            rec_group = st.text_input(
                "Functional Group / Module:",
                value="Recorded",
                key="t1_rec_pop_group",
                placeholder="e.g. Authentication, Quotations, Orders",
            )
            rec_persist_reg = st.checkbox(
                "Persist directly into Regression Suite Repository",
                value=True,
                key="t1_rec_pop_persist_reg",
                help="Automatically saves or updates the suite in data/cases/ upon recording completion",
            )
            if st.button("Launch Recorder", type="primary", use_container_width=True, key="t1_btn_launch_rec_pop"):
                with st.spinner("Launching Playwright Codegen... Perform your actions in Chromium and close the browser window when finished."):
                    try:
                        import importlib
                        import app.browser.recorder
                        importlib.reload(app.browser.recorder)
                        recorded_code = app.browser.recorder.record_playwright_session(target_url=rec_url.strip())
                        st.session_state.recorded_script_raw = recorded_code
                        if recorded_code.strip():
                            parsed_steps = parse_recorded_script(recorded_code, default_url=rec_url.strip())
                            curr_suite = st.session_state.test_suite
                            next_tc_num = (len(curr_suite.test_cases) + 1) if curr_suite else 1
                            next_id = f"TC-{next_tc_num:02d}"
                            req_k = curr_suite.requirement_key if curr_suite else (issue_key_input.strip() if issue_key_input.strip() else "REC-01")
                            clean_title = rec_title.strip() or f"Recorded Scenario {next_id}"
                            chosen_group = rec_group.strip() or "Recorded"
                            new_tc = create_test_case_from_recording(
                                title=clean_title,
                                steps=parsed_steps,
                                requirement_key=req_k,
                                tc_id=next_id,
                                group=chosen_group,
                            )
                            if not st.session_state.test_suite:
                                st.session_state.test_suite = TestSuite(
                                    suite_id=f"SUITE-{req_k}-{datetime.now().strftime('%Y%m%d%H%M')}",
                                    requirement_key=req_k,
                                    target_application="SAP S/4HANA Fiori",
                                    test_cases=[new_tc],
                                )
                            else:
                                st.session_state.test_suite.test_cases.append(new_tc)
                            suite = st.session_state.test_suite

                            # 1. Export standalone Playwright Python script file
                            clean_req = suite.requirement_key.replace("-", "_").lower()
                            script_filename = f"recorded_{clean_req}_{next_id.lower()}.py"
                            rec_script_dest = Path("artifacts/scripts").resolve() / script_filename
                            rec_script_dest.write_text(recorded_code, encoding="utf-8")
                            rec_script_alt = Path("app/browser/test_scripts").resolve() / script_filename
                            rec_script_alt.write_text(recorded_code, encoding="utf-8")

                            # 2. Harvest all verified selectors into Continuous Learning Knowledge Catalog
                            learned_cnt = 0
                            for stp in parsed_steps:
                                if stp.selector_value:
                                    try:
                                        save_learned_selector(
                                            element_label=stp.description or stp.selector_value,
                                            selector=stp.selector_value,
                                            strategy=stp.locator_strategy.value if stp.locator_strategy else "css",
                                            action=stp.action.value,
                                            role_type=stp.role_name,
                                            app_domain="SAP S/4HANA",
                                            notes=f"Harvested from recording: {clean_title}",
                                        )
                                        learned_cnt += 1
                                    except Exception:
                                        pass

                            # 3. Save as Reusable Flow Template in data/library/flows.json
                            try:
                                save_reusable_flow(
                                    flow_name=f"Recorded: {clean_title}",
                                    description=f"Recorded workflow from Playwright Codegen for {suite.requirement_key}",
                                    category="Recorded Flow",
                                    steps=parsed_steps,
                                )
                            except Exception:
                                pass

                            # 4. Save into Golden Examples Knowledge Base for future LLM few-shot synthesis
                            try:
                                save_golden_example(
                                    pattern=f"Recorded Workflow ({clean_title})",
                                    description=f"Human-recorded interaction sequence on {rec_url.strip()}",
                                    test_case=new_tc,
                                )
                            except Exception:
                                pass

                            # 5. Auto-persist into Regression Suite Repository
                            if rec_persist_reg:
                                try:
                                    save_regression_suite(suite, last_run_status="Recorded (Unexecuted)")
                                except Exception:
                                    pass

                            st.session_state.approval_record = None
                            st.session_state.flash_success = (
                                f"✅ Recorded scenario '{new_tc.id}: {new_tc.title}' added!\n\n"
                                f"- **Playwright Script Saved:** `artifacts/scripts/{script_filename}`\n"
                                f"- **Regression Suite:** Automatically updated in `data/cases/{suite.suite_id}.json`\n"
                                f"- **Learned Selectors Added:** `{learned_cnt}` elements added to Knowledge Catalog\n"
                                f"- **Reusable Flow Created:** `Recorded: {clean_title}` in Flow Library\n"
                                f"- **Golden Knowledge Base:** Pattern saved for future LLM test generation"
                            )
                            navigate_to_tab("2. Review Center")
                            st.rerun()
                        else:
                            st.warning("No interactions were recorded or the browser was closed before any actions.")
                    except Exception as e:
                        st.error(f"Recording session failed: {e}")

    # Synthesis Execution
    if fetch_btn and issue_key_input:
        st.session_state.synthesis_logs = []

        # Step 1: Fetching requirement
        st.markdown("**Step 1:** Reading User Story from Jira Cloud...")
        try:
            requirement = jira_client.get_issue(issue_key_input.strip())
            st.session_state.jira_requirement = requirement
            st.write(f"Ingested: **{requirement.key}** — *{requirement.summary}*")
        except Exception as e:
            st.error(f"Could not fetch issue '{issue_key_input}': {e}")
            st.stop()

        # Step 2: Extracting Acceptance Criteria dynamically
        st.markdown("**Step 2:** Extracting Acceptance Criteria from User Story...")
        raw_lines = [l.strip() for l in requirement.description_text.splitlines() if l.strip()]
        
        # 1. Normalize two-line numbered lists (e.g., line 1 is "1", line 2 is "Login...")
        merged_lines = []
        i = 0
        while i < len(raw_lines):
            line = raw_lines[i]
            if line.isdigit() and i + 1 < len(raw_lines):
                merged_lines.append(f"{line}. {raw_lines[i + 1]}")
                i += 2
            else:
                merged_lines.append(line)
                i += 1

        ac_list = []

        # 2. Check for an explicit "Acceptance Criteria" header block
        ac_header_idx = -1
        for idx, l in enumerate(merged_lines):
            if re.match(r"^(acceptance\s*criteria|ac:?|scenarios?):?", l, re.IGNORECASE):
                ac_header_idx = idx
                break

        if ac_header_idx != -1:
            for l in merged_lines[ac_header_idx + 1:]:
                if re.match(r"^(preconditions?|notes?|test\s*steps?|procedure):?", l, re.IGNORECASE):
                    break
                clean_l = l.strip()
                if len(clean_l) > 4:
                    bullet_text = re.sub(r"^(\d+[\.\)]|[-*•#]|ac[:\-\d]*)\s*", "", clean_l, flags=re.IGNORECASE).strip()
                    if bullet_text:
                        ac_list.append(AcceptanceCriterion(id=f"AC-{len(ac_list)+1:02d}", text=bullet_text))

        # 3. Check if input is a sequential numbered procedural script (e.g. >= 4 steps, like KAN-23 or KAN-25)
        if not ac_list:
            numbered_steps = [
                re.sub(r"^(\d+[\.\)]|step\s*\d+[:\.]?)\s*", "", l, flags=re.IGNORECASE).strip()
                for l in merged_lines
                if re.match(r"^(\d+[\.\)]|step\s*\d+[:\.]?)\s+", l, re.IGNORECASE)
            ]
            if len(numbered_steps) >= 4:
                # Group into a single cohesive End-to-End Procedural Flow test scenario
                e2e_text = f"End-to-End Procedural Flow ({len(numbered_steps)} steps): " + " -> ".join(numbered_steps)
                ac_list.append(AcceptanceCriterion(id="AC-01", text=e2e_text))

        # 4. Check if input has sequential procedural action keywords even without strict numbering
        if not ac_list:
            procedural_keywords = ["login", "navigate", "create", "sold-to", "items", "dates", "price", "save", "released", "accept", "logout", "revenue", "contract"]
            procedural_matches = [l for l in merged_lines if any(k in l.lower() for k in procedural_keywords)]
            if len(procedural_matches) >= 5 and len(merged_lines) <= 30:
                e2e_text = f"End-to-End Business Flow ({len(procedural_matches)} actions): " + " -> ".join(procedural_matches)
                ac_list.append(AcceptanceCriterion(id="AC-01", text=e2e_text))

        # 5. Standard bullet / line parsing fallback
        if not ac_list:
            for line in merged_lines:
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
            ac_list.append(AcceptanceCriterion(id="AC-01", text=requirement.summary.strip() or "Standard Functional Verification"))

        requirement.acceptance_criteria = ac_list
        st.session_state.acceptance_criteria = ac_list
        st.write(f"Extracted **{len(ac_list)}** Acceptance Criteria dynamically from `{requirement.key}`.")

        # Show Requirement Description AND Extracted Acceptance Criteria together
        with st.expander(f"Requirement Details: `{requirement.key}` — {requirement.summary}", expanded=True):
            st.markdown(requirement.description_text)
            st.markdown("#### Extracted Acceptance Criteria")
            for ac in requirement.acceptance_criteria:
                st.markdown(f"**[{ac.id}]** {ac.text}")

        # Step 3: Synthesis
        st.markdown(f"**Step 3:** Generating SAP Test Scripts using {provider_choice} ({selected_model})...")
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
            import importlib
            import app.test_design.generator
            importlib.reload(app.test_design.generator)
            from app.test_design.generator import TestDesigner

            target_app_url = settings.sap_fiori_url
            designer = TestDesigner(llm_client=active_llm)
            suite = designer.generate_suite(
                requirement=requirement,
                target_base_url=target_app_url,
                progress_callback=on_progress,
            )
            if suite and suite.test_cases:
                seen_ids = set()
                for i, tc in enumerate(suite.test_cases, start=1):
                    if not tc.id or tc.id in seen_ids:
                        tc.id = f"TC-{i:02d}"
                    seen_ids.add(tc.id)
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
    if suite and suite.test_cases:
        seen_ids = set()
        for i, tc in enumerate(suite.test_cases, start=1):
            if not tc.id or tc.id in seen_ids:
                tc.id = f"TC-{i:02d}"
            seen_ids.add(tc.id)

    if "flash_success" in st.session_state and st.session_state.flash_success:
        st.success(st.session_state.flash_success)
        st.session_state.flash_success = None

    if not suite:
        st.info("No test suite staged for review. Ingest a Jira requirement, create a new test case, or record via browser in Tab 1.")
        if st.button("← Go to Tab 1 (Ingest & Design)", type="primary", key="btn_goto_tab1_empty"):
            navigate_to_tab("1. Ingest & Design")
            st.rerun()
    else:
        header_col1, header_col2, header_col3, header_col4 = st.columns([2.5, 1.2, 1.3, 1.1])
        with header_col1:
            st.markdown(f"**Staged Suite:** `{suite.suite_id}` | **Total Scenarios:** `{len(suite.test_cases)}`")
        with header_col2:
            if st.button("➕ Add Scenario (Tab 1)", use_container_width=True, help="Go to Tab 1 to add manual or recorded test cases"):
                navigate_to_tab("1. Ingest & Design")
                st.rerun()
        with header_col3:
            if st.button("💾 Save to Regression", use_container_width=True, help="Saves this verified suite into the Regression Suite Repository"):
                saved_f = save_regression_suite(suite)
                st.success(f"Saved: `{saved_f.name}` in `data/cases/`")
        with header_col4:
            if st.button("Export Script 🐍", use_container_width=True, help="Exports standalone Playwright script into app/browser/test_scripts/ and artifacts/scripts/"):
                from app.browser.exporter import export_suite_to_playwright_script
                exported_path = export_suite_to_playwright_script(suite)
                st.success(f"Exported: `{exported_path.name}` in `artifacts/scripts/`")

        approval: Optional[ApprovalRecord] = st.session_state.approval_record
        is_approved = approval is not None and approval.decision == ApprovalDecision.APPROVED

        if is_approved:
            st.success(f"**APPROVED & SIGNED** by `{approval.reviewer}` on `{approval.timestamp.strftime('%Y-%m-%d %H:%M:%S UTC')}`")
        elif approval and approval.decision == ApprovalDecision.REJECTED:
            st.error(f"**REJECTED** by `{approval.reviewer}`. Comments: {approval.comments}")
        else:
            st.warning("Pending Human Review: Review test steps below, edit or record new scenarios, then approve.")

        # ----------------------------------------------------------------------
        # Test Scenarios: Selection & Custom Execution Sequence
        # ----------------------------------------------------------------------
        st.markdown("### Test Scenarios & Execution Scope")
        sc_col1, sc_col2, sc_col3 = st.columns([1.5, 1.5, 3.5])
        with sc_col1:
            if st.button("✅ Select All Scenarios", use_container_width=True, key="btn_sel_all_scenarios"):
                for c in suite.test_cases:
                    st.session_state[f"exec_chk_{c.id}"] = True
                st.rerun()
        with sc_col2:
            if st.button("❌ Deselect All", use_container_width=True, key="btn_desel_all_scenarios"):
                for c in suite.test_cases:
                    st.session_state[f"exec_chk_{c.id}"] = False
                st.rerun()

        # Module Group Filter and Batch Selection
        distinct_groups = sorted(list(set(getattr(tc, "group", None) or "General" for tc in suite.test_cases)))
        grp_col1, grp_col2, grp_col3 = st.columns([2.0, 1.2, 1.2])
        with grp_col1:
            rev_grp_filter = st.selectbox(
                "Filter Scenarios by Functional Group / Module:",
                options=["All Groups"] + distinct_groups,
                key="rev_grp_filter",
            )
        with grp_col2:
            if st.button("Select Group", use_container_width=True, key="btn_sel_rev_grp", help="Select all scenarios in the filtered group"):
                for c in suite.test_cases:
                    c_grp = getattr(c, "group", None) or "General"
                    if rev_grp_filter == "All Groups" or c_grp == rev_grp_filter:
                        st.session_state[f"exec_chk_{c.id}"] = True
                st.rerun()
        with grp_col3:
            if st.button("Deselect Group", use_container_width=True, key="btn_desel_rev_grp", help="Deselect all scenarios in the filtered group"):
                for c in suite.test_cases:
                    c_grp = getattr(c, "group", None) or "General"
                    if rev_grp_filter == "All Groups" or c_grp == rev_grp_filter:
                        st.session_state[f"exec_chk_{c.id}"] = False
                st.rerun()

        # Compute selected test cases in their current order
        selected_scenarios = [
            tc for tc in suite.test_cases
            if st.session_state.get(f"exec_chk_{tc.id}", True)
        ]
        with sc_col3:
            order_label = " → ".join(tc.id for tc in selected_scenarios) if selected_scenarios else "None (0 selected)"
            st.info(f"**Execution Scope:** `{len(selected_scenarios)} of {len(suite.test_cases)} Selected` | **Order:** `{order_label}`")

        for idx, tc in enumerate(suite.test_cases):
            tc_group = getattr(tc, "group", None) or "General"
            if rev_grp_filter != "All Groups" and tc_group != rev_grp_filter:
                continue

            with st.container():
                st.markdown("---")
                col_chk, col_meta, col_actions = st.columns([0.4, 4.2, 1.4])
                with col_chk:
                    st.write("")
                    st.checkbox(
                        f"Select {tc.id}",
                        value=st.session_state.get(f"exec_chk_{tc.id}", True),
                        key=f"exec_chk_{tc.id}",
                        help=f"Select {tc.id} for execution",
                        label_visibility="collapsed",
                    )
                is_editing = st.session_state.get(f"editing_{tc.id}", False)
                with col_meta:
                    group_badge = f'<span style="background:#ede9fe; color:#5b21b6; border: 1px solid #ddd6fe; padding: 2px 8px; border-radius: 9999px; font-size: 0.75rem; font-weight: 600;">📁 {tc_group}</span>'
                    st.markdown(f"#### **[{tc.id}]** {tc.title} &nbsp;{group_badge}", unsafe_allow_html=True)
                    st.caption(f"Sequence: `#{idx + 1}` | Group: `{tc_group}` | Priority: `{tc.priority}` | Steps: `{len(tc.steps)}`")

                with col_actions:
                    btn_edit_col, btn_del_col = st.columns([1.2, 1.0])
                    with btn_edit_col:
                        if st.button("Edit Steps" if not is_editing else "Close", key=f"btn_edit_tc_{tc.id}", use_container_width=True):
                            st.session_state[f"editing_{tc.id}"] = not is_editing
                            st.rerun()
                    with btn_del_col:
                        if st.button("Delete", key=f"btn_del_tc_{tc.id}", use_container_width=True):
                            suite.test_cases = [c for c in suite.test_cases if c.id != tc.id]
                            for i, c in enumerate(suite.test_cases, start=1):
                                c.id = f"TC-{i:02d}"
                            try:
                                if load_regression_suite(suite.suite_id):
                                    save_regression_suite(suite)
                            except Exception:
                                pass
                            st.session_state.approval_record = None
                            st.success(f"Scenario {tc.id} deleted and suite re-indexed.")
                            st.rerun()

                # Expandable / Minimised Steps & Details (by default minimised unless editing)
                with st.expander(f"View Steps & Details for [{tc.id}] ({len(tc.steps)} steps)", expanded=is_editing):
                    st.markdown(f"**Objective:** {tc.objective}")
                    if not is_editing:
                        step_data = []
                        for s in tc.steps:
                            safe_val, safe_desc = mask_step_credential_display(
                                action=s.action.value,
                                selector=s.selector_value,
                                value=s.input_value or s.expected_value,
                                description=s.description,
                            )
                            step_data.append({
                                "Step #": s.step_number,
                                "Action": s.action.value.upper(),
                                "Strategy": s.locator_strategy.value if s.locator_strategy else "—",
                                "Target Selector": s.selector_value or "—",
                                "Input / Expected": safe_val or "—",
                                "Description": safe_desc,
                            })
                        st.dataframe(step_data, use_container_width=True)
                    else:
                        st.markdown(f"##### Step Editor: [{tc.id}] {tc.title}")
                        if tc.steps:
                            step_data = []
                            for s in tc.steps:
                                safe_val, safe_desc = mask_step_credential_display(
                                    action=s.action.value,
                                    selector=s.selector_value,
                                    value=s.input_value or s.expected_value,
                                    description=s.description,
                                )
                                step_data.append({
                                    "Step #": s.step_number,
                                    "Action": s.action.value.upper(),
                                    "Strategy": s.locator_strategy.value if s.locator_strategy else "—",
                                    "Target Selector": s.selector_value or "—",
                                    "Input / Expected": safe_val or "—",
                                    "Description": safe_desc,
                                })
                            st.dataframe(step_data, use_container_width=True)

                        tab_mod, tab_add, tab_flow = st.tabs(["✏️ Modify / Delete Existing Step", "➕ Add New Step", "⚡ Insert Reusable Flow"])

                        with tab_mod:
                            if not tc.steps:
                                st.info("No steps exist in this scenario yet. Use the 'Add New Step' tab to add your first step.")
                            else:
                                step_nums = [s.step_number for s in tc.steps]
                                e_col1, e_col2 = st.columns([1, 1])
                                with e_col1:
                                    selected_step_num = st.selectbox(
                                        "Select Step to Modify:",
                                        options=step_nums,
                                        format_func=lambda snum: f"Step {snum}: {next((s.action.value.upper() for s in tc.steps if s.step_number == snum), '')} - {mask_step_credential_display('', next((s.selector_value for s in tc.steps if s.step_number == snum), ''), '', next((s.description for s in tc.steps if s.step_number == snum), ''))[1][:35]}",
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
                                    strategy_options = ["css", "text", "test_id", "role"]
                                    curr_strat = current_step.locator_strategy.value if current_step.locator_strategy else "css"
                                    curr_strat_idx = strategy_options.index(curr_strat) if curr_strat in strategy_options else 0
                                    new_strategy = st.selectbox(
                                        "Locator Strategy:",
                                        options=strategy_options,
                                        index=curr_strat_idx,
                                        key=f"edit_strat_{tc.id}_{selected_step_num}",
                                        help="css: CSS selector (#id, .class); text: Visible element text; test_id: data-testid; role: ARIA role",
                                    )
                                with f_col2:
                                    new_selector = st.text_input(
                                        "Target Selector / Text / Value:",
                                        value=current_step.selector_value or "",
                                        key=f"edit_sel_{tc.id}_{selected_step_num}",
                                        placeholder="e.g. #LOGIN_LINK or Sign Out",
                                    )

                                g_col1, g_col2 = st.columns([1, 1])
                                with g_col1:
                                    is_pwd_step = is_credential_step(current_step.selector_value, current_step.description, current_step.input_value) and any(k in (current_step.selector_value or "").lower() or k in (current_step.description or "").lower() for k in ["password", "pwd"])
                                    new_val = st.text_input(
                                        "Input / Expected Value:",
                                        value=current_step.input_value or current_step.expected_value or "",
                                        type="password" if is_pwd_step else "default",
                                        key=f"edit_val_{tc.id}_{selected_step_num}",
                                        placeholder="Value to type, duration (e.g. 5s), or assertion text",
                                    )
                                with g_col2:
                                    safe_desc_init = mask_step_credential_display(
                                        current_step.action.value,
                                        current_step.selector_value,
                                        current_step.input_value,
                                        current_step.description,
                                    )[1]
                                    new_desc = st.text_input(
                                        "Step Description:",
                                        value=safe_desc_init,
                                        key=f"edit_desc_{tc.id}_{selected_step_num}",
                                        placeholder="Describe what this step does",
                                    )

                                act_col1, act_col2 = st.columns([1, 1])
                                with act_col1:
                                    if st.button("Save Step Modification", type="primary", use_container_width=True, key=f"btn_save_{tc.id}_{selected_step_num}"):
                                        old_selector = current_step.selector_value
                                        current_step.action = ActionType(new_action)
                                        current_step.locator_strategy = LocatorStrategy(new_strategy) if new_strategy else None
                                        current_step.selector_value = new_selector.strip() if new_selector else None
                                        if new_action.startswith("assert"):
                                            current_step.expected_value = new_val.strip() if new_val else None
                                            current_step.input_value = None
                                        else:
                                            current_step.input_value = new_val.strip() if new_val else None
                                            current_step.expected_value = None
                                        current_step.description = new_desc.strip() or f"Step {selected_step_num}"

                                        # Record Human Correction if user updated selector
                                        if old_selector and current_step.selector_value and old_selector != current_step.selector_value:
                                            try:
                                                save_correction(
                                                    target_pattern=current_step.description or current_step.selector_value,
                                                    bad_selector=old_selector,
                                                    recommended_selector=current_step.selector_value,
                                                    strategy=current_step.locator_strategy.value if current_step.locator_strategy else "css",
                                                    note=f"Corrected by user during manual review of {tc.id} Step {selected_step_num}",
                                                )
                                            except Exception:
                                                pass

                                        # Continuous Learning: save verified selector into catalog
                                        if current_step.selector_value:
                                            try:
                                                save_learned_selector(
                                                    element_label=current_step.description or current_step.selector_value,
                                                    selector=current_step.selector_value,
                                                    strategy=current_step.locator_strategy.value if current_step.locator_strategy else "css",
                                                    action=current_step.action.value,
                                                )
                                            except Exception:
                                                pass

                                        st.session_state.approval_record = None
                                        st.success(f"Step {selected_step_num} for {tc.id} saved.")
                                        st.rerun()

                                with act_col2:
                                    if st.button("Delete Selected Step", use_container_width=True, key=f"btn_del_{tc.id}_{selected_step_num}") and len(tc.steps) > 1:
                                        tc.steps = [s for s in tc.steps if s.step_number != selected_step_num]
                                        for idx, s in enumerate(tc.steps, start=1):
                                            s.step_number = idx
                                        st.session_state.approval_record = None
                                        st.warning(f"Step {selected_step_num} deleted from {tc.id}.")
                                        st.rerun()

                        with tab_add:
                            st.markdown(f"**Add Step {len(tc.steps) + 1} to [{tc.id}]**")
                            a_col1, a_col2 = st.columns([1, 1])
                            with a_col1:
                                add_action = st.selectbox(
                                    "Action Type:",
                                    options=[a.value for a in ActionType],
                                    index=1,
                                    key=f"add_act_{tc.id}",
                                )
                            with a_col2:
                                add_strategy = st.selectbox(
                                    "Locator Strategy:",
                                    options=["css", "text", "test_id", "role"],
                                    index=0,
                                    key=f"add_strat_{tc.id}",
                                    help="css: CSS selector (#id, .class); text: Visible element text; test_id: data-testid attribute; role: ARIA role",
                                )

                            b_col1, b_col2 = st.columns([1, 1])
                            with b_col1:
                                add_selector = st.text_input(
                                    "Target Selector / Text / Value:",
                                    value="",
                                    placeholder="e.g. #LOGIN_LINK or Sign Out or body",
                                    key=f"add_sel_{tc.id}",
                                    help="Target locator value",
                                )
                            with b_col2:
                                add_val = st.text_input(
                                    "Input / Expected Value:",
                                    value="",
                                    placeholder="Value to type, duration (e.g. 5s), or expected text",
                                    key=f"add_val_{tc.id}",
                                )

                            add_desc = st.text_input(
                                "Step Description:",
                                value="",
                                placeholder="e.g. Click user profile avatar or enter order quantity",
                                key=f"add_desc_{tc.id}",
                            )

                            if st.button("➕ Add Step to Scenario", type="primary", use_container_width=True, key=f"btn_confirm_add_{tc.id}"):
                                next_num = len(tc.steps) + 1
                                is_assert = add_action.startswith("assert")
                                new_step = TestStep(
                                    step_number=next_num,
                                    action=ActionType(add_action),
                                    locator_strategy=LocatorStrategy(add_strategy) if add_strategy else None,
                                    selector_value=add_selector.strip() if add_selector else None,
                                    input_value=add_val.strip() if not is_assert and add_val else None,
                                    expected_value=add_val.strip() if is_assert and add_val else None,
                                    description=add_desc.strip() or f"Step {next_num}: {add_action.upper()}",
                                )
                                # Continuous Learning: save new selector into knowledge catalog
                                if new_step.selector_value:
                                    try:
                                        save_learned_selector(
                                            element_label=new_step.description or new_step.selector_value,
                                            selector=new_step.selector_value,
                                            strategy=new_step.locator_strategy.value if new_step.locator_strategy else "css",
                                            action=new_step.action.value,
                                        )
                                    except Exception:
                                        pass

                                tc.steps.append(new_step)
                                st.session_state.approval_record = None
                                st.success(f"Step {next_num} added to {tc.id}!")
                                st.rerun()

                        with tab_flow:
                            st.markdown(f"**⚡ Insert Reusable Building Block Flow into [{tc.id}]**")
                            st.caption("Insert pre-verified enterprise flows without manually configuring locators.")
                            avail_flows = list_reusable_flows()
                            chosen_flow_name = st.selectbox(
                                "Choose Flow Template:",
                                options=list(avail_flows.keys()),
                                key=f"flow_choice_{tc.id}",
                            )
                            if chosen_flow_name:
                                flow_meta = avail_flows[chosen_flow_name]
                                st.info(f"**{flow_meta.get('description', '')}** — `{len(flow_meta.get('steps', []))} steps` (Category: `{flow_meta.get('category', 'General')}`)")

                                pos_choice = st.radio(
                                    "Insert Position:",
                                    options=["Append to End", "Insert at Beginning", "Insert after Step Number"],
                                    horizontal=True,
                                    key=f"flow_pos_radio_{tc.id}",
                                )
                                insert_at = len(tc.steps)
                                if pos_choice == "Insert at Beginning":
                                    insert_at = 0
                                elif pos_choice == "Insert after Step Number" and tc.steps:
                                    step_pick = st.selectbox(
                                        "After Step #:",
                                        options=[s.step_number for s in tc.steps],
                                        key=f"flow_after_step_{tc.id}",
                                    )
                                    insert_at = step_pick

                                if st.button(f"⚡ Insert '{chosen_flow_name}' ({len(flow_meta.get('steps', []))} steps)", type="primary", use_container_width=True, key=f"btn_insert_flow_{tc.id}"):
                                    flow_steps = get_reusable_flow_steps(chosen_flow_name)
                                    combined = tc.steps[:insert_at] + flow_steps + tc.steps[insert_at:]
                                    for i, s in enumerate(combined, start=1):
                                        s.step_number = i
                                    tc.steps = combined
                                    st.session_state.approval_record = None
                                    st.success(f"Inserted flow '{chosen_flow_name}'! Scenario now contains {len(tc.steps)} steps.")
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

            exec_col1, exec_col2 = st.columns([2, 1])
            with exec_col1:
                exec_mode_choice = st.radio(
                    "Browser Execution Mode:",
                    options=["Headed (Watch on Screen)", "Headless (Background)"],
                    index=0,
                    horizontal=True,
                    key="review_exec_view_mode",
                )
                is_headed_exec = "Headed" in exec_mode_choice
            with exec_col2:
                st.write("")
                run_btn = st.button("Run Approved Tests in Browser", type="primary", use_container_width=True)

            progress_bar = st.progress(0.0)
            status_text = st.empty()

            if run_btn and suite and approval:
                current_hash = suite.compute_hash()
                if current_hash != approval.suite_hash:
                    st.error("Security Alert: Cryptographic suite hash mismatch. Suite was modified after sign-off.")
                    st.stop()

                cases_to_run = [c for c in suite.test_cases if st.session_state.get(f"exec_chk_{c.id}", True)]
                if not cases_to_run:
                    st.error("No scenarios selected for execution. Please check at least one scenario checkbox above.")
                    st.stop()

                policy = PolicyEngine()
                for tc in cases_to_run:
                    for s in tc.steps:
                        if s.action == ActionType.NAVIGATE and s.input_value:
                            try:
                                policy.validate_navigation_url(s.input_value)
                            except Exception as err:
                                st.error(f"Security Alert: Navigation URL blocked by policy: {err}")
                                st.stop()

                st.session_state.action_logs = []
                total_steps = sum(len(tc.steps) for tc in cases_to_run)
                tracker = {"completed": 0}

                def step_stream_callback(test_case: TestCase, step: TestStep, step_res):
                    if step_res is None:
                        safe_desc = mask_step_credential_display(step.action.value, step.selector_value, step.input_value, step.description)[1]
                        status_text.markdown(f"**Executing:** `[{test_case.id}] Step {step.step_number}`: *{safe_desc}*")
                    else:
                        tracker["completed"] += 1
                        progress_bar.progress(min(tracker["completed"] / max(total_steps, 1), 1.0))
                        outcome_tag = "PASS" if step_res.passed else "FAIL"
                        if is_credential_step(step.selector_value, step.description, step.input_value):
                            target_disp = step.selector_value or "Credentials"
                        else:
                            target_disp = step.selector_value or (step.input_value if step.action == ActionType.NAVIGATE else "")
                        log_entry = (
                            f"[{outcome_tag}] `[{test_case.id}] Step {step.step_number}` **{step.action.value.upper()}** "
                            f"`{target_disp}` | {step_res.duration_ms}ms"
                        )
                        if not step_res.passed:
                            log_entry += f" — Error: {step_res.error_message}"
                        st.session_state.action_logs.append(log_entry)

                with st.spinner(f"Executing {len(cases_to_run)} selected test cases in browser automation..."):
                    # Auto-sanitize any legacy malformed selector strings in session state
                    for tc in cases_to_run:
                        for stp in tc.steps:
                            if stp.selector_value and ", text=" in stp.selector_value:
                                stp.selector_value = re.sub(r",\s*text=['\"][^'\"]*['\"]", "", stp.selector_value)
                            if stp.selector_value and "btnCreate" in stp.selector_value and "New Create" not in stp.selector_value:
                                stp.selector_value = "button:has-text('New Create'), button:has-text('Create'), [title*='Create'], #btnCreate"
                            if stp.selector_value and ("quantity" in stp.selector_value.lower() or (stp.description and "quantity" in stp.description.lower())):
                                if stp.action == ActionType.FILL and not stp.selector_value.startswith("input"):
                                    stp.selector_value = "input[id*='btadmini_table[1].quantity'], input[name*='btadmini_table[1].quantity'], input[data-help-id*='I_quantity:R_1'], input[id*='btadmini_table'][id*='quantity'], input[id*='quantity']:not([readonly]), input[aria-label*='Quantity' i]"
                                    stp.locator_strategy = LocatorStrategy.CSS
                            if stp.step_number == 35 and stp.action == ActionType.FILL and stp.input_value == "962":
                                stp.input_value = "${OPERATIONAL_DOCUMENT}"

                        # Guard: If Service Quotation flow has Create but missed ZQDS popup selection
                        has_create = any("Create" in (s.description or "") and s.action == ActionType.CLICK for s in tc.steps)
                        has_zqds = any("ZQDS" in (s.selector_value or "") for s in tc.steps)
                        if has_create and not has_zqds:
                            new_steps = []
                            for s in tc.steps:
                                new_steps.append(s)
                                if "Create" in (s.description or "") and s.action == ActionType.CLICK and not has_zqds:
                                    zqds_step = TestStep(
                                        step_number=len(new_steps) + 1,
                                        action=ActionType.CLICK,
                                        locator_strategy=LocatorStrategy.TEXT,
                                        selector_value="ZQDS",
                                        description="Select Transaction Type ZQDS — CE-Direct Sales from popup",
                                    )
                                    new_steps.append(zqds_step)
                                    has_zqds = True
                            for i, s in enumerate(new_steps, 1):
                                s.step_number = i
                            tc.steps = new_steps

                        # Guard: If RAR flow has legacy #shellBar-home navigation, upgrade to verified direct Manage Revenue Contracts flow
                        has_home = any("shellbar-home" in (s.selector_value or "").lower() for s in tc.steps)
                        if has_home:
                            logger.info("Auto-sanitizing legacy #shellBar-home steps in %s to direct Manage Revenue Contracts navigation", tc.id)
                            home_idx = next(i for i, s in enumerate(tc.steps) if "shellbar-home" in (s.selector_value or "").lower())
                            prefix_steps = tc.steps[:home_idx]
                            from app.storage.repository import load_regression_suite
                            kan25 = load_regression_suite("SUITE-KAN-25")
                            if kan25 and kan25.test_cases:
                                verified_downstream = [s for s in kan25.test_cases[0].steps if s.step_number >= 33]
                                tc.steps = prefix_steps + verified_downstream
                                for idx, stp in enumerate(tc.steps, 1):
                                    stp.step_number = idx

                    target_exec_url = settings.sap_fiori_url
                    cdp_ep = settings.cdp_endpoint_url or None

                    import importlib
                    import app.browser.locators
                    import app.browser.executor
                    importlib.reload(app.browser.locators)
                    importlib.reload(app.browser.executor)
                    from app.browser.executor import TestExecutor

                    executor = TestExecutor(
                        headless=not is_headed_exec,
                        slow_mo_ms=150 if is_headed_exec else 0,
                        cdp_url=cdp_ep,
                    )
                    run = executor.execute_suite(
                        suite=suite,
                        target_url=target_exec_url,
                        step_callback=step_stream_callback,
                        test_cases=cases_to_run,
                    )
                    st.session_state.execution_run = run

                progress_bar.progress(1.0)
                if run.passed_tests == run.total_tests and run.total_tests > 0:
                    status_text.success(f"Execution Complete: All {run.passed_tests}/{run.total_tests} Selected Tests Passed.")
                elif run.passed_tests == 0:
                    status_text.error(f"Execution Failed: 0/{run.total_tests} Tests Passed ({run.failed_tests} Failed).")
                else:
                    status_text.warning(f"Execution Completed with Failures: {run.passed_tests}/{run.total_tests} Tests Passed ({run.failed_tests} Failed).")

            if st.session_state.execution_run:
                run_post = st.session_state.execution_run
                st.write("")
                post_save_col1, post_save_col2 = st.columns([2.5, 1.5])
                with post_save_col1:
                    st.caption(f"Last Execution: `{run_post.passed_tests}/{run_post.total_tests}` Passed | Suite ID: `{suite.suite_id}`")
                with post_save_col2:
                    if st.button("💾 Save / Update in Regression Suite", type="secondary", use_container_width=True, key="btn_save_post_run"):
                        saved_path = save_regression_suite(
                            suite,
                            last_run_status=f"{run_post.passed_tests}/{run_post.total_tests} Passed"
                        )
                        st.success(f"Updated suite in Regression Repository: `{saved_path.name}`")

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
                    defect_title = matching_tc.title if matching_tc else res.test_case_id
                    defect_summary = f"[SAP Defect] {defect_title}: {raw_msg}"

                    repro_steps = []
                    if st.session_state.test_suite and matching_tc:
                        for s in matching_tc.steps:
                            safe_val, safe_desc = mask_step_credential_display(
                                s.action.value, s.selector_value, s.input_value, s.description
                            )
                            target_part = s.selector_value or safe_val or ""
                            repro_steps.append(f"{s.action.value.upper()} ({target_part}): {safe_desc}")

                    defect = DefectDraft(
                        draft_id=f"DRAFT-{res.test_case_id}",
                        parent_issue_key=target_issue_key or "",
                        test_case_id=res.test_case_id,
                        summary=defect_summary,
                        steps_to_reproduce=repro_steps,
                        expected_result=matching_tc.expected_result if matching_tc else "Action should complete successfully on SAP Fiori.",
                        actual_result=res.failure_message or "Step execution failed on SAP Fiori.",
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


# ==============================================================================
# TAB 4: Regression Suite Repository
# ==============================================================================
elif selected_nav == "4. Regression Repository":
    st.subheader("Regression Suite Repository")
    st.caption("Manage, customize, and execute verified test suites directly from persistent storage without calling Jira or LLMs.")

    # High-level Metrics Cards
    all_suites = list_regression_suites()

    m1, m2 = st.columns(2)
    m1.metric("Saved Regression Suites", len(all_suites))
    m2.metric("Total Scenarios in Repo", sum(s.get("total_cases", 0) for s in all_suites))

    st.markdown("---")

    # Search & Filter
    search_q = st.text_input("🔍 Search Suites (by Suite ID, Jira Key, or Name):", placeholder="e.g. KAN-11, SAP, Quotations, Authentication...")
    filtered_suites = [
        s for s in all_suites
        if search_q.lower() in s.get("suite_id", "").lower()
        or search_q.lower() in s.get("name", "").lower()
        or search_q.lower() in s.get("requirement_key", "").lower()
    ] if search_q else all_suites

    if not filtered_suites:
        st.info("No regression suites found matching your search. Ingest a requirement in Tab 1 or save an approved suite in Tab 2 to populate your repository.")
    else:
        for suite_meta in filtered_suites:
            s_id = suite_meta.get("suite_id")
            s_name = suite_meta.get("name")
            s_req = suite_meta.get("requirement_key")
            s_cases_cnt = suite_meta.get("total_cases")
            s_steps_cnt = suite_meta.get("total_steps")
            s_status = suite_meta.get("last_run_status")
            s_saved = suite_meta.get("last_saved_at")

            status_badge = f'<span class="badge-pass">{s_status}</span>' if "Pass" in s_status else f'<span class="badge-fail">{s_status}</span>'

            with st.expander(f"📦 **{s_id}** — {s_name} [{s_cases_cnt} Scenarios | {s_steps_cnt} Steps | Status: {s_status}]", expanded=False):
                loaded_s = load_regression_suite(s_id)
                if not loaded_s:
                    st.error("Failed to read suite file.")
                    continue

                act_col1, act_col2, act_col3 = st.columns([2.5, 1.3, 1.0])
                with act_col1:
                    st.markdown(f"**Jira Requirement:** `{s_req}` | **Version:** `{loaded_s.version}`")
                    st.caption(f"Last Saved: `{s_saved}` | File: `{suite_meta.get('file_path')}`")
                with act_col2:
                    if st.button("📂 Load into Review Center", key=f"btn_load_to_rev_{s_id}", use_container_width=True):
                        st.session_state.test_suite = loaded_s
                        st.session_state.approval_record = None
                        st.session_state.execution_run = None
                        navigate_to_tab("2. Review Center")
                        st.rerun()
                with act_col3:
                    if st.button("🗑️ Delete Suite", key=f"btn_del_reg_{s_id}", use_container_width=True):
                        delete_regression_suite(s_id)
                        st.success(f"Deleted suite {s_id}")
                        st.rerun()

                # Scenarios & Selective Execution Controls
                st.markdown("##### Scenarios in this Suite:")
                reg_groups = sorted(list(set(getattr(c, "group", None) or "General" for c in loaded_s.test_cases)))
                r_grp_col1, r_grp_col2, r_grp_col3 = st.columns([2.0, 1.2, 1.2])
                with r_grp_col1:
                    r_grp_sel = st.selectbox("Filter by Module Group:", ["All Groups"] + reg_groups, key=f"reg_filter_grp_{s_id}")
                with r_grp_col2:
                    if st.button("Select Group", key=f"btn_sel_reg_grp_{s_id}", use_container_width=True):
                        for c in loaded_s.test_cases:
                            c_g = getattr(c, "group", None) or "General"
                            if r_grp_sel == "All Groups" or c_g == r_grp_sel:
                                st.session_state[f"reg_chk_{s_id}_{c.id}"] = True
                        st.rerun()
                with r_grp_col3:
                    if st.button("Deselect Group", key=f"btn_desel_reg_grp_{s_id}", use_container_width=True):
                        for c in loaded_s.test_cases:
                            c_g = getattr(c, "group", None) or "General"
                            if r_grp_sel == "All Groups" or c_g == r_grp_sel:
                                st.session_state[f"reg_chk_{s_id}_{c.id}"] = False
                        st.rerun()

                reg_selected = []
                for idx, c in enumerate(loaded_s.test_cases):
                    c_grp = getattr(c, "group", None) or "General"
                    if r_grp_sel != "All Groups" and c_grp != r_grp_sel:
                        continue

                    tc_chk_col, tc_info_col = st.columns([0.4, 5.0])
                    with tc_chk_col:
                        chk_val = st.checkbox(
                            f"Select {c.id}",
                            value=st.session_state.get(f"reg_chk_{s_id}_{c.id}", True),
                            key=f"reg_chk_{s_id}_{c.id}",
                            label_visibility="collapsed",
                        )
                        if chk_val:
                            reg_selected.append(c)
                    with tc_info_col:
                        st.markdown(f"**[{c.id}]** <span style='background:#ede9fe; color:#5b21b6; border: 1px solid #ddd6fe; padding: 2px 6px; border-radius: 4px; font-size: 0.75rem; font-weight: 600;'>📁 {c_grp}</span> {c.title} — *{len(c.steps)} steps*", unsafe_allow_html=True)
                        st.caption(f"Objective: {c.objective}")

                # Execution Bar for Regression Suite
                st.markdown("---")
                exec_reg_col1, exec_reg_col2 = st.columns([2, 1])
                with exec_reg_col1:
                    reg_exec_mode = st.radio(
                        "Execution Mode:",
                        options=["Visual Headed (Watch on Screen)", "Background Headless"],
                        index=0,
                        horizontal=True,
                        key=f"reg_exec_mode_{s_id}",
                    )
                    is_headed_reg = "Headed" in reg_exec_mode
                with exec_reg_col2:
                    st.write("")
                    run_reg_btn = st.button(f"▶️ Run Selected ({len(reg_selected)}) Tests", type="primary", use_container_width=True, key=f"btn_run_reg_{s_id}")

                if run_reg_btn:
                    if not reg_selected:
                        st.error("Please select at least one scenario to execute.")
                    else:
                        reg_pbar = st.progress(0.0)
                        reg_status = st.empty()
                        reg_logs = []
                        total_reg_steps = sum(len(tc.steps) for tc in reg_selected)
                        reg_tracker = {"done": 0}

                        def reg_callback(tc, step, step_res):
                            if step_res is None:
                                safe_desc = mask_step_credential_display(step.action.value, step.selector_value, step.input_value, step.description)[1]
                                reg_status.markdown(f"**Executing:** `[{tc.id}] Step {step.step_number}`: *{safe_desc}*")
                            else:
                                reg_tracker["done"] += 1
                                reg_pbar.progress(min(reg_tracker["done"] / max(total_reg_steps, 1), 1.0))
                                outcome_tag = "PASS" if step_res.passed else "FAIL"
                                t_disp = step.selector_value or ("••••••••" if is_credential_step(step.selector_value, step.description, step.input_value) else "")
                                reg_logs.append(f"[{outcome_tag}] `[{tc.id}] Step {step.step_number}` **{step.action.value.upper()}** `{t_disp}` | {step_res.duration_ms}ms")

                        with st.spinner(f"Executing {len(reg_selected)} scenarios in Playwright..."):
                            for tc in reg_selected:
                                for stp in tc.steps:
                                    if stp.selector_value and ", text=" in stp.selector_value:
                                        stp.selector_value = re.sub(r",\s*text=['\"][^'\"]*['\"]", "", stp.selector_value)
                                    if stp.selector_value and "btnCreate" in stp.selector_value and "New Create" not in stp.selector_value:
                                        stp.selector_value = "button:has-text('New Create'), button:has-text('Create'), [title*='Create'], #btnCreate"

                                # Guard: If Service Quotation flow has Create but missed ZQDS popup selection
                                has_create = any("Create" in (s.description or "") and s.action == ActionType.CLICK for s in tc.steps)
                                has_zqds = any("ZQDS" in (s.selector_value or "") for s in tc.steps)
                                if has_create and not has_zqds:
                                    new_steps = []
                                    for s in tc.steps:
                                        new_steps.append(s)
                                        if "Create" in (s.description or "") and s.action == ActionType.CLICK and not has_zqds:
                                            zqds_step = TestStep(
                                                step_number=len(new_steps) + 1,
                                                action=ActionType.CLICK,
                                                locator_strategy=LocatorStrategy.TEXT,
                                                selector_value="ZQDS",
                                                description="Select Transaction Type ZQDS — CE-Direct Sales from popup",
                                            )
                                            new_steps.append(zqds_step)
                                            has_zqds = True
                                    for i, s in enumerate(new_steps, 1):
                                        s.step_number = i
                                    tc.steps = new_steps

                            import importlib
                            import app.browser.locators
                            import app.browser.executor
                            importlib.reload(app.browser.locators)
                            importlib.reload(app.browser.executor)
                            from app.browser.executor import TestExecutor

                            executor = TestExecutor(headless=not is_headed_reg, slow_mo_ms=800 if is_headed_reg else 0)
                            run_res = executor.execute_suite(
                                suite=loaded_s,
                                target_url=settings.sap_fiori_url,
                                step_callback=reg_callback,
                                test_cases=reg_selected,
                            )
                            # Update last run status on suite
                            save_regression_suite(
                                loaded_s,
                                last_run_status=f"{run_res.passed_tests}/{run_res.total_tests} Passed"
                            )
                            reg_pbar.progress(1.0)
                            if run_res.passed_tests == run_res.total_tests and run_res.total_tests > 0:
                                reg_status.success(f"Execution Complete: All {run_res.passed_tests}/{run_res.total_tests} Tests Passed!")
                            else:
                                reg_status.error(f"Execution Failed: {run_res.passed_tests}/{run_res.total_tests} Passed ({run_res.failed_tests} Failed).")

                        for l in reg_logs:
                            st.markdown(f'<div class="step-log-item">{l}</div>', unsafe_allow_html=True)

# ==============================================================================
# TAB 5: Admin & Continuous Learning Console
# ==============================================================================
elif selected_nav == "5. Admin":
    st.subheader("Admin & Continuous Learning Console")
    st.caption("Manage enterprise knowledge bases, reusable flow building blocks, self-healing selectors, and testing standards.")

    all_flows = list_reusable_flows()
    all_selectors = get_learned_selectors()
    all_golden = list_golden_examples()
    all_corrections = list_corrections()

    # Metrics Overview
    am1, am2, am3, am4 = st.columns(4)
    am1.metric("Learned Selectors", len(all_selectors))
    am2.metric("Reusable Flows", len(all_flows))
    am3.metric("Golden Exemplars", len(all_golden))
    am4.metric("Rule Corrections", len(all_corrections))

    st.markdown("---")

    admin_tabs = st.tabs([
        "🧠 Learned Selectors",
        "⚡ Reusable Flows",
        "🌟 Golden Exemplars",
        "💡 Testing Standards & Rules",
        "⚙️ System Environment & Diagnostics",
    ])

    with admin_tabs[0]:
        st.markdown("### 🧠 Learned Selector Catalog")
        st.caption("Self-healing selectors verified from successful runs in `data/knowledge/element_catalog.json`.")
        cat_table = []
        for el in all_selectors:
            cat_table.append({
                "Element Label": el.get("element_label"),
                "Selector": el.get("selector"),
                "Strategy": el.get("strategy"),
                "Action": el.get("action"),
                "Passes": el.get("pass_count", 1),
            })
        if cat_table:
            st.dataframe(cat_table, use_container_width=True)
        else:
            st.info("No learned selectors recorded yet.")

    with admin_tabs[1]:
        st.markdown("### ⚡ Reusable Flow Library")
        st.caption("Pre-configured enterprise building blocks stored in `data/library/flows.json`.")
        if not all_flows:
            st.info("No reusable flows registered yet.")
        else:
            for flow_name, flow_info in all_flows.items():
                with st.expander(f"🔹 {flow_name} ({len(flow_info.get('steps', []))} steps)"):
                    st.markdown(f"**Category:** `{flow_info.get('category', 'General')}`")
                    st.write(flow_info.get("description", ""))
                    flow_step_data = []
                    for s in flow_info.get("steps", []):
                        flow_step_data.append({
                            "Step #": s.get("step_number"),
                            "Action": s.get("action", "").upper(),
                            "Target": s.get("selector_value") or "—",
                            "Input/Expected": s.get("input_value") or s.get("expected_value") or "—",
                            "Description": s.get("description", ""),
                        })
                    st.dataframe(flow_step_data, use_container_width=True)

    with admin_tabs[2]:
        st.markdown("### 🌟 Golden Test Case Exemplars")
        st.caption("Human-verified few-shot patterns injected into LLM prompts (`data/knowledge/golden_examples.json`).")
        if not all_golden:
            st.info("No golden examples saved yet.")
        else:
            for g in all_golden:
                with st.expander(f"⭐ {g.get('pattern', 'Exemplar')} ({g.get('example_id')})"):
                    st.write(g.get("description", ""))
                    tc_data = g.get("test_case", {})
                    st.markdown(f"**Title:** {tc_data.get('title')}")
                    st.caption(f"Objective: {tc_data.get('objective')}")
                    g_steps = []
                    for s in tc_data.get("steps", []):
                        g_steps.append({
                            "Step #": s.get("step_number"),
                            "Action": s.get("action", "").upper(),
                            "Target": s.get("selector_value") or "—",
                            "Input/Expected": s.get("input_value") or s.get("expected_value") or "—",
                            "Description": s.get("description", ""),
                        })
                    st.dataframe(g_steps, use_container_width=True)

    with admin_tabs[3]:
        st.markdown("### 💡 Human Corrections & Testing Standards")
        st.caption("Preferences memory and standards guide (`testing_standards.md` & `corrections.json`).")
        t_corr, t_std = st.tabs(["Corrections Memory", "Testing Standards Guide"])
        with t_corr:
            if not all_corrections:
                st.info("No manual corrections recorded yet.")
            else:
                corr_rows = []
                for c in all_corrections:
                    corr_rows.append({
                        "Target Pattern": c.get("target_pattern"),
                        "Avoid Selector": c.get("bad_selector"),
                        "Recommended Selector": c.get("recommended_selector"),
                        "Strategy": c.get("strategy"),
                        "Rationale / Note": c.get("note"),
                    })
                st.dataframe(corr_rows, use_container_width=True)
        with t_std:
            st.markdown(get_testing_standards())

    with admin_tabs[4]:
        st.markdown("### ⚙️ System Environment & Diagnostics")
        env_col1, env_col2 = st.columns(2)
        with env_col1:
            st.markdown("#### SAP Target Application")
            st.info(
                f"**Host:** `{settings.sap_host_domain}`\n\n"
                f"**Client:** `{settings.sap_client}` | **Language:** `{settings.sap_language}`\n\n"
                f"**Username:** `{settings.sap_username or 'MYRAR1'}`\n\n"
                f"**URL:** `{settings.sap_fiori_url}`"
            )
        with env_col2:
            st.markdown("#### Jira Cloud Connection")
            st.info(
                f"**Base URL:** `{settings.jira_base_url}`\n\n"
                f"**User Email:** `{settings.jira_user_email}`\n\n"
                f"**Status:** `{'Connected' if jira_client.is_connected() else 'Disconnected'}`"
            )
