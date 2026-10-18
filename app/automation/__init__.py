"""
Browser Automation & Playwright Engine Package.
Contains Playwright test execution engine, accessible locator resolution,
browser context lifecycle, recording, evidence capture, and script exporting.
"""
from app.automation.executor import TestExecutor, TestExecutionError
from app.automation.locators import LocatorResolver, ElementNotFoundError, AmbiguousLocatorError
from app.automation.context import BrowserContextManager
from app.automation.evidence import EvidenceManager
from app.automation.recorder import SessionRecorder
from app.automation.exporter import export_suite_to_playwright_script

__all__ = [
    "TestExecutor",
    "TestExecutionError",
    "LocatorResolver",
    "ElementNotFoundError",
    "AmbiguousLocatorError",
    "BrowserContextManager",
    "EvidenceManager",
    "SessionRecorder",
    "export_suite_to_playwright_script",
]

