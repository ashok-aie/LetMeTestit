"""
Storage & Knowledge Repository for Agentic Quality Engineering.
Provides persistence for:
1. Regression Test Suites (data/cases/)
2. Reusable Step Flows (data/library/flows.json)
3. Learned Selector Catalog / Self-Healing Memory (data/knowledge/element_catalog.json)
4. Execution Run Records (data/runs/)
"""
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict, Any, Optional

from app.models.test_suite import TestSuite, TestCase, TestStep, ActionType, LocatorStrategy, TestCategory
from app.models.execution import ExecutionRun

logger = logging.getLogger(__name__)

# Base storage directories
BASE_DATA_DIR = Path("data").resolve()
CASES_DIR = BASE_DATA_DIR / "cases"
LIBRARY_DIR = BASE_DATA_DIR / "library"
KNOWLEDGE_DIR = BASE_DATA_DIR / "knowledge"
RUNS_DIR = BASE_DATA_DIR / "runs"

FLOWS_FILE = LIBRARY_DIR / "flows.json"
CATALOG_FILE = KNOWLEDGE_DIR / "element_catalog.json"
STANDARDS_FILE = KNOWLEDGE_DIR / "testing_standards.md"
GOLDEN_FILE = KNOWLEDGE_DIR / "golden_examples.json"
CORRECTIONS_FILE = KNOWLEDGE_DIR / "corrections.json"


def _ensure_dirs():
    CASES_DIR.mkdir(parents=True, exist_ok=True)
    LIBRARY_DIR.mkdir(parents=True, exist_ok=True)
    KNOWLEDGE_DIR.mkdir(parents=True, exist_ok=True)
    RUNS_DIR.mkdir(parents=True, exist_ok=True)


# ==============================================================================
# 1. REGRESSION TEST SUITE PERSISTENCE
# ==============================================================================

def save_regression_suite(
    suite: TestSuite,
    suite_name: Optional[str] = None,
    description: Optional[str] = None,
    tags: Optional[List[str]] = None,
    last_run_status: Optional[str] = None,
) -> Path:
    """
    Saves or updates a TestSuite into the data/cases/ repository with metadata.
    """
    _ensure_dirs()
    clean_id = suite.suite_id.strip()
    target_file = CASES_DIR / f"{clean_id}.json"

    meta = {
        "suite_id": clean_id,
        "name": suite_name or clean_id,
        "description": description or f"Regression Suite for {suite.requirement_key}",
        "requirement_key": suite.requirement_key,
        "version": suite.version,
        "tags": tags or ["regression", "sap"],
        "total_cases": len(suite.test_cases),
        "total_steps": sum(len(tc.steps) for tc in suite.test_cases),
        "last_saved_at": datetime.now(timezone.utc).isoformat(),
        "last_run_status": last_run_status or "Not Executed",
        "suite_data": suite.model_dump(mode="json"),
    }

    target_file.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info(f"Saved regression suite {clean_id} to {target_file}")
    return target_file


def list_regression_suites() -> List[Dict[str, Any]]:
    """
    Returns metadata list of all saved regression suites sorted by last saved date.
    """
    _ensure_dirs()
    suites = []
    for f in CASES_DIR.glob("*.json"):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            suites.append({
                "suite_id": data.get("suite_id", f.stem),
                "name": data.get("name", f.stem),
                "description": data.get("description", ""),
                "requirement_key": data.get("requirement_key", "UNKNOWN"),
                "total_cases": data.get("total_cases", 0),
                "total_steps": data.get("total_steps", 0),
                "last_saved_at": data.get("last_saved_at", ""),
                "last_run_status": data.get("last_run_status", "Not Executed"),
                "tags": data.get("tags", []),
                "file_path": str(f),
            })
        except Exception as e:
            logger.warning(f"Error reading suite file {f}: {e}")

    suites.sort(key=lambda s: s.get("last_saved_at", ""), reverse=True)
    return suites


def load_regression_suite(suite_id: str) -> Optional[TestSuite]:
    """
    Loads a validated TestSuite model from data/cases/<suite_id>.json.
    """
    _ensure_dirs()
    target_file = CASES_DIR / f"{suite_id}.json"
    if not target_file.exists():
        # Fallback check without case sensitivity or with suffix
        candidates = list(CASES_DIR.glob(f"*{suite_id}*.json"))
        if candidates:
            target_file = candidates[0]
        else:
            return None

    try:
        data = json.loads(target_file.read_text(encoding="utf-8"))
        suite_dict = data.get("suite_data", data)
        return TestSuite.model_validate(suite_dict)
    except Exception as e:
        logger.error(f"Failed to load suite {suite_id}: {e}")
        return None


def delete_regression_suite(suite_id: str) -> bool:
    """Deletes a saved regression suite."""
    _ensure_dirs()
    target_file = CASES_DIR / f"{suite_id}.json"
    if target_file.exists():
        target_file.unlink()
        return True
    return False


def get_cached_suite_for_requirement(req_key: str) -> Optional[TestSuite]:
    """
    Finds if a saved regression suite already exists for a Jira issue key (e.g. KAN-11).
    """
    _ensure_dirs()
    clean_req = req_key.strip().upper()
    for f in CASES_DIR.glob("*.json"):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            if data.get("requirement_key", "").strip().upper() == clean_req:
                suite_dict = data.get("suite_data", data)
                return TestSuite.model_validate(suite_dict)
        except Exception:
            continue
    return None


# ==============================================================================
# 2. REUSABLE FLOW LIBRARY PERSISTENCE
# ==============================================================================

_DEFAULT_FLOWS: Dict[str, Dict[str, Any]] = {
    "SAP Standard Logon": {
        "description": "Navigates to SAP S/4HANA Fiori URL, inputs username & password, and clicks Log On.",
        "category": "Authentication",
        "steps": [
            {
                "step_number": 1,
                "action": "navigate",
                "locator_strategy": None,
                "selector_value": None,
                "role_name": None,
                "input_value": None,
                "expected_value": None,
                "description": "Navigate to SAP Fiori Launchpad login URL",
            },
            {
                "step_number": 2,
                "action": "fill",
                "locator_strategy": "css",
                "selector_value": "#USERNAME_FIELD-inner",
                "role_name": None,
                "input_value": "MYRAR1",
                "expected_value": None,
                "description": "Enter SAP user credentials into username field",
            },
            {
                "step_number": 3,
                "action": "fill",
                "locator_strategy": "css",
                "selector_value": "#PASSWORD_FIELD-inner",
                "role_name": None,
                "input_value": "Welcome@123",
                "expected_value": None,
                "description": "Enter SAP password securely",
            },
            {
                "step_number": 4,
                "action": "click",
                "locator_strategy": "css",
                "selector_value": "#LOGIN_LINK",
                "role_name": None,
                "input_value": None,
                "expected_value": None,
                "description": "Click Log On button to establish session",
            },
            {
                "step_number": 5,
                "action": "assert_text",
                "locator_strategy": "css",
                "selector_value": "body",
                "role_name": None,
                "input_value": None,
                "expected_value": "Home",
                "description": "Assert successful logon by verifying Launchpad dashboard presence",
            },
        ],
    },
    "SAP Standard Logout": {
        "description": "Opens user profile action menu (#meAreaHeaderButton), clicks Sign Out, and confirms sign out dialog.",
        "category": "Authentication",
        "steps": [
            {
                "step_number": 1,
                "action": "click",
                "locator_strategy": "css",
                "selector_value": "#userActionsMenuHeaderButton, #meAreaHeaderButton",
                "role_name": None,
                "input_value": None,
                "expected_value": None,
                "description": "Click user profile action menu in SAP Launchpad header",
            },
            {
                "step_number": 2,
                "action": "click",
                "locator_strategy": "css",
                "selector_value": "button:has-text('Sign Out'), #logoutBtn",
                "role_name": None,
                "input_value": None,
                "expected_value": None,
                "description": "Click Sign Out button in user action sheet",
            },
            {
                "step_number": 3,
                "action": "click",
                "locator_strategy": "css",
                "selector_value": "button:has-text('OK'), button:has-text('Sign Out'), #logoutConfirm",
                "role_name": None,
                "input_value": None,
                "expected_value": None,
                "description": "Confirm sign-out modal dialog",
            },
            {
                "step_number": 4,
                "action": "assert_text",
                "locator_strategy": "css",
                "selector_value": "body",
                "role_name": None,
                "input_value": None,
                "expected_value": "signed out",
                "description": "Assert SAP logout confirmation screen",
            },
        ],
    },
    "Open Fiori Tile: Manage Service Quotations": {
        "description": "Navigates to the Manage Service Quotations tile and waits for the application worklist to load.",
        "category": "Navigation",
        "steps": [
            {
                "step_number": 1,
                "action": "click",
                "locator_strategy": "text",
                "selector_value": "Manage Service Quotations",
                "role_name": None,
                "input_value": None,
                "expected_value": None,
                "description": "Click on Manage Service Quotations tile on Fiori Launchpad",
            },
            {
                "step_number": 2,
                "action": "wait_for",
                "locator_strategy": "css",
                "selector_value": "body",
                "role_name": None,
                "input_value": "20s",
                "expected_value": None,
                "description": "Wait for 20 seconds on Service Quotations worklist page",
            },
        ],
    },
    "Wait 20 Seconds Pause": {
        "description": "Inserts an intentional 20-second pause to let asynchronous UI5 services or backend transactions complete.",
        "category": "Utility",
        "steps": [
            {
                "step_number": 1,
                "action": "wait_for",
                "locator_strategy": "css",
                "selector_value": "body",
                "role_name": None,
                "input_value": "20s",
                "expected_value": None,
                "description": "Pause execution for 20 seconds",
            }
        ],
    },
}


def _load_flows_raw() -> Dict[str, Dict[str, Any]]:
    _ensure_dirs()
    if not FLOWS_FILE.exists():
        FLOWS_FILE.write_text(json.dumps(_DEFAULT_FLOWS, indent=2, ensure_ascii=False), encoding="utf-8")
        return _DEFAULT_FLOWS
    try:
        return json.loads(FLOWS_FILE.read_text(encoding="utf-8"))
    except Exception as e:
        logger.warning(f"Error reading {FLOWS_FILE}: {e}")
        return _DEFAULT_FLOWS


def list_reusable_flows() -> Dict[str, Dict[str, Any]]:
    """Returns all available reusable flows."""
    return _load_flows_raw()


def get_reusable_flow_steps(flow_name: str, starting_step_number: int = 1) -> List[TestStep]:
    """
    Returns instantiated TestStep objects for a given flow name, renumbered sequentially.
    """
    flows = _load_flows_raw()
    flow_data = flows.get(flow_name)
    if not flow_data:
        return []

    raw_steps = flow_data.get("steps", [])
    steps = []
    for idx, s in enumerate(raw_steps):
        s_copy = dict(s)
        s_copy["step_number"] = starting_step_number + idx
        steps.append(TestStep.model_validate(s_copy))
    return steps


def save_reusable_flow(
    flow_name: str,
    description: str,
    category: str,
    steps: List[TestStep],
) -> None:
    """Saves a custom sequence of steps as a named reusable flow."""
    _ensure_dirs()
    flows = _load_flows_raw()
    flows[flow_name] = {
        "description": description,
        "category": category,
        "steps": [s.model_dump(mode="json") for s in steps],
    }
    FLOWS_FILE.write_text(json.dumps(flows, indent=2, ensure_ascii=False), encoding="utf-8")


# ==============================================================================
# 3. LEARNED SELECTOR CATALOG / SELF-HEALING KNOWLEDGE
# ==============================================================================

_DEFAULT_CATALOG: List[Dict[str, Any]] = [
    {
        "element_label": "SAP Username Input",
        "selector": "#USERNAME_FIELD-inner",
        "strategy": "css",
        "action": "fill",
        "pass_count": 10,
        "app_domain": "SAP S/4HANA",
        "notes": "Standard SAP S/4HANA WebGUI/Fiori logon input",
    },
    {
        "element_label": "SAP Password Input",
        "selector": "#PASSWORD_FIELD-inner",
        "strategy": "css",
        "action": "fill",
        "pass_count": 10,
        "app_domain": "SAP S/4HANA",
        "notes": "Standard SAP S/4HANA logon password field",
    },
    {
        "element_label": "SAP Log On Button",
        "selector": "#LOGIN_LINK",
        "strategy": "css",
        "action": "click",
        "pass_count": 10,
        "app_domain": "SAP S/4HANA",
        "notes": "Standard SAP S/4HANA logon submit button",
    },
    {
        "element_label": "Manage Service Quotations Tile",
        "selector": "Manage Service Quotations",
        "strategy": "text",
        "action": "click",
        "pass_count": 5,
        "app_domain": "SAP S/4HANA",
        "notes": "Fiori Launchpad tile with UI5 soft-hyphen fallback",
    },
    {
        "element_label": "User Profile / Me Area Header Button",
        "selector": "#userActionsMenuHeaderButton, #meAreaHeaderButton",
        "strategy": "css",
        "action": "click",
        "pass_count": 5,
        "app_domain": "SAP S/4HANA",
        "notes": "Top-right avatar/profile action menu button",
    },
    {
        "element_label": "SAP Sign Out Button",
        "selector": "button:has-text('Sign Out'), #logoutBtn",
        "strategy": "css",
        "action": "click",
        "pass_count": 5,
        "app_domain": "SAP S/4HANA",
        "notes": "Sign out item in user action popup",
    },
    {
        "element_label": "SAP Sign Out Confirm Dialog Button",
        "selector": "button:has-text('OK'), button:has-text('Sign Out'), #logoutConfirm",
        "strategy": "css",
        "action": "click",
        "pass_count": 5,
        "app_domain": "SAP S/4HANA",
        "notes": "Confirmation dialog button when logging out",
    },
]


def _load_catalog_raw() -> List[Dict[str, Any]]:
    _ensure_dirs()
    if not CATALOG_FILE.exists():
        CATALOG_FILE.write_text(json.dumps(_DEFAULT_CATALOG, indent=2, ensure_ascii=False), encoding="utf-8")
        return _DEFAULT_CATALOG
    try:
        return json.loads(CATALOG_FILE.read_text(encoding="utf-8"))
    except Exception as e:
        logger.warning(f"Error reading {CATALOG_FILE}: {e}")
        return _DEFAULT_CATALOG


def get_learned_selectors() -> List[Dict[str, Any]]:
    """Returns list of all learned verified selectors."""
    return _load_catalog_raw()


def save_learned_selector(
    element_label: str,
    selector: str,
    strategy: str = "css",
    action: Optional[str] = None,
    role_type: Optional[str] = None,
    app_domain: str = "SAP S/4HANA",
    notes: Optional[str] = None,
) -> None:
    """
    Saves or increments pass count for a verified working selector.
    Continuous learning from every successful execution and user edit.
    """
    if not selector or not selector.strip():
        return

    _ensure_dirs()
    catalog = _load_catalog_raw()
    clean_sel = selector.strip()
    clean_lbl = element_label.strip() if element_label else clean_sel

    found = False
    for entry in catalog:
        if entry.get("selector") == clean_sel or (entry.get("element_label", "").lower() == clean_lbl.lower() and entry.get("strategy") == strategy):
            entry["pass_count"] = entry.get("pass_count", 1) + 1
            entry["last_verified"] = datetime.now(timezone.utc).isoformat()
            if action:
                entry["action"] = action
            if notes:
                entry["notes"] = notes
            found = True
            break

    if not found:
        catalog.append({
            "element_label": clean_lbl,
            "selector": clean_sel,
            "strategy": strategy,
            "action": action or "click",
            "role_type": role_type,
            "pass_count": 1,
            "app_domain": app_domain,
            "last_verified": datetime.now(timezone.utc).isoformat(),
            "notes": notes or "Learned from execution",
        })

    CATALOG_FILE.write_text(json.dumps(catalog, indent=2, ensure_ascii=False), encoding="utf-8")


def get_learned_selectors_prompt_context() -> str:
    """
    Formats the learned catalog into a concise prompt block for the LLM test designer.
    """
    catalog = _load_catalog_raw()
    if not catalog:
        return ""

    lines = ["VERIFIED WORKING SELECTORS (CONTINUOUS LEARNING MEMORY):"]
    for entry in catalog[:15]:
        lbl = entry.get("element_label", "")
        sel = entry.get("selector", "")
        strat = entry.get("strategy", "css")
        act = entry.get("action", "")
        lines.append(f'- Label: "{lbl}" -> selector_value="{sel}", strategy="{strat}", action="{act}"')

    return "\n".join(lines)


# ==============================================================================
# 4. EXECUTION RUN LOGGING & HISTORY
# ==============================================================================

def save_execution_run_record(run: ExecutionRun) -> Path:
    """
    Saves an execution run summary to data/runs/ for audit and regression trends.
    """
    _ensure_dirs()
    run_file = RUNS_DIR / f"{run.run_id}.json"
    run_file.write_text(run.model_dump_json(indent=2), encoding="utf-8")
    return run_file


def list_execution_runs(suite_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """Returns summaries of past execution runs."""
    _ensure_dirs()
    runs = []
    for f in RUNS_DIR.glob("*.json"):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            if suite_id and data.get("suite_id") != suite_id:
                continue
            runs.append({
                "run_id": data.get("run_id", f.stem),
                "suite_id": data.get("suite_id", ""),
                "total_tests": data.get("total_tests", 0),
                "passed_tests": data.get("passed_tests", 0),
                "failed_tests": data.get("failed_tests", 0),
                "started_at": data.get("started_at", ""),
                "finished_at": data.get("finished_at", ""),
            })
        except Exception:
            continue
    runs.sort(key=lambda r: r.get("started_at", ""), reverse=True)
    return runs


# ==============================================================================
# 5. ENTERPRISE KNOWLEDGE BASE & CONTINUOUS LEARNING
# ==============================================================================

def get_testing_standards() -> str:
    """Reads enterprise testing methodology and standards from data/knowledge/testing_standards.md."""
    _ensure_dirs()
    if STANDARDS_FILE.exists():
        try:
            return STANDARDS_FILE.read_text(encoding="utf-8")
        except Exception:
            pass
    return "Follow Arrange-Act-Assert methodology, validate boundary conditions, and use resilient semantic locators."


def list_golden_examples() -> List[Dict[str, Any]]:
    """Lists high-quality exemplar test cases from data/knowledge/golden_examples.json."""
    _ensure_dirs()
    if not GOLDEN_FILE.exists():
        return []
    try:
        return json.loads(GOLDEN_FILE.read_text(encoding="utf-8"))
    except Exception:
        return []


def save_golden_example(
    pattern: str,
    description: str,
    test_case: TestCase,
    example_id: Optional[str] = None,
) -> None:
    """Saves a verified test case as an exemplar into the golden examples knowledge base."""
    _ensure_dirs()
    examples = list_golden_examples()
    eid = example_id or f"GOLDEN-{pattern.replace(' ', '-').upper()}-{len(examples)+1:02d}"
    examples.append({
        "example_id": eid,
        "pattern": pattern,
        "description": description,
        "test_case": test_case.model_dump(mode="json"),
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    GOLDEN_FILE.write_text(json.dumps(examples, indent=2, ensure_ascii=False), encoding="utf-8")


def get_golden_examples_prompt_context(limit: int = 2) -> str:
    """Formats golden examples into few-shot demonstration context for LLM test design."""
    examples = list_golden_examples()
    if not examples:
        return ""

    lines = ["EXEMPLAR ENTERPRISE TEST CASES (FOLLOW THIS STRUCTURE AND FIDELITY):"]
    for ex in examples[:limit]:
        pattern = ex.get("pattern", "Standard Flow")
        desc = ex.get("description", "")
        tc = ex.get("test_case", {})
        steps_summary = []
        for s in tc.get("steps", []):
            strat = s.get("locator_strategy") or "—"
            sel = s.get("selector_value") or "—"
            act = s.get("action", "")
            steps_summary.append(f"  Step {s.get('step_number')}: {act.upper()} {sel} ({strat}) -> {s.get('description')}")
        lines.append(f"\nPattern: {pattern} ({desc})\n" + "\n".join(steps_summary))

    return "\n".join(lines)


def list_corrections() -> List[Dict[str, Any]]:
    """Lists human corrections and preferences from data/knowledge/corrections.json."""
    _ensure_dirs()
    if not CORRECTIONS_FILE.exists():
        return []
    try:
        return json.loads(CORRECTIONS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return []


def save_correction(
    target_pattern: str,
    bad_selector: str,
    recommended_selector: str,
    strategy: str = "css",
    note: str = "",
) -> None:
    """Records a human correction or preference so the LLM does not repeat past mistakes."""
    _ensure_dirs()
    corrections = list_corrections()
    clean_rec = recommended_selector.strip()
    clean_bad = bad_selector.strip()

    # Avoid duplicate correction entries
    for c in corrections:
        if c.get("recommended_selector") == clean_rec and c.get("target_pattern") == target_pattern:
            c["note"] = note or c.get("note", "")
            CORRECTIONS_FILE.write_text(json.dumps(corrections, indent=2, ensure_ascii=False), encoding="utf-8")
            return

    corrections.append({
        "target_pattern": target_pattern,
        "bad_selector": clean_bad,
        "recommended_selector": clean_rec,
        "strategy": strategy,
        "note": note,
        "recorded_at": datetime.now(timezone.utc).isoformat(),
    })
    CORRECTIONS_FILE.write_text(json.dumps(corrections, indent=2, ensure_ascii=False), encoding="utf-8")


def get_corrections_prompt_context() -> str:
    """Formats human corrections memory into a guidance block for the LLM."""
    corrections = list_corrections()
    if not corrections:
        return ""

    lines = ["HUMAN CORRECTIONS & PREFERENCES MEMORY (AVOID PAST PITFALLS):"]
    for c in corrections[:10]:
        pat = c.get("target_pattern", "")
        rec = c.get("recommended_selector", "")
        bad = c.get("bad_selector", "")
        note = c.get("note", "")
        lines.append(f'- For "{pat}": DO NOT USE `{bad}`. INSTEAD USE `{rec}` ({c.get("strategy", "css")}). Rationale: {note}')

    return "\n".join(lines)


def get_full_knowledge_base_context() -> str:
    """Assembles all continuous learning signals (selectors, corrections, exemplars) for prompt injection."""
    parts = []
    sel_ctx = get_learned_selectors_prompt_context()
    if sel_ctx:
        parts.append(sel_ctx)

    corr_ctx = get_corrections_prompt_context()
    if corr_ctx:
        parts.append(corr_ctx)

    gold_ctx = get_golden_examples_prompt_context(limit=2)
    if gold_ctx:
        parts.append(gold_ctx)

    return "\n\n".join(parts)

