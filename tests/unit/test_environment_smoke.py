"""
Phase 1 Smoke Verification Test
Verifies that the Python environment, dependencies, and Playwright Chromium driver are healthy.
"""
import pytest
from playwright.sync_api import sync_playwright

def test_core_dependencies_importable():
    """Verify that all mission-critical packages can be imported without conflict."""
    import streamlit
    import langgraph
    import langchain_core
    import pydantic
    import httpx
    import fastapi
    import uvicorn
    import jinja2

    import importlib.metadata
    assert streamlit.__version__ is not None
    assert importlib.metadata.version("langgraph") is not None
    assert pydantic.__version__ is not None

def test_playwright_chromium_headless():
    """Verify that Playwright Chromium can launch, navigate to an HTML string, and extract text."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()
        page.set_content("<title>Let me TEST it</title><h1 id='banner'>Agentic QA Platform</h1>")
        
        banner_text = page.locator("#banner").inner_text()
        assert banner_text == "Agentic QA Platform"
        assert page.title() == "Let me TEST it"
        
        context.close()
        browser.close()
