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


class SessionRecorder:
    """Convenience wrapper for interactive Playwright recording sessions."""

    @staticmethod
    def record(
        target_url: str = "http://127.0.0.1:8000/",
        output_file: Optional[Path] = None,
        timeout_seconds: int = 300,
    ) -> str:
        return record_playwright_session(
            target_url=target_url,
            output_file=output_file,
            timeout_seconds=timeout_seconds,
        )

    @staticmethod
    def parse(
        script_content: str,
        default_url: str = "http://127.0.0.1:8000/",
    ) -> List[TestStep]:
        return parse_recorded_script(script_content, default_url=default_url)

