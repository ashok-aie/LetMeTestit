"""
Playwright Interactive Session Recorder & Codegen Parser
Allows QA engineers to record real-time browser interactions using Playwright Codegen
and converts the resulting Python script into declarative TestStep and TestCase models.
"""
import os
import re
import sys
import subprocess
import logging
from pathlib import Path
from typing import List, Optional

from app.models.test_suite import (
    TestCase,
    TestStep,
    ActionType,
    LocatorStrategy,
    TestCategory,
)

logger = logging.getLogger(__name__)


def record_playwright_session(
    target_url: str = "http://127.0.0.1:8000/",
    output_file: Optional[Path] = None,
    timeout_seconds: int = 300,
) -> str:
    """
    Launches Playwright Codegen in an interactive browser window on the user desktop.
    Blocks until the user closes the browser inspector, then returns generated Python script.
    """
    if output_file is None:
        rec_dir = Path("app/browser/test_scripts").resolve()
        rec_dir.mkdir(parents=True, exist_ok=True)
        output_file = rec_dir / "recorded_test.py"

    output_file.parent.mkdir(parents=True, exist_ok=True)
    if output_file.exists():
        output_file.unlink()

    import shutil
    npx_bin = shutil.which("npx")
    if npx_bin:
        cmd = [
            npx_bin,
            "playwright",
            "codegen",
            target_url,
            "--target",
            "python",
            "-o",
            str(output_file),
            "--test-id-attribute",
            "data-testid",
        ]
    else:
        cmd = [
            sys.executable,
            "-m",
            "playwright",
            "codegen",
            target_url,
            "--target",
            "python",
            "-o",
            str(output_file),
            "--test-id-attribute",
            "data-testid",
        ]

    logger.info("Launching Playwright Codegen: %s", " ".join(cmd))
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
        if proc.returncode != 0 and proc.stderr:
            logger.warning("Playwright codegen returned code %d: %s", proc.returncode, proc.stderr)
    except subprocess.TimeoutExpired:
        logger.warning("Playwright codegen timed out after %ds", timeout_seconds)

    if output_file.exists():
        return output_file.read_text(encoding="utf-8")
    return ""


def parse_recorded_script(
    script_content: str,
    default_url: str = "http://127.0.0.1:8000/",
) -> List[TestStep]:
    """
    Parses Python Playwright codegen script into structured TestStep models.
    Removes redundant pre-fill clicks and normalizes step numbering.
    """
    raw_steps: List[dict] = []
    lines = script_content.splitlines()

    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        # 1. page.goto("url")
        m_goto = re.search(r'page\.goto\(["\']([^"\']+)["\']\)', stripped)
        if m_goto:
            url = m_goto.group(1)
            raw_steps.append({
                "action": ActionType.NAVIGATE,
                "input_value": url,
                "description": f"Navigate to {url}",
            })
            continue

        # 2. page.get_by_test_id("testid").fill("value")
        m_tid_fill = re.search(r'page\.get_by_test_id\(["\']([^"\']+)["\']\)\.fill\(["\']([^"\']*)["\']\)', stripped)
        if m_tid_fill:
            sel, val = m_tid_fill.group(1), m_tid_fill.group(2)
            raw_steps.append({
                "action": ActionType.FILL,
                "locator_strategy": LocatorStrategy.TEST_ID,
                "selector_value": sel,
                "input_value": val,
                "description": f"Enter '{val}' into {sel}",
            })
            continue

        # 3. page.get_by_test_id("testid").select_option("value")
        m_tid_sel = re.search(r'page\.get_by_test_id\(["\']([^"\']+)["\']\)\.select_option\(["\']([^"\']*)["\']\)', stripped)
        if m_tid_sel:
            sel, val = m_tid_sel.group(1), m_tid_sel.group(2)
            raw_steps.append({
                "action": ActionType.SELECT_OPTION,
                "locator_strategy": LocatorStrategy.TEST_ID,
                "selector_value": sel,
                "input_value": val,
                "description": f"Select '{val}' in {sel}",
            })
            continue

        # 4. page.get_by_test_id("testid").click()
        m_tid_click = re.search(r'page\.get_by_test_id\(["\']([^"\']+)["\']\)\.click\(\)', stripped)
        if m_tid_click:
            sel = m_tid_click.group(1)
            raw_steps.append({
                "action": ActionType.CLICK,
                "locator_strategy": LocatorStrategy.TEST_ID,
                "selector_value": sel,
                "description": f"Click {sel}",
            })
            continue

        # 5. page.locator("selector").fill("value")
        m_loc_fill = re.search(r'page\.locator\(["\']([^"\']+)["\']\)\.fill\(["\']([^"\']*)["\']\)', stripped)
        if m_loc_fill:
            sel, val = m_loc_fill.group(1), m_loc_fill.group(2)
            raw_steps.append({
                "action": ActionType.FILL,
                "locator_strategy": LocatorStrategy.CSS,
                "selector_value": sel,
                "input_value": val,
                "description": f"Enter '{val}' into {sel}",
            })
            continue

        # 6. page.locator("selector").select_option("value")
        m_loc_sel = re.search(r'page\.locator\(["\']([^"\']+)["\']\)\.select_option\(["\']([^"\']*)["\']\)', stripped)
        if m_loc_sel:
            sel, val = m_loc_sel.group(1), m_loc_sel.group(2)
            raw_steps.append({
                "action": ActionType.SELECT_OPTION,
                "locator_strategy": LocatorStrategy.CSS,
                "selector_value": sel,
                "input_value": val,
                "description": f"Select '{val}' in {sel}",
            })
            continue

        # 7. page.locator("selector").click()
        m_loc_click = re.search(r'page\.locator\(["\']([^"\']+)["\']\)\.click\(\)', stripped)
        if m_loc_click:
            sel = m_loc_click.group(1)
            raw_steps.append({
                "action": ActionType.CLICK,
                "locator_strategy": LocatorStrategy.CSS,
                "selector_value": sel,
                "description": f"Click {sel}",
            })
            continue

        # 8. page.get_by_role("role", name="name").click()
        m_role_click = re.search(r'page\.get_by_role\(["\']([^"\']+)["\'](?:,\s*name=["\']([^"\']+)["\'])?\)\.click\(\)', stripped)
        if m_role_click:
            role, name = m_role_click.group(1), m_role_click.group(2)
            raw_steps.append({
                "action": ActionType.CLICK,
                "locator_strategy": LocatorStrategy.ROLE,
                "role_name": role,
                "selector_value": name or role,
                "description": f"Click {role} ({name or ''})",
            })
            continue

        # 9. page.get_by_text("text").click()
        m_text_click = re.search(r'page\.get_by_text\(["\']([^"\']+)["\']\)\.click\(\)', stripped)
        if m_text_click:
            txt = m_text_click.group(1)
            raw_steps.append({
                "action": ActionType.CLICK,
                "locator_strategy": LocatorStrategy.TEXT,
                "selector_value": txt,
                "description": f"Click text '{txt}'",
            })
            continue

        # 10. expect(...).to_contain_text("val") or to_have_text("val")
        m_assert = re.search(r'expect\(page\.(?:get_by_test_id|locator)\(["\']([^"\']+)["\']\)\)\.(?:to_contain_text|to_have_text)\(["\']([^"\']+)["\']\)', stripped)
        if m_assert:
            sel, exp = m_assert.group(1), m_assert.group(2)
            raw_steps.append({
                "action": ActionType.ASSERT_TEXT,
                "locator_strategy": LocatorStrategy.TEST_ID,
                "selector_value": sel,
                "expected_value": exp,
                "description": f"Assert {sel} contains '{exp}'",
            })
            continue

    # Filter redundant click on element X immediately followed by fill on element X
    filtered_steps: List[dict] = []
    for i, s in enumerate(raw_steps):
        if (
            s["action"] == ActionType.CLICK
            and i + 1 < len(raw_steps)
            and raw_steps[i + 1]["action"] == ActionType.FILL
            and raw_steps[i + 1].get("selector_value") == s.get("selector_value")
        ):
            # Skip redundant focus click before fill
            continue
        filtered_steps.append(s)

    # Ensure step 1 is navigate
    if not filtered_steps or filtered_steps[0]["action"] != ActionType.NAVIGATE:
        nav_url = default_url.rstrip("/") + "/"
        filtered_steps.insert(0, {
            "action": ActionType.NAVIGATE,
            "input_value": nav_url,
            "description": f"Navigate to {nav_url}",
        })

    # Convert to validated TestStep models with sequential indexing
    final_steps: List[TestStep] = []
    for idx, s in enumerate(filtered_steps, start=1):
        s["step_number"] = idx
        final_steps.append(TestStep.model_validate(s))

    return final_steps


def create_test_case_from_recording(
    title: str,
    steps: List[TestStep],
    requirement_key: str,
    tc_id: str,
    objective: Optional[str] = None,
) -> TestCase:
    """Wraps recorded steps into a fully validated TestCase model."""
    return TestCase(
        id=tc_id,
        requirement_key=requirement_key,
        source_ac_id=f"REC-{tc_id}",
        title=title,
        objective=objective or f"User-recorded exploratory scenario via Playwright Codegen",
        category=TestCategory.POSITIVE,
        steps=steps,
        expected_result="Recorded sequence completes without browser error",
    )

