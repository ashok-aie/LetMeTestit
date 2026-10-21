"""
Test Designer Module
Uses local Ollama LLM to synthesize Pydantic-validated TestSuites from JiraRequirements,
with bounded self-correction retries on schema violations.
"""
import re
import json
import logging
from typing import Optional, Dict, Any, List
from pydantic import ValidationError

from app.config import settings
from app.agents.llm_client import OllamaClient, LLMResponse
from app.models.requirements import JiraRequirement, AcceptanceCriterion
from app.models.test_suite import TestSuite, TestCase, TestStep, ActionType, LocatorStrategy, TestCategory
from app.test_design.prompts import (
    SYSTEM_TEST_DESIGNER_PROMPT,
    format_requirement_prompt,
    format_schema_retry_prompt,
    format_single_ac_prompt,
)

logger = logging.getLogger(__name__)

try:
    from langfuse import observe
except ImportError:
    def observe(*args, **kwargs):
        def decorator(f):
            return f
        return decorator


class TestDesignError(Exception):
    """Base exception for test design generation failures."""
    pass


class SchemaValidationError(TestDesignError):
    """Raised when generated test suite violates Pydantic schema after retries."""
    pass


class TestDesigner:
    """Orchestrates test case generation and schema self-correction."""
    __test__ = False

    def __init__(
        self,
        llm_client: Optional[Any] = None,
        max_retries: int = 2,
    ):
        self.llm = llm_client or OllamaClient()
        self.max_retries = max_retries

    @observe(name="TestDesigner.generate_suite")
    def generate_suite(
        self,
        requirement: JiraRequirement,
        target_base_url: Optional[str] = None,
        progress_callback: Optional[Any] = None,
    ) -> TestSuite:
        """
        Synthesizes an executable, strongly-typed TestSuite from a JiraRequirement.
        
        Args:
            requirement: JiraRequirement model containing summary, description, and ACs.
            target_base_url: Target application URL (e.g. http://localhost:8000).
            progress_callback: Optional callback(current, total, message) for incremental progress reporting.
            
        Returns:
            Validated TestSuite model with SHA-256 hash.
        """
        base_url = target_base_url or settings.demo_app_url

        # Incremental per-AC generation when progress_callback is provided
        if progress_callback is not None and requirement.acceptance_criteria:
            return self._generate_suite_incremental(requirement, base_url, progress_callback)
        user_prompt = format_requirement_prompt(requirement, target_base_url=base_url)

        current_prompt = user_prompt
        last_error = ""
        last_raw_output = ""

        for attempt in range(self.max_retries + 1):
            logger.info("Generating test suite for %s (attempt %d/%d)", requirement.key, attempt + 1, self.max_retries + 1)
            response: LLMResponse = self.llm.generate(
                prompt=current_prompt,
                system_prompt=SYSTEM_TEST_DESIGNER_PROMPT,
                json_mode=True,
            )

            last_raw_output = response.content
            try:
                # 1. Parse JSON
                parsed_dict = response.parse_json()

                # If model wrapped in a parent key like {"test_suite": {...}}
                if "test_suite" in parsed_dict and isinstance(parsed_dict["test_suite"], dict):
                    parsed_dict = parsed_dict["test_suite"]

                # Ensure requirement_key is bound
                parsed_dict.setdefault("requirement_key", requirement.key)
                parsed_dict.setdefault("suite_id", f"SUITE-{requirement.key}")

                # 2. Pydantic validation
                suite = TestSuite.model_validate(parsed_dict)
                normalized_tcs = [self._enforce_sap_lifecycle(tc, base_url, requirement) for tc in suite.test_cases]
                suite = suite.model_copy(update={"test_cases": normalized_tcs})
                logger.info(
                    "Successfully synthesized %d test cases for %s in %.2fs (Hash: %s)",
                    len(suite.test_cases),
                    requirement.key,
                    response.latency_seconds,
                    suite.compute_hash()[:12],
                )
                return suite

            except (json.JSONDecodeError, ValidationError) as exc:
                last_error = str(exc)
                logger.warning(
                    "Schema validation failed on attempt %d: %s. Initiating self-correction.",
                    attempt + 1,
                    last_error,
                )

                if attempt < self.max_retries:
                    current_prompt = format_schema_retry_prompt(
                        original_prompt=user_prompt,
                        error_message=last_error,
                        raw_invalid_output=last_raw_output,
                    )
                else:
                    raise SchemaValidationError(
                        f"Failed to generate schema-compliant test suite for '{requirement.key}' "
                        f"after {self.max_retries + 1} attempts. Last error: {last_error}"
                    ) from exc

        raise TestDesignError("Unexpected termination of test generation loop.")

    def _generate_suite_incremental(
        self,
        requirement: JiraRequirement,
        base_url: str,
        progress_callback: Any,
    ) -> TestSuite:
        """
        Synthesizes test cases incrementally for each Acceptance Criterion,
        reporting live progress to the caller.
        """
        acs = requirement.acceptance_criteria or [AcceptanceCriterion(id="AC-01", text=requirement.summary.strip())]
        total = len(acs)
        test_cases: List[TestCase] = []

        for idx, ac in enumerate(acs, start=1):
            progress_callback(idx, total, f"Synthesizing Scenario {idx}/{total}: [{ac.id}] {ac.text[:35]}...")
            tc_prompt = format_single_ac_prompt(
                requirement=requirement,
                ac=ac,
                tc_index=idx,
                total_acs=total,
                target_base_url=base_url,
            )

            tc_obj: Optional[TestCase] = None
            try:
                res = self.llm.generate(
                    prompt=tc_prompt,
                    system_prompt=SYSTEM_TEST_DESIGNER_PROMPT,
                    json_mode=True,
                )
                data = res.parse_json()
                if "test_case" in data and isinstance(data["test_case"], dict):
                    data = data["test_case"]
                data.setdefault("id", f"TC-{idx:02d}")
                data.setdefault("requirement_key", requirement.key)
                data.setdefault("source_ac_id", ac.id)
                tc_obj = TestCase.model_validate(data)
            except Exception as err:
                logger.warning("Single AC generation failed for %s: %s. Using resilient fallback.", ac.id, err)
                ac_lower = ac.text.lower()
                is_neg = any(w in ac_lower for w in ["invalid", "without", "missing", "error", "exceed", "blank", "cannot", "fail", "reject", "negative", "boundary", "mandatory", "zero", "limit"])
                if is_neg:
                    if any(k in ac_lower for k in ["quantity", "exceed", "limit", "max", "500"]):
                        steps = [
                            TestStep(step_number=1, action=ActionType.NAVIGATE, input_value=f"{base_url}/", description="Open SAP screen"),
                            TestStep(step_number=2, action=ActionType.FILL, locator_strategy=LocatorStrategy.TEST_ID, selector_value="customer-id-input", input_value="CUST-3001", description="Enter valid customer ID"),
                            TestStep(step_number=3, action=ActionType.SELECT_OPTION, locator_strategy=LocatorStrategy.TEST_ID, selector_value="material-select", input_value="MAT-1001", description="Select material from catalog"),
                            TestStep(step_number=4, action=ActionType.FILL, locator_strategy=LocatorStrategy.TEST_ID, selector_value="quantity-input", input_value="999", description="Enter quantity exceeding limit of 500"),
                            TestStep(step_number=5, action=ActionType.CLICK, locator_strategy=LocatorStrategy.TEST_ID, selector_value="submit-order-button", description="Submit form"),
                            TestStep(step_number=6, action=ActionType.ASSERT_TEXT, locator_strategy=LocatorStrategy.TEST_ID, selector_value="error-banner", expected_value="Validation Error", description="Verify quantity limit error banner"),
                        ]
                    elif any(k in ac_lower for k in ["zero", "negative", "positive integer", "<="]):
                        steps = [
                            TestStep(step_number=1, action=ActionType.NAVIGATE, input_value=f"{base_url}/", description="Open SAP screen"),
                            TestStep(step_number=2, action=ActionType.FILL, locator_strategy=LocatorStrategy.TEST_ID, selector_value="customer-id-input", input_value="CUST-3001", description="Enter valid customer ID"),
                            TestStep(step_number=3, action=ActionType.SELECT_OPTION, locator_strategy=LocatorStrategy.TEST_ID, selector_value="material-select", input_value="MAT-1001", description="Select material from catalog"),
                            TestStep(step_number=4, action=ActionType.FILL, locator_strategy=LocatorStrategy.TEST_ID, selector_value="quantity-input", input_value="0", description="Enter zero quantity"),
                            TestStep(step_number=5, action=ActionType.CLICK, locator_strategy=LocatorStrategy.TEST_ID, selector_value="submit-order-button", description="Submit form"),
                            TestStep(step_number=6, action=ActionType.ASSERT_TEXT, locator_strategy=LocatorStrategy.TEST_ID, selector_value="error-banner", expected_value="Validation Error", description="Verify positive integer error banner"),
                        ]
                    elif any(k in ac_lower for k in ["material", "catalog"]):
                        steps = [
                            TestStep(step_number=1, action=ActionType.NAVIGATE, input_value=f"{base_url}/", description="Open SAP screen"),
                            TestStep(step_number=2, action=ActionType.FILL, locator_strategy=LocatorStrategy.TEST_ID, selector_value="customer-id-input", input_value="CUST-3001", description="Enter valid customer ID"),
                            TestStep(step_number=3, action=ActionType.FILL, locator_strategy=LocatorStrategy.TEST_ID, selector_value="quantity-input", input_value="5", description="Enter quantity"),
                            TestStep(step_number=4, action=ActionType.CLICK, locator_strategy=LocatorStrategy.TEST_ID, selector_value="submit-order-button", description="Submit form without material"),
                            TestStep(step_number=5, action=ActionType.ASSERT_TEXT, locator_strategy=LocatorStrategy.TEST_ID, selector_value="error-banner", expected_value="Validation Error", description="Verify material selection error banner"),
                        ]
                    else:
                        steps = [
                            TestStep(step_number=1, action=ActionType.NAVIGATE, input_value=f"{base_url}/", description="Open SAP screen"),
                            TestStep(step_number=2, action=ActionType.FILL, locator_strategy=LocatorStrategy.TEST_ID, selector_value="customer-id-input", input_value="", description="Leave customer ID empty"),
                            TestStep(step_number=3, action=ActionType.SELECT_OPTION, locator_strategy=LocatorStrategy.TEST_ID, selector_value="material-select", input_value="MAT-1001", description="Select material from catalog"),
                            TestStep(step_number=4, action=ActionType.FILL, locator_strategy=LocatorStrategy.TEST_ID, selector_value="quantity-input", input_value="5", description="Enter quantity"),
                            TestStep(step_number=5, action=ActionType.CLICK, locator_strategy=LocatorStrategy.TEST_ID, selector_value="submit-order-button", description="Submit form"),
                            TestStep(step_number=6, action=ActionType.ASSERT_TEXT, locator_strategy=LocatorStrategy.TEST_ID, selector_value="error-banner", expected_value="Validation Error", description="Verify mandatory customer ID error banner"),
                        ]
                else:
                    req_corpus = (requirement.summary.lower() + " " + ac_lower)
                    target_url = base_url if ("nodomain.com" in base_url or "44325" in base_url) else settings.sap_fiori_url
                    if any(k in req_corpus for k in ["e2e", "create", "header", "sold-to", "party", "customer", "zqds", "hospital", "quotation", "service quotation", "rar"]):
                        # 1. Parameterized Flow Reusability: Check for recorded golden flow in library
                        flow_steps = []
                        try:
                            from app.storage.repository import get_reusable_flow_steps
                            flow_steps = get_reusable_flow_steps("SAP RAR - Service Quotation End-to-End Flow")
                            if not flow_steps:
                                flow_steps = get_reusable_flow_steps("Recorded: Create Service quotation")
                        except Exception:
                            flow_steps = []

                        if flow_steps and len(flow_steps) >= 15:
                            desc_val = "RAR"
                            m_desc = re.search(r"description\s*(?:as|is|:)?\s*([a-zA-Z0-9_\-]+)", req_corpus)
                            if m_desc:
                                desc_val = m_desc.group(1).upper()

                            soldto_val = "Brugmann Hospital"
                            m_soldto = re.search(r"sold-to\s*party\s*(?:as|is|:)?\s*([a-zA-Z0-9_\-\s]+?)(?:and|\.|\n|$)", req_corpus)
                            if m_soldto:
                                soldto_val = m_soldto.group(1).strip()

                            prod_val = "45157510101"
                            m_prod = re.search(r"(?:product\s*id|product)\s*(?:as|is|:)?\s*([0-9]{5,})", req_corpus)
                            if m_prod:
                                prod_val = m_prod.group(1)

                            qty_val = "1"
                            m_qty = re.search(r"(\d+)\s*quantity|quantity\s*(?:as|is|:)?\s*(\d+)", req_corpus)
                            if m_qty:
                                qty_val = m_qty.group(1) or m_qty.group(2)

                            steps = []
                            for stp in flow_steps:
                                stp_dict = stp.model_dump()
                                sel = (stp_dict.get("selector_value") or "").lower()
                                if "description" in sel:
                                    stp_dict["input_value"] = desc_val
                                    stp_dict["description"] = f"Enter Quotation Description '{desc_val}'"
                                elif "sold-to" in sel:
                                    if stp_dict.get("input_value") != "Enter":
                                        stp_dict["input_value"] = soldto_val
                                        stp_dict["description"] = f"Enter Sold-to Party '{soldto_val}'"
                                elif "ordered_prod" in sel:
                                    stp_dict["input_value"] = prod_val
                                    stp_dict["description"] = f"Enter Product ID '{prod_val}'"
                                elif "quantity" in sel:
                                    if stp_dict.get("input_value") != "Enter":
                                        stp_dict["input_value"] = qty_val
                                        stp_dict["description"] = f"Enter Quantity '{qty_val}'"
                                steps.append(TestStep.model_validate(stp_dict))

                            has_logout = any("sign out" in (s.description or "").lower() for s in steps)
                            if not has_logout:
                                logout_steps = [
                                    TestStep(step_number=len(steps)+1, action=ActionType.CLICK, locator_strategy=LocatorStrategy.CSS, selector_value="#userActionsMenuHeaderButton, #meAreaHeaderButton", description="Click User Profile Avatar Menu"),
                                    TestStep(step_number=len(steps)+2, action=ActionType.CLICK, locator_strategy=LocatorStrategy.CSS, selector_value="button:has-text('Sign Out'), #logoutBtn", description="Click Sign Out"),
                                    TestStep(step_number=len(steps)+3, action=ActionType.CLICK, locator_strategy=LocatorStrategy.CSS, selector_value="button:has-text('OK'), #logoutConfirm", description="Confirm Sign Out dialog"),
                                    TestStep(step_number=len(steps)+4, action=ActionType.ASSERT_TEXT, locator_strategy=LocatorStrategy.CSS, selector_value="body", expected_value="logged off", description="Verify returned to Logoff screen"),
                                ]
                                steps.extend(logout_steps)
                            for idx, s in enumerate(steps, 1):
                                s.step_number = idx
                        else:
                            steps = [
                                TestStep(step_number=1, action=ActionType.NAVIGATE, input_value=target_url, description="Open SAP Fiori Logon screen"),
                                TestStep(step_number=2, action=ActionType.FILL, locator_strategy=LocatorStrategy.CSS, selector_value="#USERNAME_FIELD-inner", input_value=(settings.sap_username or "MYRAR1").strip(), description="Enter SAP username"),
                                TestStep(step_number=3, action=ActionType.FILL, locator_strategy=LocatorStrategy.CSS, selector_value="#PASSWORD_FIELD-inner", input_value=(settings.sap_password or "Pass23#$").strip(), description="Enter SAP password"),
                                TestStep(step_number=4, action=ActionType.CLICK, locator_strategy=LocatorStrategy.CSS, selector_value="#LOGIN_LINK", description="Click Log On button"),
                                TestStep(step_number=5, action=ActionType.ASSERT_TEXT, locator_strategy=LocatorStrategy.CSS, selector_value="body", expected_value="Home", description="Assert SAP Fiori Launchpad loaded"),
                                TestStep(step_number=6, action=ActionType.CLICK, locator_strategy=LocatorStrategy.TEXT, selector_value="Manage Service Quotations", description="Click Manage Service Quotations tile"),
                                TestStep(step_number=7, action=ActionType.CLICK, locator_strategy=LocatorStrategy.CSS, selector_value="button:has-text('New Create'), button:has-text('Create'), [title*='Create'], #btnCreate", description="Click Create button on Service Quotations worklist"),
                                TestStep(step_number=8, action=ActionType.CLICK, locator_strategy=LocatorStrategy.TEXT, selector_value="ZQDS", description="Select Transaction Type ZQDS (CE-Direct Sales) from popup"),
                                TestStep(step_number=9, action=ActionType.FILL, locator_strategy=LocatorStrategy.ROLE, role_name="textbox", selector_value="Description:", input_value="RAR", description="Enter Quotation Description"),
                                TestStep(step_number=10, action=ActionType.FILL, locator_strategy=LocatorStrategy.ROLE, role_name="textbox", selector_value="Sold-To Party:", input_value="Brugmann Hospital", description="Enter Sold-to Party customer"),
                                TestStep(step_number=11, action=ActionType.CLICK, locator_strategy=LocatorStrategy.ROLE, role_name="option", selector_value="Dates", description="Open Dates tab"),
                                TestStep(step_number=12, action=ActionType.FILL, locator_strategy=LocatorStrategy.CSS, selector_value="#C16_W64_V65_DatesTable_bottom_div tr:has-text('Term of Quotation') input, #C16_W64_V65_DatesTable_bottom_div tr:has-text('Term of Quotation') [role='textbox']", input_value="1", description="Go to Term of Quotation and enter Duration as 1"),
                                TestStep(step_number=13, action=ActionType.CLICK, locator_strategy=LocatorStrategy.ROLE, role_name="option", selector_value="Items", description="Open Items tab"),
                                TestStep(step_number=14, action=ActionType.FILL, locator_strategy=LocatorStrategy.CSS, selector_value="[id*='ordered_prod'], input[id*='ordered_prod']", input_value="45157510101", description="Enter Product ID 45157510101"),
                                TestStep(step_number=15, action=ActionType.FILL, locator_strategy=LocatorStrategy.CSS, selector_value="[id*='quantity'], input[id*='quantity']", input_value="1", description="Enter Quantity 1"),
                                TestStep(step_number=16, action=ActionType.CLICK, locator_strategy=LocatorStrategy.TEXT, selector_value="VELLYS SATELLITE STATION SKU1", description="Click on product name to view item details"),
                                TestStep(step_number=17, action=ActionType.CLICK, locator_strategy=LocatorStrategy.ROLE, role_name="option", selector_value="Price Details", description="Click Price Details tab"),
                                TestStep(step_number=18, action=ActionType.CLICK, locator_strategy=LocatorStrategy.ROLE, role_name="button", selector_value="Add", description="Click Add Pricing Element button"),
                                TestStep(step_number=19, action=ActionType.CLICK, locator_strategy=LocatorStrategy.TEXT, selector_value="ZTAF", description="Select condition type ZTAF from popup"),
                                TestStep(step_number=20, action=ActionType.CLICK, locator_strategy=LocatorStrategy.ROLE, role_name="button", selector_value="Back", description="Click Back to return to quotation"),
                                TestStep(step_number=21, action=ActionType.CLICK, locator_strategy=LocatorStrategy.ROLE, role_name="button", selector_value="Save (Ctrl+S)", description="Click Save button to persist quotation"),
                                TestStep(step_number=22, action=ActionType.CLICK, locator_strategy=LocatorStrategy.CSS, selector_value="#thtmlbOverviewPageBox tr button[aria-label='Edit'], #thtmlbOverviewPageBox tr [title='Edit'], button:has-text('Edit')", description="Click Edit button"),
                                TestStep(step_number=23, action=ActionType.CLICK, locator_strategy=LocatorStrategy.CSS, selector_value="#C9_W36_V39_V40_btadminh_lcstatus-btn, [id*='btadminh_lcstatus-btn']", description="Open Lifecycle Status dropdown"),
                                TestStep(step_number=24, action=ActionType.CLICK, locator_strategy=LocatorStrategy.ROLE, role_name="link", selector_value="Released", description="Change status to Released"),
                                TestStep(step_number=25, action=ActionType.CLICK, locator_strategy=LocatorStrategy.ROLE, role_name="button", selector_value="Save (Ctrl+S)", description="Click Save button again"),
                                TestStep(step_number=26, action=ActionType.CLICK, locator_strategy=LocatorStrategy.CSS, selector_value="#C9_W36_V39_thtmlb_menuButton_27_span-wrap, button:has-text('More')", description="Click More actions"),
                                TestStep(step_number=27, action=ActionType.CLICK, locator_strategy=LocatorStrategy.ROLE, role_name="menuitem", selector_value="List Item. Is Active. Accept", description="Click Accept button"),
                                TestStep(step_number=28, action=ActionType.CLICK, locator_strategy=LocatorStrategy.CSS, selector_value="#userActionsMenuHeaderButton, #meAreaHeaderButton", description="Click User Profile Avatar Menu"),
                                TestStep(step_number=29, action=ActionType.CLICK, locator_strategy=LocatorStrategy.CSS, selector_value="button:has-text('Sign Out'), #logoutBtn", description="Click Sign Out"),
                                TestStep(step_number=30, action=ActionType.CLICK, locator_strategy=LocatorStrategy.CSS, selector_value="button:has-text('OK'), #logoutConfirm", description="Confirm Sign Out dialog"),
                                TestStep(step_number=31, action=ActionType.ASSERT_TEXT, locator_strategy=LocatorStrategy.CSS, selector_value="body", expected_value="logged off", description="Verify returned to Logoff screen"),
                            ]
                    elif any(k in ac_lower for k in ["item", "product", "quantity", "45157510101"]):
                        steps = [
                            TestStep(step_number=1, action=ActionType.CLICK, locator_strategy=LocatorStrategy.ROLE, role_name="option", selector_value="Items", description="Open Items tab"),
                            TestStep(step_number=2, action=ActionType.FILL, locator_strategy=LocatorStrategy.CSS, selector_value="[id*='ordered_prod'], input[id*='ordered_prod']", input_value="45157510101", description="Enter Product ID 45157510101"),
                            TestStep(step_number=3, action=ActionType.FILL, locator_strategy=LocatorStrategy.CSS, selector_value="[id*='quantity'], input[id*='quantity']", input_value="1", description="Enter Quantity 1"),
                            TestStep(step_number=4, action=ActionType.ASSERT_TEXT, locator_strategy=LocatorStrategy.CSS, selector_value="body", expected_value="45157510101", description="Assert product added to quotation line items"),
                        ]
                    elif any(k in ac_lower for k in ["price", "pricing", "ztaf", "condition"]):
                        steps = [
                            TestStep(step_number=1, action=ActionType.CLICK, locator_strategy=LocatorStrategy.TEXT, selector_value="Price Details", description="Click Price Details tab"),
                            TestStep(step_number=2, action=ActionType.ASSERT_TEXT, locator_strategy=LocatorStrategy.CSS, selector_value="body", expected_value="ZTAF", description="Verify condition type ZTAF present in pricing elements"),
                        ]
                    elif any(k in ac_lower for k in ["save", "release", "accept", "persist"]):
                        steps = [
                            TestStep(step_number=1, action=ActionType.CLICK, locator_strategy=LocatorStrategy.CSS, selector_value="button:has-text('Save'), #btnSave", description="Click Save button to persist quotation"),
                            TestStep(step_number=2, action=ActionType.ASSERT_TEXT, locator_strategy=LocatorStrategy.CSS, selector_value="body", expected_value="saved", description="Verify quotation saved successfully with confirmation"),
                            TestStep(step_number=3, action=ActionType.CLICK, locator_strategy=LocatorStrategy.CSS, selector_value="button:has-text('Release')", description="Click Release button"),
                            TestStep(step_number=4, action=ActionType.CLICK, locator_strategy=LocatorStrategy.CSS, selector_value="button:has-text('Accept')", description="Click Accept button"),
                            TestStep(step_number=5, action=ActionType.ASSERT_TEXT, locator_strategy=LocatorStrategy.CSS, selector_value="body", expected_value="Accepted", description="Verify quotation status is updated to Accepted"),
                        ]
                    elif any(k in ac_lower for k in ["duration", "date", "term"]):
                        steps = [
                            TestStep(step_number=1, action=ActionType.CLICK, locator_strategy=LocatorStrategy.TEXT, selector_value="Dates", description="Open Dates and Duration tab"),
                            TestStep(step_number=2, action=ActionType.ASSERT_TEXT, locator_strategy=LocatorStrategy.CSS, selector_value="body", expected_value="Valid To", description="Verify duration and validity dates section displayed"),
                        ]
                    elif any(k in ac_lower for k in ["tile", "worklist", "manage service"]):
                        steps = [
                            TestStep(step_number=1, action=ActionType.NAVIGATE, input_value=target_url, description="Open SAP Fiori Logon screen"),
                            TestStep(step_number=2, action=ActionType.FILL, locator_strategy=LocatorStrategy.CSS, selector_value="#USERNAME_FIELD-inner", input_value=(settings.sap_username or "MYRAR1").strip(), description="Enter SAP username"),
                            TestStep(step_number=3, action=ActionType.FILL, locator_strategy=LocatorStrategy.CSS, selector_value="#PASSWORD_FIELD-inner", input_value=(settings.sap_password or "Pass23#$").strip(), description="Enter SAP password"),
                            TestStep(step_number=4, action=ActionType.CLICK, locator_strategy=LocatorStrategy.CSS, selector_value="#LOGIN_LINK", description="Click Log On button"),
                            TestStep(step_number=5, action=ActionType.ASSERT_TEXT, locator_strategy=LocatorStrategy.CSS, selector_value="body", expected_value="Home", description="Assert SAP Fiori Launchpad loaded"),
                            TestStep(step_number=6, action=ActionType.CLICK, locator_strategy=LocatorStrategy.TEXT, selector_value="Manage Service Quotations", description="Click Manage Service Quotations tile"),
                            TestStep(step_number=7, action=ActionType.ASSERT_TEXT, locator_strategy=LocatorStrategy.CSS, selector_value="body", expected_value="Service Quotations", description="Verify Service Quotations screen loaded"),
                        ]
                    elif any(k in req_corpus for k in ["login", "logon", "logout", "sign out", "sign in", "authenticate"]):
                        steps = [
                            TestStep(step_number=1, action=ActionType.NAVIGATE, input_value=target_url, description="Open SAP Fiori Logon screen"),
                            TestStep(step_number=2, action=ActionType.FILL, locator_strategy=LocatorStrategy.CSS, selector_value="#USERNAME_FIELD-inner", input_value=(settings.sap_username or "MYRAR1").strip(), description="Enter SAP username"),
                            TestStep(step_number=3, action=ActionType.FILL, locator_strategy=LocatorStrategy.CSS, selector_value="#PASSWORD_FIELD-inner", input_value=(settings.sap_password or "Pass23#$").strip(), description="Enter SAP password"),
                            TestStep(step_number=4, action=ActionType.CLICK, locator_strategy=LocatorStrategy.CSS, selector_value="#LOGIN_LINK", description="Click Log On button"),
                            TestStep(step_number=5, action=ActionType.ASSERT_TEXT, locator_strategy=LocatorStrategy.CSS, selector_value="body", expected_value="Home", description="Assert SAP Fiori Launchpad loaded"),
                            TestStep(step_number=6, action=ActionType.WAIT_FOR, input_value="20s", description="Wait for 20 seconds on Launchpad"),
                            TestStep(step_number=7, action=ActionType.CLICK, locator_strategy=LocatorStrategy.CSS, selector_value="#userActionsMenuHeaderButton, #meAreaHeaderButton", description="Click User Profile Avatar Menu"),
                            TestStep(step_number=8, action=ActionType.CLICK, locator_strategy=LocatorStrategy.TEXT, selector_value="Sign Out", description="Click Sign Out"),
                            TestStep(step_number=9, action=ActionType.CLICK, locator_strategy=LocatorStrategy.TEXT, selector_value="OK", description="Confirm Sign Out dialog"),
                            TestStep(step_number=10, action=ActionType.ASSERT_TEXT, locator_strategy=LocatorStrategy.CSS, selector_value="body", expected_value="logged off", description="Verify returned to Logoff screen"),
                        ]
                    else:
                        steps = [
                            TestStep(step_number=1, action=ActionType.NAVIGATE, input_value=f"{base_url}/", description="Open SAP screen"),
                            TestStep(step_number=2, action=ActionType.FILL, locator_strategy=LocatorStrategy.TEST_ID, selector_value="customer-id-input", input_value="CUST-3001", description="Enter customer ID"),
                            TestStep(step_number=3, action=ActionType.FILL, locator_strategy=LocatorStrategy.TEST_ID, selector_value="customer-name-input", input_value="Acme Industrial Corp", description="Enter customer name"),
                            TestStep(step_number=4, action=ActionType.SELECT_OPTION, locator_strategy=LocatorStrategy.TEST_ID, selector_value="material-select", input_value="MAT-1001", description="Select material from catalog"),
                            TestStep(step_number=5, action=ActionType.FILL, locator_strategy=LocatorStrategy.TEST_ID, selector_value="quantity-input", input_value="5", description="Enter quantity"),
                            TestStep(step_number=6, action=ActionType.CLICK, locator_strategy=LocatorStrategy.TEST_ID, selector_value="submit-order-button", description="Submit form"),
                            TestStep(step_number=7, action=ActionType.ASSERT_TEXT, locator_strategy=LocatorStrategy.TEST_ID, selector_value="success-banner", expected_value="created successfully", description="Verify order confirmation"),
                        ]

                tc_obj = TestCase(
                    id=f"TC-{idx:02d}",
                    requirement_key=requirement.key,
                    source_ac_id=ac.id,
                    title=f"Validate {ac.id}: {ac.text[:40]}",
                    objective=f"Verify behavior for {ac.text}",
                    category=TestCategory.NEGATIVE if is_neg else TestCategory.POSITIVE,
                    steps=steps,
                    expected_result=f"System response matches criteria for [{ac.id}]",
                )

            normalized_tc = self._enforce_sap_lifecycle(tc_obj, base_url, requirement)
            test_cases.append(normalized_tc)
            progress_callback(idx, total, f"Completed Scenario {idx}/{total}: {normalized_tc.title} [Done]")

        return TestSuite(
            suite_id=f"SUITE-{requirement.key}",
            requirement_key=requirement.key,
            version=1,
            test_cases=test_cases,
        )

    @classmethod
    def _enforce_sap_lifecycle(
        cls,
        tc: TestCase,
        base_url: str,
        requirement: Optional[JiraRequirement] = None,
    ) -> TestCase:
        """
        Enforces that any SAP test case deterministically:
        1. Begins with full login steps (Navigate, Username, Password, Login button, Assert Launchpad Home).
        2. Preserves the core business functionality.
        3. Terminates with full logoff steps (Avatar Menu, Sign Out, Confirm OK, Assert logged off).
        4. Sequentially re-indexes all step_numbers from 1 to N.
        """
        # First ensure initial navigate is present and valid
        tc = cls._ensure_initial_navigate(tc, base_url)

        req_corpus = ""
        if requirement:
            req_corpus = f"{requirement.summary} {requirement.description_text}".lower()

        tc_corpus = (
            f"{base_url} {tc.title} {tc.objective} {req_corpus} " +
            " ".join(s.description or "" for s in tc.steps) + " " +
            " ".join(s.selector_value or "" for s in tc.steps)
        ).lower()

        is_sap = any(
            k in tc_corpus
            for k in [
                "sap", "fiori", "s/4hana", "saps4hana", "44325", "nodomain.com",
                "rar", "service quotation", "username_field", "login_link",
                "meareaheaderbutton", "useractionsmenu"
            ]
        )

        has_login_step = any(
            any(k in (s.description or "").lower() for k in ["login", "log in", "logon", "log on", "authenticate"]) or
            any(k in (s.selector_value or "").lower() for k in ["username_field", "password_field", "login_link"])
            for s in tc.steps
        )

        if not (is_sap or has_login_step):
            return tc

        # If it's a negative authentication test case specifically testing invalid credentials, do not overwrite
        if tc.category == TestCategory.NEGATIVE and any(k in (tc.title + " " + tc.objective).lower() for k in ["invalid cred", "wrong password", "bad credential", "unauthorized"]):
            return tc

        sap_url = base_url if ("nodomain.com" in base_url or "44325" in base_url or "sap" in base_url.lower()) else settings.sap_fiori_url
        if not sap_url:
            sap_url = settings.sap_fiori_url

        sap_user = (settings.sap_username or "MYRAR1").strip()
        sap_pwd = (settings.sap_password or "Pass23#$").strip()

        steps = list(tc.steps)

        # ----------------------------------------------------------------------
        # PART 1: ENSURE FULL LOGIN STEPS AT BEGINNING (DEDUPLICATED)
        # ----------------------------------------------------------------------
        standard_login_steps = [
            TestStep(
                step_number=1,
                action=ActionType.NAVIGATE,
                input_value=sap_url,
                description="Open SAP Fiori Logon screen",
            ),
            TestStep(
                step_number=2,
                action=ActionType.FILL,
                locator_strategy=LocatorStrategy.CSS,
                selector_value="#USERNAME_FIELD-inner",
                input_value=sap_user,
                description="Enter SAP username",
            ),
            TestStep(
                step_number=3,
                action=ActionType.FILL,
                locator_strategy=LocatorStrategy.CSS,
                selector_value="#PASSWORD_FIELD-inner",
                input_value=sap_pwd,
                description="Enter SAP password",
            ),
            TestStep(
                step_number=4,
                action=ActionType.CLICK,
                locator_strategy=LocatorStrategy.CSS,
                selector_value="#LOGIN_LINK",
                description="Click Log On button",
            ),
            TestStep(
                step_number=5,
                action=ActionType.ASSERT_TEXT,
                locator_strategy=LocatorStrategy.CSS,
                selector_value="body",
                expected_value="Home",
                description="Assert SAP Fiori Launchpad loaded",
            ),
        ]

        def is_leading_login_step(s: TestStep) -> bool:
            act = s.action
            s_val = (s.selector_value or "").lower()
            s_desc = (s.description or "").lower()
            s_role = (s.role_name or "").lower()
            s_exp = (s.expected_value or "").lower()

            if act == ActionType.NAVIGATE:
                return True

            if act == ActionType.FILL and (
                any(k in s_val for k in ["username", "user", "sap-user", "login"]) or
                any(k in s_val for k in ["password", "pwd", "pass", "sap-password"]) or
                any(k in s_desc for k in ["user", "username", "password", "pwd", "credential"]) or
                (s_role == "textbox" and any(k in s_val for k in ["user", "password"]))
            ):
                return True

            if act == ActionType.CLICK and (
                any(k in s_val for k in ["login_link", "log on", "logon", "login", "submit", "sign in", "signin"]) or
                any(k in s_desc for k in ["log on", "logon", "login", "sign in"]) or
                (s_role == "button" and any(k in s_val for k in ["log on", "logon", "login"]))
            ):
                return True

            if act == ActionType.ASSERT_TEXT and (
                (s_val in ["body", "html", "#shell"] and any(k in s_exp for k in ["home", "launchpad"])) or
                "launchpad" in s_desc
            ):
                return True

            return False

        idx_start = 0
        while idx_start < len(steps) and is_leading_login_step(steps[idx_start]):
            idx_start += 1

        remaining_functional = steps[idx_start:]
        functional_steps = list(standard_login_steps) + remaining_functional

        # ----------------------------------------------------------------------
        # PART 2: ENSURE FULL LOGOFF STEPS AT THE END
        # ----------------------------------------------------------------------
        last_4_steps = functional_steps[-4:] if len(functional_steps) >= 4 else functional_steps
        has_logoff_end = False
        for s in last_4_steps:
            s_desc = (s.description or "").lower()
            s_sel = (s.selector_value or "").lower()
            s_exp = (s.expected_value or "").lower()
            if any(k in s_desc or k in s_sel for k in ["sign out", "logout", "logoff", "log out", "log off"]) or \
               any(k in s_exp for k in ["logged off", "signed out", "logoff", "logout"]):
                has_logoff_end = True
                break

        standard_logoff_steps = [
            TestStep(
                step_number=901,
                action=ActionType.CLICK,
                locator_strategy=LocatorStrategy.CSS,
                selector_value="#userActionsMenuHeaderButton, #meAreaHeaderButton",
                description="Click User Profile Avatar Menu",
            ),
            TestStep(
                step_number=902,
                action=ActionType.CLICK,
                locator_strategy=LocatorStrategy.CSS,
                selector_value="button:has-text('Sign Out'), text='Sign Out'",
                description="Click Sign Out",
            ),
            TestStep(
                step_number=903,
                action=ActionType.CLICK,
                locator_strategy=LocatorStrategy.CSS,
                selector_value="button:has-text('OK'), text='OK'",
                description="Confirm Sign Out dialog",
            ),
            TestStep(
                step_number=904,
                action=ActionType.ASSERT_TEXT,
                locator_strategy=LocatorStrategy.CSS,
                selector_value="body",
                expected_value="logged off",
                description="Verify returned to Logoff screen",
            ),
        ]

        if not has_logoff_end:
            final_steps_list = functional_steps + standard_logoff_steps
        else:
            final_steps_list = []
            for s in functional_steps:
                s_copy = s.model_copy()
                if "meAreaHeaderButton" in (s.selector_value or "") and "userActionsMenuHeaderButton" not in (s.selector_value or ""):
                    s_copy = s.model_copy(update={"selector_value": "#userActionsMenuHeaderButton, #meAreaHeaderButton"})
                final_steps_list.append(s_copy)

        # ----------------------------------------------------------------------
        # PART 3: RE-NUMBER ALL STEPS SEQUENTIALLY 1 to N
        # ----------------------------------------------------------------------
        renumbered_steps = []
        for i, step in enumerate(final_steps_list, start=1):
            renumbered_steps.append(step.model_copy(update={"step_number": i}))

        return tc.model_copy(update={"steps": renumbered_steps})

    @staticmethod
    def _ensure_initial_navigate(tc: TestCase, base_url: str) -> TestCase:
        """Ensures every test case begins with a deterministic navigate step to base_url."""
        target_url = base_url if ("?" in base_url or "#" in base_url) else base_url.rstrip("/") + "/"
        steps = list(tc.steps)
        if not steps or steps[0].action != ActionType.NAVIGATE:
            nav_step = TestStep(
                step_number=1,
                action=ActionType.NAVIGATE,
                input_value=target_url,
                description=f"Navigate to {target_url}",
            )
            updated_steps = [nav_step]
            for i, step in enumerate(steps, start=2):
                s_dict = step.model_dump()
                s_dict["step_number"] = i
                updated_steps.append(TestStep.model_validate(s_dict))
            return tc.model_copy(update={"steps": updated_steps})

        # Ensure first step has a valid input_value URL
        if not steps[0].input_value or not str(steps[0].input_value).startswith("http"):
            steps[0] = steps[0].model_copy(update={"input_value": target_url})

        # Renumber sequentially
        updated_steps = []
        for i, step in enumerate(steps, start=1):
            if step.step_number != i:
                updated_steps.append(step.model_copy(update={"step_number": i}))
            else:
                updated_steps.append(step)
        return tc.model_copy(update={"steps": updated_steps})

