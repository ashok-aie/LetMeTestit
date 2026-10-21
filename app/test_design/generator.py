"""
Test Designer Module
Uses local Ollama LLM to synthesize Pydantic-validated TestSuites from JiraRequirements,
with bounded self-correction retries on schema violations.
"""
import re
import json
import time
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
                for i, tc in enumerate(normalized_tcs, start=1):
                    tc.id = f"TC-{i:02d}"
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
                data["id"] = f"TC-{idx:02d}"
                data.setdefault("requirement_key", requirement.key)
                data.setdefault("source_ac_id", ac.id)
                tc_obj = TestCase.model_validate(data)
                tc_obj.id = f"TC-{idx:02d}"
                if idx < total:
                    time.sleep(1.2)
            except Exception as err:
                logger.warning("Single AC generation failed for %s: %s. Using resilient fallback.", ac.id, err)
                ac_lower = ac.text.lower()
                req_corpus = (requirement.summary.lower() + " " + ac_lower)
                is_demo_app = ("127.0.0.1" in base_url or "localhost" in base_url or ":8000" in base_url)
                target_url = base_url if is_demo_app else (base_url if ("nodomain.com" in base_url or "44325" in base_url) else settings.sap_fiori_url)
                is_sap = not is_demo_app and (
                    "sap" in target_url.lower()
                    or "44325" in target_url
                    or "nodomain" in target_url
                    or any(k in req_corpus for k in ["sap", "fiori", "quotation", "service quotation", "zqds", "rar", "hospital"])
                )

                # Parameter extraction from requirement context
                combined_corpus = f"{requirement.summary} {requirement.description_text} {ac.text}"
                desc_val = "RAR Test"
                m_desc = re.search(r"description\s*(?:as|is|:)?\s*['\"]?([a-zA-Z0-9_\- ]+?)['\"]?(?:\n|\r|\d+\s+|sold-to|\s+and|\s+with|\.|$)", combined_corpus, re.IGNORECASE)
                if m_desc and m_desc.group(1).strip():
                    desc_val = m_desc.group(1).strip()

                soldto_val = "Brugmann Hospital"
                m_soldto = re.search(r"sold-to\s*(?:party)?\s*(?:as|is|:)?\s*['\"]?([^'\"\n\r,;]+?)['\"]?(?:\n|\r|;|\d+\s+|\s+and|\s+with|\s+press|\.|$)", combined_corpus, re.IGNORECASE)
                if m_soldto and m_soldto.group(1).strip():
                    soldto_val = m_soldto.group(1).strip()

                prod_val = "45157510101"
                m_prod = re.search(r"(?:product\s*id|product)\s*(?:as|is|:)?\s*['\"]?([0-9]{5,})['\"]?", combined_corpus, re.IGNORECASE)
                if m_prod and m_prod.group(1).strip():
                    prod_val = m_prod.group(1).strip()

                qty_val = "1"
                m_qty = re.search(r"quantity.*?(?:is|as|:|enter|\b)\s*([0-9]+)", combined_corpus, re.IGNORECASE)
                if m_qty:
                    qty_val = m_qty.group(1).strip()
                else:
                    m_qty2 = re.search(r"(\d+)\s*quantity", combined_corpus, re.IGNORECASE)
                    if m_qty2:
                        qty_val = m_qty2.group(1).strip()

                # Multi-product extraction: supports 1 or more line items
                raw_prod_ids = re.findall(r"(?:product\s*(?:id)?\s*(?:as|is|:)?\s*['\"]?([0-9]{5,})['\"]?|\b(4515[0-9]{7})\b)", combined_corpus, re.IGNORECASE)
                extracted_prods = []
                for p_tup in raw_prod_ids:
                    p = (p_tup[0] or p_tup[1]).strip()
                    if p and p not in extracted_prods and p not in ("8000000631", "44325"):
                        extracted_prods.append(p)

                if not extracted_prods:
                    extracted_prods = [prod_val]

                duration_val = "1"
                m_dur = re.search(r"(?:duration\s*(?:as|is|:)?\s*['\"]?(\d+)['\"]?|term\s*(?:of\s*quotation)?\s*.*?(\d+))", combined_corpus, re.IGNORECASE)
                if m_dur:
                    duration_val = (m_dur.group(1) or m_dur.group(2)).strip()

                time_unit_val = "Year"
                m_tu = re.search(r"time\s*unit\s*(?:as|is|:)?\s*['\"]?([a-zA-Z]+)['\"]?", combined_corpus, re.IGNORECASE)
                if m_tu:
                    raw_tu = m_tu.group(1).strip()
                    time_unit_val = "Month" if "month" in raw_tu.lower() else ("Day" if "day" in raw_tu.lower() else "Year")

                pricing_val = "ZTAF"
                m_price = re.search(r"(?:pricing\s*element|condition\s*type|pricing)\s*(?:as|is|:)?\s*['\"]?([a-zA-Z0-9_\-]+)['\"]?", combined_corpus, re.IGNORECASE)
                if m_price and m_price.group(1).strip():
                    pricing_val = m_price.group(1).strip()

                ttype_val = "ZQDS"
                m_ttype = re.search(r"(?:transaction\s*type)\s*(?:as|is|:)?\s*['\"]?([a-zA-Z0-9_\-]+)['\"]?", combined_corpus, re.IGNORECASE)
                if m_ttype and m_ttype.group(1).strip():
                    ttype_val = m_ttype.group(1).strip()

                is_neg = any(w in ac_lower for w in ["invalid", "without", "missing", "error", "exceed", "blank", "cannot", "fail", "reject", "negative", "boundary", "zero", "limit"])

                if is_sap:
                    # Shared base steps: SAP Logon, Create Quotation, Header fields, Dates
                    base_quotation_steps = [
                        TestStep(step_number=1, action=ActionType.NAVIGATE, input_value=target_url, description="Open SAP Fiori Logon screen"),
                        TestStep(step_number=2, action=ActionType.FILL, locator_strategy=LocatorStrategy.CSS, selector_value="#USERNAME_FIELD-inner", input_value=(settings.sap_username or "MYRAR1").strip(), description="Enter SAP username"),
                        TestStep(step_number=3, action=ActionType.FILL, locator_strategy=LocatorStrategy.CSS, selector_value="#PASSWORD_FIELD-inner", input_value=(settings.sap_password or "Pass23#$").strip(), description="Enter SAP password"),
                        TestStep(step_number=4, action=ActionType.CLICK, locator_strategy=LocatorStrategy.CSS, selector_value="#LOGIN_LINK", description="Click Log On button"),
                        TestStep(step_number=5, action=ActionType.ASSERT_TEXT, locator_strategy=LocatorStrategy.CSS, selector_value="body", expected_value="Home", description="Assert SAP Fiori Launchpad loaded"),
                        TestStep(step_number=6, action=ActionType.CLICK, locator_strategy=LocatorStrategy.TEXT, selector_value="Manage Service Quotations", description="Click Manage Service Quotations tile"),
                        TestStep(step_number=7, action=ActionType.CLICK, locator_strategy=LocatorStrategy.CSS, selector_value="button:has-text('New Create'), button:has-text('Create'), [title*='Create'], #btnCreate", description="Click Create button on Service Quotations worklist"),
                        TestStep(step_number=8, action=ActionType.CLICK, locator_strategy=LocatorStrategy.TEXT, selector_value=ttype_val, description=f"Select Transaction Type {ttype_val} from popup"),
                        TestStep(step_number=9, action=ActionType.FILL, locator_strategy=LocatorStrategy.ROLE, role_name="textbox", selector_value="Description:", input_value=desc_val, description=f"Enter Quotation Description '{desc_val}'"),
                        TestStep(step_number=10, action=ActionType.FILL, locator_strategy=LocatorStrategy.ROLE, role_name="textbox", selector_value="Sold-To Party:", input_value=soldto_val, description=f"Enter Sold-to Party customer '{soldto_val}'"),
                        TestStep(step_number=11, action=ActionType.FILL, locator_strategy=LocatorStrategy.ROLE, role_name="textbox", selector_value="Sold-To Party:", input_value="Enter", description="Press Enter to commit Sold-to Party"),
                        TestStep(step_number=12, action=ActionType.CLICK, locator_strategy=LocatorStrategy.ROLE, role_name="option", selector_value="Dates", description="Open Dates tab"),
                        TestStep(step_number=13, action=ActionType.FILL, locator_strategy=LocatorStrategy.CSS, selector_value="#C16_W64_V65_DatesTable_bottom_div tr:has-text('Term of Quotation') input, #C16_W64_V65_DatesTable_bottom_div tr:has-text('Term of Quotation') [role='textbox']", input_value=duration_val, description=f"Enter Term of Quotation Duration as {duration_val}"),
                        TestStep(step_number=14, action=ActionType.CLICK, locator_strategy=LocatorStrategy.CSS, selector_value="[id='C16_W64_V65_btdate_table[4].time_unit-btn']", description="Open Time Unit dropdown"),
                        TestStep(step_number=15, action=ActionType.CLICK, locator_strategy=LocatorStrategy.ROLE, role_name="link", selector_value=time_unit_val, description=f"Select Time Unit {time_unit_val}"),
                        TestStep(step_number=16, action=ActionType.CLICK, locator_strategy=LocatorStrategy.ROLE, role_name="option", selector_value="Items", description="Open Items tab"),
                    ]

                    # Multi-product dynamic line item steps: 8 steps per product ID
                    cur_snum = 17
                    item_loop_steps = []
                    for idx, p_id in enumerate(extracted_prods, start=1):
                        item_loop_steps.extend([
                            TestStep(step_number=cur_snum, action=ActionType.FILL, locator_strategy=LocatorStrategy.CSS, selector_value=f"[id*='btadmini_table[{idx}].ordered_prod'], [id*='ordered_prod'], [id='C13_W49_V50_V54_btadmini_table[{idx}].ordered_prod']", input_value=p_id, description=f"Enter Product ID {p_id} for item {idx}"),
                            TestStep(step_number=cur_snum + 1, action=ActionType.FILL, locator_strategy=LocatorStrategy.CSS, selector_value=f"[id*='btadmini_table[{idx}].quantity'], [id*='quantity'], [id='C13_W49_V50_V54_btadmini_table[{idx}].quantity']", input_value=qty_val, description=f"Enter Quantity {qty_val} for item {idx}"),
                            TestStep(step_number=cur_snum + 2, action=ActionType.FILL, locator_strategy=LocatorStrategy.CSS, selector_value=f"[id*='btadmini_table[{idx}].quantity'], [id*='quantity'], [id='C13_W49_V50_V54_btadmini_table[{idx}].quantity']", input_value="Enter", description=f"Press Enter to commit line item {idx}"),
                            TestStep(step_number=cur_snum + 3, action=ActionType.CLICK, locator_strategy=LocatorStrategy.TEXT, selector_value="VELLYS SATELLITE STATION SKU1", description=f"Click Product Name to view item {idx} details"),
                            TestStep(step_number=cur_snum + 4, action=ActionType.CLICK, locator_strategy=LocatorStrategy.ROLE, role_name="option", selector_value="Price Details", description=f"Open Price Details tab for item {idx}"),
                            TestStep(step_number=cur_snum + 5, action=ActionType.CLICK, locator_strategy=LocatorStrategy.ROLE, role_name="button", selector_value="Add", description=f"Click Add Pricing Element button for item {idx}"),
                            TestStep(step_number=cur_snum + 6, action=ActionType.CLICK, locator_strategy=LocatorStrategy.TEXT, selector_value=pricing_val, description=f"Select condition type {pricing_val} from popup"),
                            TestStep(step_number=cur_snum + 7, action=ActionType.CLICK, locator_strategy=LocatorStrategy.ROLE, role_name="button", selector_value="Back", description=f"Click Back to return to quotation"),
                        ])
                        cur_snum += 8

                    # Lifecycle status: Save, Edit, Released, Save, Accept
                    lifecycle_steps = [
                        TestStep(step_number=cur_snum, action=ActionType.CLICK, locator_strategy=LocatorStrategy.ROLE, role_name="button", selector_value="Save (Ctrl+S)", description="Click Save button to persist quotation"),
                        TestStep(step_number=cur_snum + 1, action=ActionType.CLICK, locator_strategy=LocatorStrategy.CSS, selector_value="button:has-text('Edit'), a:has-text('Edit'), [title*='Edit'], [aria-label*='Edit']", description="Click Edit button"),
                        TestStep(step_number=cur_snum + 2, action=ActionType.CLICK, locator_strategy=LocatorStrategy.CSS, selector_value="#C9_W36_V39_V40_btadminh_lcstatus-btn, [id*='btadminh_lcstatus-btn']", description="Open Lifecycle Status dropdown"),
                        TestStep(step_number=cur_snum + 3, action=ActionType.CLICK, locator_strategy=LocatorStrategy.ROLE, role_name="link", selector_value="Released", description="Change status to Released"),
                        TestStep(step_number=cur_snum + 4, action=ActionType.CLICK, locator_strategy=LocatorStrategy.ROLE, role_name="button", selector_value="Save (Ctrl+S)", description="Click Save button to persist Released status"),
                        TestStep(step_number=cur_snum + 5, action=ActionType.CLICK, locator_strategy=LocatorStrategy.CSS, selector_value="button:has-text('Accept'), [title*='Accept'], a:has-text('Accept'), [role='menuitem']:has-text('Accept')", description="Click Accept quotation button"),
                    ]
                    cur_snum += 6

                    # SAP-Native Fallback Branches
                    if any(k in req_corpus for k in ["contract", "obligation", "pob", "operational document", "manage contracts", "accounting validation"]):
                        # Complete SAP RAR End-to-End Fallback (KAN-25): Capture Transaction History + Direct Navigation to Manage Revenue Contracts
                        mrc_url = "https://s4srv25.nodomain.com:44325/sap/bc/ui2/flp?sap-client=100&sap-language=EN#RevenueAccountingContract-manageContract&/?sap-iapp-state--history=TAS60ZN0APGEXK9SB8U7CWP0998E9ZTQEZ7DBW9FR"
                        rar_downstream_steps = [
                            TestStep(step_number=cur_snum, action=ActionType.CLICK, locator_strategy=LocatorStrategy.TEXT, selector_value="Transaction History", description="Click Transaction History tab"),
                            TestStep(step_number=cur_snum + 1, action=ActionType.ASSERT_TEXT, locator_strategy=LocatorStrategy.CSS, selector_value="body", expected_value="Transaction", description="Capture Operational Document / Transaction ID as test evidence"),
                            TestStep(step_number=cur_snum + 2, action=ActionType.NAVIGATE, input_value=mrc_url, description="Navigate directly to Manage Revenue Contracts application"),
                            TestStep(step_number=cur_snum + 3, action=ActionType.CLICK, locator_strategy=LocatorStrategy.CSS, selector_value="[id*='RevenueAccountingContract-vhi'], [id*='RevenueContract-vhi'], div:has(> label:has-text('Revenue Contract')) .sapMInputValHelpInner, label:has-text('Revenue Contract') ~ div .sapMInputValHelpInner, [id='fin.rar.manage.contract::sap.suite.ui.generic.template.ListReport.view.ListReport::C_RAContrWithPostedBalanceTP--listReportFilter-filterItemControl_BASIC-RevenueAccountingContract-vhi']", description="Click Revenue Accounting Contract Value Help"),
                            TestStep(step_number=cur_snum + 4, action=ActionType.FILL, locator_strategy=LocatorStrategy.ROLE, role_name="textbox", selector_value="Operational Document:", input_value="${OPERATIONAL_DOCUMENT}", description="Enter captured Operational Document into Operational Document:"),
                            TestStep(step_number=cur_snum + 5, action=ActionType.FILL, locator_strategy=LocatorStrategy.ROLE, role_name="textbox", selector_value="Operational Document:", input_value="Enter", description="Press 'Enter' into Operational Document:"),
                            TestStep(step_number=cur_snum + 6, action=ActionType.CLICK, locator_strategy=LocatorStrategy.TEXT, selector_value="Selection column", description="Click Selection column"),
                            TestStep(step_number=cur_snum + 7, action=ActionType.CLICK, locator_strategy=LocatorStrategy.ROLE, role_name="dialog", selector_value="Revenue Contract", description="Click Revenue Contract dialog"),
                            TestStep(step_number=cur_snum + 8, action=ActionType.CLICK, locator_strategy=LocatorStrategy.ROLE, role_name="button", selector_value="OK", description="Click OK"),
                            TestStep(step_number=cur_snum + 9, action=ActionType.CLICK, locator_strategy=LocatorStrategy.ROLE, role_name="button", selector_value="Go", description="Click Go"),
                            TestStep(step_number=cur_snum + 10, action=ActionType.ASSERT_TEXT, locator_strategy=LocatorStrategy.CSS, selector_value="body", expected_value="Revenue Contract", description="Verify Revenue Contract loaded"),
                            TestStep(step_number=cur_snum + 11, action=ActionType.CLICK, locator_strategy=LocatorStrategy.ROLE, role_name="button", selector_value="Avatar", description="Click User Profile Avatar Menu"),
                            TestStep(step_number=cur_snum + 12, action=ActionType.CLICK, locator_strategy=LocatorStrategy.ROLE, role_name="button", selector_value="Sign Out", description="Click Sign Out"),
                            TestStep(step_number=cur_snum + 13, action=ActionType.CLICK, locator_strategy=LocatorStrategy.ROLE, role_name="button", selector_value="OK", description="Confirm Sign Out dialog"),
                            TestStep(step_number=cur_snum + 14, action=ActionType.ASSERT_TEXT, locator_strategy=LocatorStrategy.CSS, selector_value="body", expected_value="logged off", description="Verify returned to Logoff screen"),
                        ]
                        steps = base_quotation_steps + item_loop_steps + lifecycle_steps + rar_downstream_steps
                    elif any(k in ac_lower for k in ["end-to-end", "e2e", "procedural flow", "business flow", "complete flow", "lifecycle"]) or (
                        any(k in req_corpus for k in ["quotation", "service quotation", "zqds"]) and
                        any(k in req_corpus for k in ["item", "product", "45157510101"]) and
                        any(k in req_corpus for k in ["dates", "term", "duration"]) and
                        any(k in req_corpus for k in ["price", "ztaf", "release", "accept"])
                    ):
                        # Complete SAP Service Quotation End-to-End Fallback (KAN-23)
                        sq_logout_steps = [
                            TestStep(step_number=cur_snum, action=ActionType.CLICK, locator_strategy=LocatorStrategy.CSS, selector_value="#userActionsMenuHeaderButton, #meAreaHeaderButton", description="Click User Profile Avatar Menu"),
                            TestStep(step_number=cur_snum + 1, action=ActionType.CLICK, locator_strategy=LocatorStrategy.CSS, selector_value="button:has-text('Sign Out'), #logoutBtn", description="Click Sign Out"),
                            TestStep(step_number=cur_snum + 2, action=ActionType.CLICK, locator_strategy=LocatorStrategy.CSS, selector_value="button:has-text('OK'), #logoutConfirm", description="Confirm Sign Out dialog"),
                            TestStep(step_number=cur_snum + 3, action=ActionType.ASSERT_TEXT, locator_strategy=LocatorStrategy.CSS, selector_value="body", expected_value="logged off", description="Verify returned to Logoff screen"),
                        ]
                        steps = base_quotation_steps + item_loop_steps + lifecycle_steps + sq_logout_steps
                    elif any(k in ac_lower for k in ["evidence", "number", "quotation number", "status", "document", "saved quotation"]) and not any(k in ac_lower for k in ["release", "accept"]):
                        steps = [
                            TestStep(step_number=1, action=ActionType.NAVIGATE, input_value=target_url, description="Open SAP Fiori Logon screen"),
                            TestStep(step_number=2, action=ActionType.FILL, locator_strategy=LocatorStrategy.CSS, selector_value="#USERNAME_FIELD-inner", input_value=(settings.sap_username or "MYRAR1").strip(), description="Enter SAP username"),
                            TestStep(step_number=3, action=ActionType.FILL, locator_strategy=LocatorStrategy.CSS, selector_value="#PASSWORD_FIELD-inner", input_value=(settings.sap_password or "Pass23#$").strip(), description="Enter SAP password"),
                            TestStep(step_number=4, action=ActionType.CLICK, locator_strategy=LocatorStrategy.CSS, selector_value="#LOGIN_LINK", description="Click Log On button"),
                            TestStep(step_number=5, action=ActionType.ASSERT_TEXT, locator_strategy=LocatorStrategy.CSS, selector_value="body", expected_value="Home", description="Assert SAP Fiori Launchpad loaded"),
                            TestStep(step_number=6, action=ActionType.CLICK, locator_strategy=LocatorStrategy.TEXT, selector_value="Manage Service Quotations", description="Click Manage Service Quotations tile"),
                            TestStep(step_number=7, action=ActionType.CLICK, locator_strategy=LocatorStrategy.ROLE, role_name="button", selector_value="Save (Ctrl+S)", description="Click Save button to persist quotation"),
                            TestStep(step_number=8, action=ActionType.ASSERT_TEXT, locator_strategy=LocatorStrategy.CSS, selector_value="body", expected_value="saved", description="Verify quotation saved confirmation in status bar"),
                            TestStep(step_number=9, action=ActionType.ASSERT_TEXT, locator_strategy=LocatorStrategy.CSS, selector_value="body", expected_value="Quotation", description="Capture saved quotation number and status as test evidence"),
                            TestStep(step_number=10, action=ActionType.CLICK, locator_strategy=LocatorStrategy.CSS, selector_value="#userActionsMenuHeaderButton, #meAreaHeaderButton", description="Click User Profile Avatar Menu"),
                            TestStep(step_number=11, action=ActionType.CLICK, locator_strategy=LocatorStrategy.CSS, selector_value="button:has-text('Sign Out'), #logoutBtn", description="Click Sign Out"),
                            TestStep(step_number=12, action=ActionType.CLICK, locator_strategy=LocatorStrategy.CSS, selector_value="button:has-text('OK'), #logoutConfirm", description="Confirm Sign Out dialog"),
                            TestStep(step_number=13, action=ActionType.ASSERT_TEXT, locator_strategy=LocatorStrategy.CSS, selector_value="body", expected_value="logged off", description="Verify returned to Logoff screen"),
                        ]
                    elif any(k in ac_lower for k in ["bundle", "installation", "warranty", "relationship", "configured"]):
                        steps = [
                            TestStep(step_number=1, action=ActionType.NAVIGATE, input_value=target_url, description="Open SAP Fiori Logon screen"),
                            TestStep(step_number=2, action=ActionType.FILL, locator_strategy=LocatorStrategy.CSS, selector_value="#USERNAME_FIELD-inner", input_value=(settings.sap_username or "MYRAR1").strip(), description="Enter SAP username"),
                            TestStep(step_number=3, action=ActionType.FILL, locator_strategy=LocatorStrategy.CSS, selector_value="#PASSWORD_FIELD-inner", input_value=(settings.sap_password or "Pass23#$").strip(), description="Enter SAP password"),
                            TestStep(step_number=4, action=ActionType.CLICK, locator_strategy=LocatorStrategy.CSS, selector_value="#LOGIN_LINK", description="Click Log On button"),
                            TestStep(step_number=5, action=ActionType.ASSERT_TEXT, locator_strategy=LocatorStrategy.CSS, selector_value="body", expected_value="Home", description="Assert SAP Fiori Launchpad loaded"),
                            TestStep(step_number=6, action=ActionType.CLICK, locator_strategy=LocatorStrategy.ROLE, role_name="option", selector_value="Items", description="Open Items tab"),
                            TestStep(step_number=7, action=ActionType.FILL, locator_strategy=LocatorStrategy.CSS, selector_value="[id*='ordered_prod'], input[id*='ordered_prod']", input_value=prod_val, description=f"Enter Product ID {prod_val}"),
                            TestStep(step_number=8, action=ActionType.FILL, locator_strategy=LocatorStrategy.CSS, selector_value="[id*='ordered_prod'], input[id*='ordered_prod']", input_value="Enter", description="Press Enter to trigger bundle explosion and partner derivations"),
                            TestStep(step_number=9, action=ActionType.ASSERT_TEXT, locator_strategy=LocatorStrategy.CSS, selector_value="body", expected_value=prod_val, description="Verify main product row visible in Items table"),
                            TestStep(step_number=10, action=ActionType.ASSERT_TEXT, locator_strategy=LocatorStrategy.CSS, selector_value="body", expected_value="Service", description="Verify configured service, installation, and warranty bundle items present"),
                            TestStep(step_number=11, action=ActionType.CLICK, locator_strategy=LocatorStrategy.CSS, selector_value="#userActionsMenuHeaderButton, #meAreaHeaderButton", description="Click User Profile Avatar Menu"),
                            TestStep(step_number=12, action=ActionType.CLICK, locator_strategy=LocatorStrategy.CSS, selector_value="button:has-text('Sign Out'), #logoutBtn", description="Click Sign Out"),
                            TestStep(step_number=13, action=ActionType.CLICK, locator_strategy=LocatorStrategy.CSS, selector_value="button:has-text('OK'), #logoutConfirm", description="Confirm Sign Out dialog"),
                            TestStep(step_number=14, action=ActionType.ASSERT_TEXT, locator_strategy=LocatorStrategy.CSS, selector_value="body", expected_value="logged off", description="Verify returned to Logoff screen"),
                        ]
                    elif any(k in ac_lower for k in ["required", "mandatory", "validation message", "validation"]):
                        steps = [
                            TestStep(step_number=1, action=ActionType.NAVIGATE, input_value=target_url, description="Open SAP Fiori Logon screen"),
                            TestStep(step_number=2, action=ActionType.FILL, locator_strategy=LocatorStrategy.CSS, selector_value="#USERNAME_FIELD-inner", input_value=(settings.sap_username or "MYRAR1").strip(), description="Enter SAP username"),
                            TestStep(step_number=3, action=ActionType.FILL, locator_strategy=LocatorStrategy.CSS, selector_value="#PASSWORD_FIELD-inner", input_value=(settings.sap_password or "Pass23#$").strip(), description="Enter SAP password"),
                            TestStep(step_number=4, action=ActionType.CLICK, locator_strategy=LocatorStrategy.CSS, selector_value="#LOGIN_LINK", description="Click Log On button"),
                            TestStep(step_number=5, action=ActionType.ASSERT_TEXT, locator_strategy=LocatorStrategy.CSS, selector_value="body", expected_value="Home", description="Assert SAP Fiori Launchpad loaded"),
                            TestStep(step_number=6, action=ActionType.CLICK, locator_strategy=LocatorStrategy.TEXT, selector_value="Manage Service Quotations", description="Click Manage Service Quotations tile"),
                            TestStep(step_number=7, action=ActionType.CLICK, locator_strategy=LocatorStrategy.CSS, selector_value="button:has-text('New Create'), button:has-text('Create'), [title*='Create'], #btnCreate", description="Click Create button on Service Quotations worklist"),
                            TestStep(step_number=8, action=ActionType.CLICK, locator_strategy=LocatorStrategy.TEXT, selector_value=ttype_val, description=f"Select Transaction Type {ttype_val} from popup"),
                            TestStep(step_number=9, action=ActionType.FILL, locator_strategy=LocatorStrategy.ROLE, role_name="textbox", selector_value="Sold-To Party:", input_value="", description="Leave mandatory Sold-to Party field empty"),
                            TestStep(step_number=10, action=ActionType.FILL, locator_strategy=LocatorStrategy.ROLE, role_name="textbox", selector_value="Sold-To Party:", input_value="Enter", description="Press Enter to trigger backend validation"),
                            TestStep(step_number=11, action=ActionType.CLICK, locator_strategy=LocatorStrategy.ROLE, role_name="button", selector_value="Save (Ctrl+S)", description="Attempt Save with missing mandatory field"),
                            TestStep(step_number=12, action=ActionType.ASSERT_TEXT, locator_strategy=LocatorStrategy.CSS, selector_value="body", expected_value="sold-to", description="Verify mandatory Sold-to Party validation error message is handled correctly"),
                            TestStep(step_number=13, action=ActionType.CLICK, locator_strategy=LocatorStrategy.CSS, selector_value="#userActionsMenuHeaderButton, #meAreaHeaderButton", description="Click User Profile Avatar Menu"),
                            TestStep(step_number=14, action=ActionType.CLICK, locator_strategy=LocatorStrategy.CSS, selector_value="button:has-text('Sign Out'), #logoutBtn", description="Click Sign Out"),
                            TestStep(step_number=15, action=ActionType.CLICK, locator_strategy=LocatorStrategy.CSS, selector_value="button:has-text('OK'), #logoutConfirm", description="Confirm Sign Out dialog"),
                            TestStep(step_number=16, action=ActionType.ASSERT_TEXT, locator_strategy=LocatorStrategy.CSS, selector_value="body", expected_value="logged off", description="Verify returned to Logoff screen"),
                        ]
                    elif any(k in ac_lower for k in ["item", "product", "quantity", "45157510101"]):
                        steps = [
                            TestStep(step_number=1, action=ActionType.NAVIGATE, input_value=target_url, description="Open SAP Fiori Logon screen"),
                            TestStep(step_number=2, action=ActionType.FILL, locator_strategy=LocatorStrategy.CSS, selector_value="#USERNAME_FIELD-inner", input_value=(settings.sap_username or "MYRAR1").strip(), description="Enter SAP username"),
                            TestStep(step_number=3, action=ActionType.FILL, locator_strategy=LocatorStrategy.CSS, selector_value="#PASSWORD_FIELD-inner", input_value=(settings.sap_password or "Pass23#$").strip(), description="Enter SAP password"),
                            TestStep(step_number=4, action=ActionType.CLICK, locator_strategy=LocatorStrategy.CSS, selector_value="#LOGIN_LINK", description="Click Log On button"),
                            TestStep(step_number=5, action=ActionType.ASSERT_TEXT, locator_strategy=LocatorStrategy.CSS, selector_value="body", expected_value="Home", description="Assert SAP Fiori Launchpad loaded"),
                            TestStep(step_number=6, action=ActionType.CLICK, locator_strategy=LocatorStrategy.ROLE, role_name="option", selector_value="Items", description="Open Items tab"),
                            TestStep(step_number=7, action=ActionType.FILL, locator_strategy=LocatorStrategy.CSS, selector_value="[id*='ordered_prod'], input[id*='ordered_prod']", input_value=prod_val, description=f"Enter Product ID {prod_val}"),
                            TestStep(step_number=8, action=ActionType.FILL, locator_strategy=LocatorStrategy.CSS, selector_value="[id*='quantity'], input[id*='quantity']", input_value=qty_val, description=f"Enter Quantity {qty_val}"),
                            TestStep(step_number=9, action=ActionType.FILL, locator_strategy=LocatorStrategy.CSS, selector_value="[id*='quantity'], input[id*='quantity']", input_value="Enter", description="Press Enter to commit line item"),
                            TestStep(step_number=10, action=ActionType.CLICK, locator_strategy=LocatorStrategy.ROLE, role_name="button", selector_value="Save (Ctrl+S)", description="Click Save button to persist quotation line items"),
                            TestStep(step_number=11, action=ActionType.ASSERT_TEXT, locator_strategy=LocatorStrategy.CSS, selector_value="body", expected_value=prod_val, description=f"Assert main product {prod_val} and quantity {qty_val} saved correctly"),
                            TestStep(step_number=12, action=ActionType.CLICK, locator_strategy=LocatorStrategy.CSS, selector_value="#userActionsMenuHeaderButton, #meAreaHeaderButton", description="Click User Profile Avatar Menu"),
                            TestStep(step_number=13, action=ActionType.CLICK, locator_strategy=LocatorStrategy.CSS, selector_value="button:has-text('Sign Out'), #logoutBtn", description="Click Sign Out"),
                            TestStep(step_number=14, action=ActionType.CLICK, locator_strategy=LocatorStrategy.CSS, selector_value="button:has-text('OK'), #logoutConfirm", description="Confirm Sign Out dialog"),
                            TestStep(step_number=15, action=ActionType.ASSERT_TEXT, locator_strategy=LocatorStrategy.CSS, selector_value="body", expected_value="logged off", description="Verify returned to Logoff screen"),
                        ]
                    elif any(k in ac_lower for k in ["create", "header", "sold-to", "party", "customer", "zqds"]):
                        steps = [
                            TestStep(step_number=1, action=ActionType.NAVIGATE, input_value=target_url, description="Open SAP Fiori Logon screen"),
                            TestStep(step_number=2, action=ActionType.FILL, locator_strategy=LocatorStrategy.CSS, selector_value="#USERNAME_FIELD-inner", input_value=(settings.sap_username or "MYRAR1").strip(), description="Enter SAP username"),
                            TestStep(step_number=3, action=ActionType.FILL, locator_strategy=LocatorStrategy.CSS, selector_value="#PASSWORD_FIELD-inner", input_value=(settings.sap_password or "Pass23#$").strip(), description="Enter SAP password"),
                            TestStep(step_number=4, action=ActionType.CLICK, locator_strategy=LocatorStrategy.CSS, selector_value="#LOGIN_LINK", description="Click Log On button"),
                            TestStep(step_number=5, action=ActionType.ASSERT_TEXT, locator_strategy=LocatorStrategy.CSS, selector_value="body", expected_value="Home", description="Assert SAP Fiori Launchpad loaded"),
                            TestStep(step_number=6, action=ActionType.CLICK, locator_strategy=LocatorStrategy.TEXT, selector_value="Manage Service Quotations", description="Click Manage Service Quotations tile"),
                            TestStep(step_number=7, action=ActionType.CLICK, locator_strategy=LocatorStrategy.CSS, selector_value="button:has-text('New Create'), button:has-text('Create'), [title*='Create'], #btnCreate", description="Click Create button on Service Quotations worklist"),
                            TestStep(step_number=8, action=ActionType.CLICK, locator_strategy=LocatorStrategy.TEXT, selector_value=ttype_val, description=f"Select Transaction Type {ttype_val} (CE-Direct Sales) from popup"),
                            TestStep(step_number=9, action=ActionType.FILL, locator_strategy=LocatorStrategy.ROLE, role_name="textbox", selector_value="Description:", input_value=desc_val, description=f"Enter Quotation Description '{desc_val}'"),
                            TestStep(step_number=10, action=ActionType.FILL, locator_strategy=LocatorStrategy.ROLE, role_name="textbox", selector_value="Sold-To Party:", input_value=soldto_val, description=f"Enter Sold-to Party customer '{soldto_val}'"),
                            TestStep(step_number=11, action=ActionType.FILL, locator_strategy=LocatorStrategy.ROLE, role_name="textbox", selector_value="Sold-To Party:", input_value="Enter", description="Press Enter to commit Sold-to Party and trigger partner determination"),
                            TestStep(step_number=12, action=ActionType.ASSERT_TEXT, locator_strategy=LocatorStrategy.CSS, selector_value="body", expected_value=soldto_val, description="Assert quotation created with required transaction type and sold-to party"),
                            TestStep(step_number=13, action=ActionType.CLICK, locator_strategy=LocatorStrategy.CSS, selector_value="#userActionsMenuHeaderButton, #meAreaHeaderButton", description="Click User Profile Avatar Menu"),
                            TestStep(step_number=14, action=ActionType.CLICK, locator_strategy=LocatorStrategy.CSS, selector_value="button:has-text('Sign Out'), #logoutBtn", description="Click Sign Out"),
                            TestStep(step_number=15, action=ActionType.CLICK, locator_strategy=LocatorStrategy.CSS, selector_value="button:has-text('OK'), #logoutConfirm", description="Confirm Sign Out dialog"),
                            TestStep(step_number=16, action=ActionType.ASSERT_TEXT, locator_strategy=LocatorStrategy.CSS, selector_value="body", expected_value="logged off", description="Verify returned to Logoff screen"),
                        ]
                    elif any(k in ac_lower for k in ["release", "accept"]):
                        steps = [
                            TestStep(step_number=1, action=ActionType.CLICK, locator_strategy=LocatorStrategy.CSS, selector_value="button:has-text('Edit'), a:has-text('Edit'), [title*='Edit'], [aria-label*='Edit']", description="Click Edit button"),
                            TestStep(step_number=2, action=ActionType.CLICK, locator_strategy=LocatorStrategy.CSS, selector_value="#C9_W36_V39_V40_btadminh_lcstatus-btn, [id*='btadminh_lcstatus-btn']", description="Open Lifecycle Status dropdown"),
                            TestStep(step_number=3, action=ActionType.CLICK, locator_strategy=LocatorStrategy.ROLE, role_name="link", selector_value="Released", description="Change status to Released"),
                            TestStep(step_number=4, action=ActionType.CLICK, locator_strategy=LocatorStrategy.ROLE, role_name="button", selector_value="Save (Ctrl+S)", description="Click Save button"),
                            TestStep(step_number=5, action=ActionType.CLICK, locator_strategy=LocatorStrategy.CSS, selector_value="button:has-text('Accept'), [title*='Accept'], a:has-text('Accept'), [role='menuitem']:has-text('Accept')", description="Click Accept button on header toolbar"),
                            TestStep(step_number=6, action=ActionType.ASSERT_TEXT, locator_strategy=LocatorStrategy.CSS, selector_value="body", expected_value="Accepted", description="Verify quotation status updated to Accepted"),
                        ]
                    elif any(k in ac_lower for k in ["price", "pricing", "ztaf", "condition"]):
                        steps = [
                            TestStep(step_number=1, action=ActionType.CLICK, locator_strategy=LocatorStrategy.ROLE, role_name="option", selector_value="Price Details", description="Click Price Details tab"),
                            TestStep(step_number=2, action=ActionType.CLICK, locator_strategy=LocatorStrategy.ROLE, role_name="button", selector_value="Add", description="Click Add Pricing Element button"),
                            TestStep(step_number=3, action=ActionType.CLICK, locator_strategy=LocatorStrategy.TEXT, selector_value=pricing_val, description=f"Select condition type {pricing_val} from popup"),
                            TestStep(step_number=4, action=ActionType.CLICK, locator_strategy=LocatorStrategy.ROLE, role_name="button", selector_value="Back", description="Click Back to return to quotation"),
                            TestStep(step_number=5, action=ActionType.ASSERT_TEXT, locator_strategy=LocatorStrategy.CSS, selector_value="body", expected_value=pricing_val, description=f"Verify condition type {pricing_val} present in pricing elements"),
                        ]
                    elif any(k in ac_lower for k in ["duration", "date", "term"]):
                        steps = [
                            TestStep(step_number=1, action=ActionType.CLICK, locator_strategy=LocatorStrategy.ROLE, role_name="option", selector_value="Dates", description="Open Dates tab"),
                            TestStep(step_number=2, action=ActionType.FILL, locator_strategy=LocatorStrategy.CSS, selector_value="#C16_W64_V65_DatesTable_bottom_div tr:has-text('Term of Quotation') input, #C16_W64_V65_DatesTable_bottom_div tr:has-text('Term of Quotation') [role='textbox']", input_value=duration_val, description=f"Go to Term of Quotation and enter Duration as {duration_val}"),
                            TestStep(step_number=3, action=ActionType.CLICK, locator_strategy=LocatorStrategy.CSS, selector_value="[id='C16_W64_V65_btdate_table[4].time_unit-btn']", description="Open Time Unit dropdown"),
                            TestStep(step_number=4, action=ActionType.CLICK, locator_strategy=LocatorStrategy.ROLE, role_name="link", selector_value=time_unit_val, description=f"Select time unit {time_unit_val}"),
                            TestStep(step_number=5, action=ActionType.ASSERT_TEXT, locator_strategy=LocatorStrategy.CSS, selector_value="body", expected_value=time_unit_val, description="Verify duration and validity dates section displayed"),
                        ]
                    else:
                        steps = [
                            TestStep(step_number=1, action=ActionType.NAVIGATE, input_value=target_url, description="Open SAP Fiori Logon screen"),
                            TestStep(step_number=2, action=ActionType.FILL, locator_strategy=LocatorStrategy.CSS, selector_value="#USERNAME_FIELD-inner", input_value=(settings.sap_username or "MYRAR1").strip(), description="Enter SAP username"),
                            TestStep(step_number=3, action=ActionType.FILL, locator_strategy=LocatorStrategy.CSS, selector_value="#PASSWORD_FIELD-inner", input_value=(settings.sap_password or "Pass23#$").strip(), description="Enter SAP password"),
                            TestStep(step_number=4, action=ActionType.CLICK, locator_strategy=LocatorStrategy.CSS, selector_value="#LOGIN_LINK", description="Click Log On button"),
                            TestStep(step_number=5, action=ActionType.ASSERT_TEXT, locator_strategy=LocatorStrategy.CSS, selector_value="body", expected_value="Home", description="Assert SAP Fiori Launchpad loaded"),
                            TestStep(step_number=6, action=ActionType.CLICK, locator_strategy=LocatorStrategy.TEXT, selector_value="Manage Service Quotations", description="Click Manage Service Quotations tile"),
                            TestStep(step_number=7, action=ActionType.ASSERT_TEXT, locator_strategy=LocatorStrategy.CSS, selector_value="body", expected_value="Service Quotations", description="Verify Service Quotations screen loaded"),
                        ]
                else:
                    # Generic Non-SAP (Demo App) Fallback
                    if is_neg:
                        if any(k in ac_lower for k in ["quantity", "exceed", "limit", "max", "500"]):
                            steps = [
                                TestStep(step_number=1, action=ActionType.NAVIGATE, input_value=f"{base_url}/", description="Open application"),
                                TestStep(step_number=2, action=ActionType.FILL, locator_strategy=LocatorStrategy.TEST_ID, selector_value="customer-id-input", input_value="CUST-3001", description="Enter valid customer ID"),
                                TestStep(step_number=3, action=ActionType.SELECT_OPTION, locator_strategy=LocatorStrategy.TEST_ID, selector_value="material-select", input_value="MAT-1001", description="Select material from catalog"),
                                TestStep(step_number=4, action=ActionType.FILL, locator_strategy=LocatorStrategy.TEST_ID, selector_value="quantity-input", input_value="999", description="Enter quantity exceeding limit of 500"),
                                TestStep(step_number=5, action=ActionType.CLICK, locator_strategy=LocatorStrategy.TEST_ID, selector_value="submit-order-button", description="Submit form"),
                                TestStep(step_number=6, action=ActionType.ASSERT_TEXT, locator_strategy=LocatorStrategy.TEST_ID, selector_value="error-banner", expected_value="Validation Error", description="Verify quantity limit error banner"),
                            ]
                        else:
                            steps = [
                                TestStep(step_number=1, action=ActionType.NAVIGATE, input_value=f"{base_url}/", description="Open application"),
                                TestStep(step_number=2, action=ActionType.FILL, locator_strategy=LocatorStrategy.TEST_ID, selector_value="customer-id-input", input_value="", description="Leave customer ID empty"),
                                TestStep(step_number=3, action=ActionType.SELECT_OPTION, locator_strategy=LocatorStrategy.TEST_ID, selector_value="material-select", input_value="MAT-1001", description="Select material from catalog"),
                                TestStep(step_number=4, action=ActionType.FILL, locator_strategy=LocatorStrategy.TEST_ID, selector_value="quantity-input", input_value="5", description="Enter quantity"),
                                TestStep(step_number=5, action=ActionType.CLICK, locator_strategy=LocatorStrategy.TEST_ID, selector_value="submit-order-button", description="Submit form"),
                                TestStep(step_number=6, action=ActionType.ASSERT_TEXT, locator_strategy=LocatorStrategy.TEST_ID, selector_value="error-banner", expected_value="Validation Error", description="Verify mandatory customer ID error banner"),
                            ]
                    else:
                        steps = [
                            TestStep(step_number=1, action=ActionType.NAVIGATE, input_value=f"{base_url}/", description="Open application"),
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
            normalized_tc.id = f"TC-{idx:02d}"
            test_cases.append(normalized_tc)
            progress_callback(idx, total, f"Completed Scenario {idx}/{total}: {normalized_tc.title} [Done]")

        # Guarantee strictly unique sequential IDs across all test cases
        for i, tc in enumerate(test_cases, start=1):
            tc.id = f"TC-{i:02d}"

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

