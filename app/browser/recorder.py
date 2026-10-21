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
import ast
import textwrap
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


def run_process_on_interactive_desktop(
    cmd_args: List[str],
    timeout_seconds: int = 300,
) -> int:
    """
    Launches a process explicitly on the user's interactive desktop ('WinSta0\\Default')
    using Win32 CreateProcessW, ensuring GUI windows (e.g. Playwright Chromium and Inspector)
    appear on the user's visible display rather than a hidden background desktop.
    """
    if sys.platform != "win32":
        proc = subprocess.run(
            cmd_args,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_seconds,
        )
        return proc.returncode

    try:
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.windll.kernel32

        class STARTUPINFO(ctypes.Structure):
            _fields_ = [
                ("cb", wintypes.DWORD),
                ("lpReserved", wintypes.LPWSTR),
                ("lpDesktop", wintypes.LPWSTR),
                ("lpTitle", wintypes.LPWSTR),
                ("dwX", wintypes.DWORD),
                ("dwY", wintypes.DWORD),
                ("dwXSize", wintypes.DWORD),
                ("dwYSize", wintypes.DWORD),
                ("dwXCountChars", wintypes.DWORD),
                ("dwYCountChars", wintypes.DWORD),
                ("dwFillAttribute", wintypes.DWORD),
                ("dwFlags", wintypes.DWORD),
                ("wShowWindow", wintypes.WORD),
                ("cbReserved2", wintypes.WORD),
                ("lpReserved2", ctypes.c_char_p),
                ("hStdInput", wintypes.HANDLE),
                ("hStdOutput", wintypes.HANDLE),
                ("hStdError", wintypes.HANDLE),
            ]

        class PROCESS_INFORMATION(ctypes.Structure):
            _fields_ = [
                ("hProcess", wintypes.HANDLE),
                ("hThread", wintypes.HANDLE),
                ("dwProcessId", wintypes.DWORD),
                ("dwThreadId", wintypes.DWORD),
            ]

        si = STARTUPINFO()
        si.cb = ctypes.sizeof(STARTUPINFO)
        si.lpDesktop = "WinSta0\\Default"

        pi = PROCESS_INFORMATION()
        cmd_str = subprocess.list2cmdline(cmd_args)
        logger.info("Launching on WinSta0\\Default: %s", cmd_str)

        success = kernel32.CreateProcessW(
            None,
            cmd_str,
            None,
            None,
            False,
            0,
            None,
            None,
            ctypes.byref(si),
            ctypes.byref(pi),
        )

        if not success:
            err = kernel32.GetLastError()
            logger.warning("CreateProcessW to WinSta0\\Default failed with code %d; falling back to subprocess.run", err)
            proc = subprocess.run(
                cmd_args,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout_seconds,
            )
            return proc.returncode

        wait_ms = timeout_seconds * 1000 if timeout_seconds else 0xFFFFFFFF
        wait_res = kernel32.WaitForSingleObject(pi.hProcess, wait_ms)

        exit_code = wintypes.DWORD()
        kernel32.GetExitCodeProcess(pi.hProcess, ctypes.byref(exit_code))

        kernel32.CloseHandle(pi.hProcess)
        kernel32.CloseHandle(pi.hThread)

        if wait_res == 0x00000102:  # WAIT_TIMEOUT
            logger.warning("Interactive codegen session timed out")
            return -1

        return int(exit_code.value)
    except Exception as e:
        logger.warning("Failed to launch on WinSta0\\Default (%s); falling back to subprocess.run", e)
        proc = subprocess.run(
            cmd_args,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_seconds,
        )
        return proc.returncode


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

    cmd = [
        sys.executable,
        "-m",
        "playwright",
        "codegen",
        "--ignore-https-errors",
        "--target",
        "python",
        "-o",
        str(output_file),
        "--test-id-attribute",
        "data-testid",
    ]

    clean_url = target_url.strip() if target_url else ""
    if clean_url:
        cmd.append(clean_url)

    logger.info("Launching Playwright Codegen: %s", " ".join(cmd))
    try:
        rc = run_process_on_interactive_desktop(cmd, timeout_seconds=timeout_seconds)
        if rc != 0 and not output_file.exists() and clean_url:
            logger.info("Retrying codegen with 'about:blank' fallback on desktop...")
            fallback_cmd = [
                sys.executable,
                "-m",
                "playwright",
                "codegen",
                "--ignore-https-errors",
                "--target",
                "python",
                "-o",
                str(output_file),
                "--test-id-attribute",
                "data-testid",
                "about:blank",
            ]
            run_process_on_interactive_desktop(fallback_cmd, timeout_seconds=timeout_seconds)
    except Exception as e:
        logger.error("Failed to run Playwright codegen: %s", e)
        raise

    if output_file.exists():
        return output_file.read_text(encoding="utf-8")
    return ""


def _extract_locator_from_ast_call(node) -> Optional[dict]:
    curr = node
    role = None
    role_name = None
    text_val = None
    label_val = None
    testid_val = None
    css_sel = None
    filter_text = None

    while isinstance(curr, ast.Call):
        func = curr.func
        if isinstance(func, ast.Attribute):
            name = func.attr
            if name == "get_by_role":
                role = ast.literal_eval(curr.args[0]) if curr.args else "button"
                for kw in curr.keywords:
                    if kw.arg == "name":
                        role_name = ast.literal_eval(kw.value)
            elif name == "get_by_text":
                text_val = ast.literal_eval(curr.args[0]) if curr.args else ""
            elif name == "get_by_label":
                label_val = ast.literal_eval(curr.args[0]) if curr.args else ""
            elif name == "get_by_test_id":
                testid_val = ast.literal_eval(curr.args[0]) if curr.args else ""
            elif name == "filter":
                for kw in curr.keywords:
                    if kw.arg == "has_text":
                        filter_text = ast.literal_eval(kw.value)
            elif name == "locator":
                s = ast.literal_eval(curr.args[0]) if curr.args else ""
                # Ignore outer iframe locators like iframe[name="..."]
                if not (s.startswith("iframe") and curr != node):
                    css_sel = s
            if isinstance(func.value, ast.Call):
                curr = func.value
                continue
        break

    if testid_val:
        return {
            "locator_strategy": LocatorStrategy.TEST_ID,
            "selector_value": testid_val,
        }
    elif role and role_name:
        return {
            "locator_strategy": LocatorStrategy.ROLE,
            "role_name": role,
            "selector_value": role_name,
        }
    elif text_val:
        return {
            "locator_strategy": LocatorStrategy.TEXT,
            "selector_value": text_val,
        }
    elif label_val:
        return {
            "locator_strategy": LocatorStrategy.TEXT,
            "selector_value": label_val,
        }
    elif css_sel:
        clean = css_sel.replace('\\"', '"').replace('\\\\', '\\')
        if filter_text:
            clean = f"{clean}:has-text('{filter_text}')"
        if "ordered_prod" in clean:
            clean = f"[id*='ordered_prod'], {clean}"
        elif "quantity" in clean:
            clean = f"[id*='quantity'], {clean}"
        return {
            "locator_strategy": LocatorStrategy.CSS,
            "selector_value": clean,
        }
    elif role:
        return {
            "locator_strategy": LocatorStrategy.ROLE,
            "role_name": role,
            "selector_value": role,
        }
    return None


def parse_recorded_script(
    script_content: str,
    default_url: str = "http://127.0.0.1:8000/",
) -> List[TestStep]:
    """
    Parses Python Playwright codegen script into structured TestStep models.
    Uses Python AST parsing to guarantee accurate capture of chained locators,
    embedded iframes, escaped characters, and filters.
    """
    raw_steps: List[dict] = []
    cleaned_script = textwrap.dedent(script_content).strip()

    # 1. Primary: Abstract Syntax Tree parsing
    try:
        tree = ast.parse(cleaned_script)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Expr) or not isinstance(node.value, ast.Call):
                continue
            call = node.value
            if not isinstance(call.func, ast.Attribute):
                continue
            method_name = call.func.attr

            if method_name in ("to_contain_text", "to_have_text") and call.args:
                exp_val = str(ast.literal_eval(call.args[0]))
                if isinstance(call.func.value, ast.Call) and getattr(call.func.value.func, "id", None) == "expect":
                    inner_loc_call = call.func.value.args[0] if call.func.value.args else None
                    if inner_loc_call:
                        step_info = _extract_locator_from_ast_call(inner_loc_call)
                        if step_info:
                            step_info["action"] = ActionType.ASSERT_TEXT
                            step_info["expected_value"] = exp_val
                            step_info["description"] = f"Assert {step_info.get('selector_value')} contains '{exp_val}'"
                            raw_steps.append(step_info)
                continue

            if method_name not in ("goto", "click", "fill", "press", "select_option"):
                continue

            if method_name == "goto" and call.args:
                url = ast.literal_eval(call.args[0])
                raw_steps.append({
                    "action": ActionType.NAVIGATE,
                    "input_value": url,
                    "description": f"Navigate to {url}",
                })
            elif method_name in ("fill", "press") and call.args:
                val = str(ast.literal_eval(call.args[0]))
                step_info = _extract_locator_from_ast_call(call.func.value)
                if step_info:
                    step_info["action"] = ActionType.FILL
                    step_info["input_value"] = val
                    action_word = "Press" if method_name == "press" else "Enter"
                    step_info["description"] = f"{action_word} '{val}' into {step_info.get('selector_value')}"
                    raw_steps.append(step_info)
            elif method_name == "click":
                step_info = _extract_locator_from_ast_call(call.func.value)
                if step_info:
                    step_info["action"] = ActionType.CLICK
                    step_info["description"] = f"Click {step_info.get('selector_value')}"
                    raw_steps.append(step_info)
            elif method_name == "select_option" and call.args:
                val = str(ast.literal_eval(call.args[0]))
                step_info = _extract_locator_from_ast_call(call.func.value)
                if step_info:
                    step_info["action"] = ActionType.SELECT_OPTION
                    step_info["input_value"] = val
                    step_info["description"] = f"Select '{val}' in {step_info.get('selector_value')}"
                    raw_steps.append(step_info)
    except Exception as e:
        logger.warning("AST parsing failed (%s); falling back to regex parser", e)

    # 2. Secondary fallback if AST yielded no steps
    if not raw_steps:
        lines = cleaned_script.splitlines()
        for line in lines:
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue

            m_goto = re.search(r'page\.goto\(["\']([^"\']+)["\']\)', stripped)
            if m_goto:
                raw_steps.append({
                    "action": ActionType.NAVIGATE,
                    "input_value": m_goto.group(1),
                    "description": f"Navigate to {m_goto.group(1)}",
                })
                continue

            m_loc_click = re.search(r'(?:page|content_frame)\.locator\(["\']([^"\']+)["\']\)(?:\.[a-zA-Z_0-9]+\([^)]*\))*\.click\(', stripped)
            if m_loc_click:
                sel = m_loc_click.group(1)
                raw_steps.append({
                    "action": ActionType.CLICK,
                    "locator_strategy": LocatorStrategy.CSS,
                    "selector_value": sel,
                    "description": f"Click {sel}",
                })
                continue

            m_loc_fill = re.search(r'(?:page|content_frame)\.locator\(["\']([^"\']+)["\']\)(?:\.[a-zA-Z_0-9]+\([^)]*\))*\.fill\(["\']([^"\']*)["\']\)', stripped)
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

            m_assert = re.search(r'expect\((?:page|content_frame)\.(?:get_by_test_id|locator)\(["\']([^"\']+)["\']\)\)\.(?:to_contain_text|to_have_text)\(["\']([^"\']+)["\']\)', stripped)
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

            m_role_fill = re.search(r'(?:page|content_frame)\.get_by_role\(["\']([^"\']+)["\'](?:,\s*(?:name=)?["\']([^"\']+)["\'](?:,\s*exact=(?:True|False))?)?\)\.fill\(["\']([^"\']*)["\']\)', stripped)
            if m_role_fill:
                role, name, val = m_role_fill.group(1), m_role_fill.group(2), m_role_fill.group(3)
                raw_steps.append({
                    "action": ActionType.FILL,
                    "locator_strategy": LocatorStrategy.ROLE,
                    "role_name": role,
                    "selector_value": name or role,
                    "input_value": val,
                    "description": f"Fill '{val}' in {role} ({name or ''})",
                })
                continue

            m_role_click = re.search(r'(?:page|content_frame)\.get_by_role\(["\']([^"\']+)["\'](?:,\s*(?:name=)?["\']([^"\']+)["\'](?:,\s*exact=(?:True|False))?)?\)\.click\(', stripped)
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

            m_text_click = re.search(r'(?:page|content_frame)\.get_by_text\(["\']([^"\']+)["\']\)\.click\(', stripped)
            if m_text_click:
                txt = m_text_click.group(1)
                raw_steps.append({
                    "action": ActionType.CLICK,
                    "locator_strategy": LocatorStrategy.TEXT,
                    "selector_value": txt,
                    "description": f"Click text '{txt}'",
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
    group: Optional[str] = "Recorded",
    tags: Optional[List[str]] = None,
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
        group=group or "Recorded",
        tags=tags or ["recorded", "browser"],
        expected_result="Recorded sequence completes without browser error",
    )

