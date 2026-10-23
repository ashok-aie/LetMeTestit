"""
Playwright Browser Context Lifecycle Manager
Safely manages Chromium browser contexts, viewport settings, tracing, and clean teardown.
Supports launching interactive Chrome directly onto Windows interactive desktop (WinSta0\\Default)
and attaching via Chrome DevTools Protocol (CDP) for full visual execution on user screen.
"""
import logging
import os
import shutil
import socket
import tempfile
import time
import urllib.request
from typing import Optional, Any
from pathlib import Path
from playwright.sync_api import sync_playwright, Playwright, Browser, BrowserContext, Page

from app.config import settings
from app.browser.evidence import EvidenceManager
from app.browser.locators import LocatorResolver

logger = logging.getLogger(__name__)

if os.name == "nt":
    import ctypes
    import ctypes.wintypes

    class STARTUPINFOW(ctypes.Structure):
        _fields_ = [
            ("cb", ctypes.wintypes.DWORD),
            ("lpReserved", ctypes.wintypes.LPWSTR),
            ("lpDesktop", ctypes.wintypes.LPWSTR),
            ("lpTitle", ctypes.wintypes.LPWSTR),
            ("dwX", ctypes.wintypes.DWORD),
            ("dwY", ctypes.wintypes.DWORD),
            ("dwXSize", ctypes.wintypes.DWORD),
            ("dwYSize", ctypes.wintypes.DWORD),
            ("dwXCountChars", ctypes.wintypes.DWORD),
            ("dwYCountChars", ctypes.wintypes.DWORD),
            ("dwFillAttribute", ctypes.wintypes.DWORD),
            ("dwFlags", ctypes.wintypes.DWORD),
            ("wShowWindow", ctypes.wintypes.WORD),
            ("cbReserved2", ctypes.wintypes.WORD),
            ("lpReserved2", ctypes.c_char_p),
            ("hStdInput", ctypes.wintypes.HANDLE),
            ("hStdOutput", ctypes.wintypes.HANDLE),
            ("hStdError", ctypes.wintypes.HANDLE),
        ]

    class PROCESS_INFORMATION(ctypes.Structure):
        _fields_ = [
            ("hProcess", ctypes.wintypes.HANDLE),
            ("hThread", ctypes.wintypes.HANDLE),
            ("dwProcessId", ctypes.wintypes.DWORD),
            ("dwThreadId", ctypes.wintypes.DWORD),
        ]


def find_free_port() -> int:
    """Finds an unused localhost TCP port."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def wait_for_cdp_ready(port: int, timeout_sec: float = 8.0) -> bool:
    """Polls Chrome DevTools Protocol /json/version endpoint until responsive."""
    start_time = time.time()
    url = f"http://127.0.0.1:{port}/json/version"
    while time.time() - start_time < timeout_sec:
        try:
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=1.0) as resp:
                if resp.status == 200:
                    return True
        except Exception:
            time.sleep(0.15)
    return False


def find_system_chrome_path() -> Optional[str]:
    """Finds Google Chrome executable path on the system."""
    candidates = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        os.path.join(os.environ.get("LOCALAPPDATA", ""), r"Google\Chrome\Application\chrome.exe"),
        os.path.join(os.environ.get("PROGRAMFILES", ""), r"Google\Chrome\Application\chrome.exe"),
        os.path.join(os.environ.get("PROGRAMFILES(X86)", ""), r"Google\Chrome\Application\chrome.exe"),
    ]
    for path in candidates:
        if path and os.path.exists(path):
            return path
    return shutil.which("chrome") or shutil.which("google-chrome")


def attach_to_interactive_desktop() -> bool:
    """
    On Windows (RDP / Multi-session / Session 7), binds the thread to the
    interactive 'Default' desktop so Chrome opens visibly on the user's monitor.
    """
    if os.name == "nt":
        try:
            import ctypes
            user32 = ctypes.windll.user32
            DESKTOP_ALL = 0x01FF
            h_default = user32.OpenDesktopW("Default", 0, False, DESKTOP_ALL)
            if h_default:
                user32.SetThreadDesktop(h_default)
                logger.info("Bound browser worker thread to interactive 'Default' desktop.")
                return True
        except Exception as e:
            logger.debug("attach_to_interactive_desktop: %s", e)
    return False


def bring_browser_to_foreground():
    """Brings Chrome to the foreground on the active interactive desktop."""
    if os.name == "nt":
        try:
            import ctypes
            user32 = ctypes.windll.user32
            SW_SHOWMAXIMIZED = 3

            WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_int, ctypes.c_int)
            def enum_cb(hwnd, lparam):
                if user32.IsWindowVisible(hwnd):
                    length = user32.GetWindowTextLengthW(hwnd)
                    if length > 0:
                        buff = ctypes.create_unicode_buffer(length + 1)
                        user32.GetWindowTextW(hwnd, buff, length + 1)
                        txt = buff.value.lower()
                        if "chrome" in txt or "sap" in txt:
                            user32.ShowWindow(hwnd, SW_SHOWMAXIMIZED)
                            user32.SetForegroundWindow(hwnd)
                return True

            h_desk = user32.OpenDesktopW("Default", 0, False, 0x01FF)
            if h_desk:
                user32.EnumDesktopWindows(h_desk, WNDENUMPROC(enum_cb), 0)
        except Exception:
            pass


_RESOLVED_SAP_HOST_RULE: Optional[str] = None


def get_sap_host_resolver_rule() -> str:
    """
    Checks if s4srv25.nodomain.com is reachable via system DNS/hosts.
    If unreachable, probes the active SAP S/4HANA IP (192.168.1.198) and returns
    Chromium '--host-resolver-rules' argument to map the domain at browser level.
    """
    global _RESOLVED_SAP_HOST_RULE
    if _RESOLVED_SAP_HOST_RULE is not None:
        return _RESOLVED_SAP_HOST_RULE

    target_domain = getattr(settings, "sap_host_domain", "s4srv25.nodomain.com")
    sap_port = 44325

    # 1. Quick probe: does standard DNS / hosts reach port 44325?
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.8)
            if s.connect_ex((target_domain, sap_port)) == 0:
                _RESOLVED_SAP_HOST_RULE = ""
                return ""
    except Exception:
        pass

    # 2. Probe candidate IPs known on LAN for SAP S/4HANA instance 25
    candidates = ["192.168.1.198", "192.168.1.50"]
    for ip in candidates:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(1.0)
                if s.connect_ex((ip, sap_port)) == 0:
                    rule = f"MAP {target_domain} {ip}, MAP s4h2025 {ip}"
                    logger.info("Auto-configured Chrome host resolver: %s", rule)
                    _RESOLVED_SAP_HOST_RULE = rule
                    return rule
        except Exception:
            continue

    _RESOLVED_SAP_HOST_RULE = ""
    return ""


class BrowserContextManager:
    """
    Context manager that guarantees clean startup, tracing, screenshot capture on failure,
    and deterministic shutdown of Playwright Chromium instances.
    """

    def __init__(
        self,
        headless: Optional[bool] = None,
        slow_mo_ms: Optional[int] = None,
        evidence_manager: Optional[EvidenceManager] = None,
        enable_tracing: bool = True,
        cdp_url: Optional[str] = None,
        test_case_id: Optional[str] = None,
    ):
        self.headless = settings.browser_headless if headless is None else headless
        self.cdp_url = cdp_url or settings.cdp_endpoint_url
        if slow_mo_ms is not None:
            self.slow_mo_ms = slow_mo_ms
        elif not self.headless:
            self.slow_mo_ms = max(settings.browser_slow_mo_ms, 500)
        else:
            self.slow_mo_ms = settings.browser_slow_mo_ms

        self.evidence_manager = evidence_manager or EvidenceManager()
        self.enable_tracing = enable_tracing
        self.test_case_id = test_case_id

        self._playwright: Optional[Playwright] = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None
        self._locator_resolver: Optional[LocatorResolver] = None
        self._chrome_pi: Optional[Any] = None
        self._chrome_tmpdir: Optional[str] = None

    def __enter__(self) -> "BrowserContextManager":
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            # Capture failure screenshot if an error occurred while page was active
            self.capture_failure_screenshot("error_state")
        self.stop()
        # Do not suppress the exception
        return False

    def start(self) -> None:
        """Launches Chromium or connects to a remote Chrome instance via CDP."""
        if not self.headless:
            attach_to_interactive_desktop()

        resolver_rule = get_sap_host_resolver_rule()

        # If running headed on Windows without explicit external CDP, spawn Chrome directly
        # on the interactive 'WinSta0\\Default' desktop to bypass agent virtual desktop isolation.
        if not self.headless and os.name == "nt" and not self.cdp_url:
            chrome_exe = find_system_chrome_path()
            if chrome_exe:
                try:
                    cdp_port = find_free_port()
                    tmpdir = tempfile.mkdtemp(prefix="pw_chrome_interactive_")
                    si = STARTUPINFOW()
                    si.cb = ctypes.sizeof(STARTUPINFOW)
                    si.lpDesktop = "WinSta0\\Default"
                    pi = PROCESS_INFORMATION()

                    rule_flag = f'--host-resolver-rules="{resolver_rule}" ' if resolver_rule else ""
                    cmd = (
                        f'"{chrome_exe}" '
                        f'--remote-debugging-port={cdp_port} '
                        f'--user-data-dir="{tmpdir}" '
                        '--ignore-certificate-errors '
                        '--test-type '
                        '--disable-infobars '
                        '--silent-debugger-extension-api '
                        '--incognito '
                        '--start-maximized '
                        '--no-first-run '
                        '--no-default-browser-check '
                        f'{rule_flag}'
                        'about:blank'
                    )
                    kernel32 = ctypes.windll.kernel32
                    created = kernel32.CreateProcessW(
                        None, cmd, None, None, False, 0, None, None, ctypes.byref(si), ctypes.byref(pi)
                    )
                    if created:
                        if wait_for_cdp_ready(cdp_port, timeout_sec=8.0):
                            self._chrome_pi = pi
                            self._chrome_tmpdir = tmpdir
                            self.cdp_url = f"http://127.0.0.1:{cdp_port}"
                            logger.info(
                                "Launched visible Chrome on WinSta0\\Default (PID: %d, Port: %d)",
                                pi.dwProcessId,
                                cdp_port,
                            )
                        else:
                            logger.warning("Chrome launched but CDP port %d timed out. Falling back to default launch.", cdp_port)
                            kernel32.TerminateProcess(pi.hProcess, 0)
                            kernel32.CloseHandle(pi.hProcess)
                            kernel32.CloseHandle(pi.hThread)
                            shutil.rmtree(tmpdir, ignore_errors=True)
                except Exception as e:
                    logger.warning("Failed to launch interactive Chrome via CreateProcessW: %s. Falling back.", e)

        self._playwright = sync_playwright().start()

        if self.cdp_url:
            self._browser = self._playwright.chromium.connect_over_cdp(
                self.cdp_url,
                slow_mo=self.slow_mo_ms,
            )
            if self._browser.contexts:
                self._context = self._browser.contexts[0]
            else:
                self._context = self._browser.new_context(
                    viewport={"width": 1280, "height": 720},
                    ignore_https_errors=True,
                )
            if self.enable_tracing:
                try:
                    self._context.tracing.start(screenshots=True, snapshots=True, sources=True)
                except Exception:
                    pass
            if self._context.pages:
                self._page = self._context.pages[0]
            else:
                self._page = self._context.new_page()
            self._page.set_default_timeout(settings.browser_step_timeout_ms)
            self._page.set_default_navigation_timeout(max(settings.browser_step_timeout_ms, 60000))
            self._locator_resolver = LocatorResolver(self._page)
            bring_browser_to_foreground()
            return

        launch_args = [
            "--ignore-certificate-errors",
            "--test-type",
            "--disable-infobars",
            "--silent-debugger-extension-api",
            "--incognito",
            "--start-maximized",
            "--no-default-browser-check",
            "--no-first-run",
        ]
        if resolver_rule:
            launch_args.append(f"--host-resolver-rules={resolver_rule}")
        try:
            self._browser = self._playwright.chromium.launch(
                channel="chrome",
                headless=self.headless,
                slow_mo=self.slow_mo_ms,
                args=launch_args,
            )
        except Exception as chrome_err:
            logger.info("Google Chrome channel not available (%s); launching bundled Chromium", chrome_err)
            self._browser = self._playwright.chromium.launch(
                headless=self.headless,
                slow_mo=self.slow_mo_ms,
                args=launch_args,
            )

        if not self.headless:
            self._context = self._browser.new_context(
                no_viewport=True,
                ignore_https_errors=True,
            )
        else:
            self._context = self._browser.new_context(
                viewport={"width": 1280, "height": 720},
                ignore_https_errors=True,
            )

        if self.enable_tracing:
            self._context.tracing.start(
                screenshots=True,
                snapshots=True,
                sources=True,
            )

        self._page = self._context.new_page()
        if not self.headless:
            try:
                self._page.bring_to_front()
            except Exception:
                pass
            bring_browser_to_foreground()
        self._page.set_default_timeout(settings.browser_step_timeout_ms)
        self._page.set_default_navigation_timeout(max(settings.browser_step_timeout_ms, 60000))
        self._locator_resolver = LocatorResolver(self._page)

    @property
    def page(self) -> Page:
        if self._page is None:
            raise RuntimeError("BrowserContextManager has not been started.")
        return self._page

    @property
    def locators(self) -> LocatorResolver:
        if self._locator_resolver is None:
            raise RuntimeError("BrowserContextManager has not been started.")
        return self._locator_resolver

    def capture_screenshot(self, test_case_id: str, step_number: Optional[int] = None) -> Path:
        """Captures a full-page screenshot and saves it to the evidence directory."""
        if self._page is None:
            raise RuntimeError("Page is not active.")
        path = self.evidence_manager.get_screenshot_path(test_case_id, step_number)
        self._page.screenshot(path=str(path), full_page=True)
        return path

    def capture_failure_screenshot(self, test_case_id: str) -> Optional[Path]:
        """Safely captures a screenshot upon failure without raising secondary exceptions."""
        try:
            if self._page and not self._page.is_closed():
                return self.capture_screenshot(test_case_id)
        except Exception:
            pass
        return None

    def stop(self) -> None:
        """Stops tracing, exports trace archive, closes context, and terminates interactive Chrome."""
        try:
            if self._context and self.enable_tracing:
                trace_path = self.evidence_manager.get_trace_path(self.test_case_id)
                self._context.tracing.stop(path=str(trace_path))
                default_trace = self.evidence_manager.trace_file_path
                if trace_path != default_trace:
                    try:
                        shutil.copyfile(trace_path, default_trace)
                    except Exception:
                        pass
        except Exception:
            pass

        try:
            if self._context:
                self._context.close()
        except Exception:
            pass

        try:
            if self._browser:
                self._browser.close()
        except Exception:
            pass

        try:
            if self._playwright:
                self._playwright.stop()
        except Exception:
            pass

        if self._chrome_pi is not None and os.name == "nt":
            try:
                kernel32 = ctypes.windll.kernel32
                kernel32.TerminateProcess(self._chrome_pi.hProcess, 0)
                kernel32.CloseHandle(self._chrome_pi.hProcess)
                kernel32.CloseHandle(self._chrome_pi.hThread)
            except Exception:
                pass
            self._chrome_pi = None

        if self._chrome_tmpdir and os.path.exists(self._chrome_tmpdir):
            try:
                shutil.rmtree(self._chrome_tmpdir, ignore_errors=True)
            except Exception:
                pass
            self._chrome_tmpdir = None
