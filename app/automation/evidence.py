"""
Evidence Manager Module
Handles file paths, directories, and persistence for Playwright traces, screenshots, and logs.
"""
import os
import shutil
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional

from app.config import settings


class EvidenceManager:
    """Manages artifact folders, screenshots, and trace archives for test runs."""

    def __init__(self, run_id: Optional[str] = None):
        self.run_id = run_id or datetime.now(timezone.utc).strftime("run_%Y%m%d_%H%M%S")
        self.base_dir = (Path(settings.artifacts_dir).resolve() / "runs" / self.run_id).resolve()
        self.screenshots_dir = self.base_dir / "screenshots"
        self.traces_dir = self.base_dir / "traces"
        self._ensure_directories()

    def _ensure_directories(self) -> None:
        """Creates the artifact folder tree if not present."""
        self.screenshots_dir.mkdir(parents=True, exist_ok=True)
        self.traces_dir.mkdir(parents=True, exist_ok=True)

    @property
    def trace_file_path(self) -> Path:
        """Default path for the Playwright trace.zip archive."""
        return (self.traces_dir / "trace.zip").resolve()

    def get_screenshot_path(self, test_case_id: str, step_number: Optional[int] = None) -> Path:
        """Returns the targeted filepath for a screenshot."""
        clean_tc_id = test_case_id.replace(" ", "_").replace("/", "-")
        if step_number is not None:
            filename = f"{clean_tc_id}_step_{step_number}.png"
        else:
            filename = f"{clean_tc_id}_failure.png"
        return (self.screenshots_dir / filename).resolve()

    def cleanup_run(self) -> None:
        """Removes the artifacts directory for this run."""
        if self.base_dir.exists():
            shutil.rmtree(self.base_dir)
