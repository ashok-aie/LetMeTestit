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
from app.flows.sap_flows import (
    extract_sap_quotation_parameters,
    extract_outbound_delivery_parameters,
    extract_billing_document_parameters,
    build_sap_login_steps,
    build_sap_logoff_steps,
    build_service_quotation_steps,
    build_revenue_contract_steps,
    build_outbound_delivery_steps,
    build_billing_document_steps,
    build_monolithic_rar_steps,
    build_evidence_capture_steps,
    build_bundle_validation_steps,
    build_mandatory_validation_steps,
    build_item_entry_steps,
    build_header_creation_steps,
    build_release_accept_steps,
    build_pricing_condition_steps,
    build_duration_dates_steps,
    build_sap_quotation_test_data,
    DEFAULT_MRC_URL,
    DEFAULT_OUTBOUND_DELIVERY_URL,
    DEFAULT_BILLING_DOC_URL,
)
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
        req_corpus_check = f"{requirement.summary} {requirement.description_text}".lower()
        is_sap_req = any(k in req_corpus_check for k in ["sap", "fiori", "quotation", "service quotation", "zqds", "rar", "manage revenue contracts", "contract", "obligation", "hospital"])
        default_url = settings.sap_fiori_url if is_sap_req else settings.demo_app_url
        base_url = target_base_url or default_url

        # Incremental per-AC generation when progress_callback is provided or when multiple ACs exist
        if progress_callback is not None or (requirement.acceptance_criteria and len(requirement.acceptance_criteria) >= 2):
            cb = progress_callback if progress_callback is not None else (lambda c, t, m: None)
            return self._generate_suite_incremental(requirement, base_url, cb)
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
        raw_acs = requirement.acceptance_criteria or [AcceptanceCriterion(id="AC-01", text=requirement.summary.strip())]
        # Defensive split: if any AC block still contains embedded line-start "AC -03" / "AC-04" sections, split them out
        acs: List[AcceptanceCriterion] = []
        for raw_ac in raw_acs:
            sub_blocks = re.findall(
                r"(?:^|\n)\s*(?:[-*#]+\s*)?(?:\*\*|\[)*\s*(AC[\s\-_–—:]*\d+\b.*?)(?=(?:\n\s*(?:[-*#]+\s*)?(?:\*\*|\[)*\s*AC[\s\-_–—:]*\d+(?:\b|[:.\s(*\]]))|\Z)",
                raw_ac.text or "",
                re.DOTALL | re.IGNORECASE,
            )
            if len(sub_blocks) > 1:
                for sb in sub_blocks:
                    clean_sb = re.sub(
                        r"^AC[\s\-_–—:]*0*(\d+)\s*[\]:.\-–—]*\s*",
                        lambda m: f"AC-{int(m.group(1)):02d}: ",
                        sb.strip(),
                        count=1,
                        flags=re.IGNORECASE,
                    )
                    acs.append(AcceptanceCriterion(id=f"AC-{len(acs) + 1:02d}", text=clean_sb, type=raw_ac.type))
            else:
                acs.append(AcceptanceCriterion(id=f"AC-{len(acs) + 1:02d}", text=raw_ac.text, type=raw_ac.type))
        requirement.acceptance_criteria = acs
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
                req_corpus = f"{requirement.summary.lower()} {requirement.description_text.lower()} {ac_lower}"
                is_sap = (
                    "nodomain.com" in base_url
                    or "44325" in base_url
                    or any(k in req_corpus for k in ["sap", "fiori", "quotation", "service quotation", "zqds", "rar", "hospital"])
                )
                is_demo_app = not is_sap and ("127.0.0.1" in base_url or "localhost" in base_url or ":8000" in base_url)
                target_url = settings.sap_fiori_url if is_sap else base_url

                # Parameter extraction from centralized flow registry
                params = extract_sap_quotation_parameters(requirement, ac)
                desc_val = params["desc_val"]
                soldto_val = params["soldto_val"]
                prod_val = params["prod_val"]
                qty_val = params["qty_val"]
                duration_val = params["duration_val"]
                time_unit_val = params["time_unit_val"]
                pricing_val = params["pricing_val"]
                ttype_val = params["ttype_val"]
                extracted_items = params["extracted_items"]

                is_neg = any(w in ac_lower for w in ["invalid", "without", "missing", "error", "exceed", "blank", "cannot", "fail", "reject", "negative", "boundary", "zero", "limit"])

                if is_sap:
                    is_outbound_delivery_ac = any(k in ac_lower for k in ["outbound delivery", "post goods issue", "picking"]) and not any(k in ac_lower for k in ["start new quotation", "term of quotation"])
                    is_billing_doc_ac = any(k in ac_lower for k in ["create billing document", "billing document", "fully invoiced", "billing number"]) and not any(k in ac_lower for k in ["outbound delivery", "post goods issue", "start new quotation"])
                    is_mrc_ac = any(k in ac_lower for k in ["manage revenue contracts", "revenue contract", "rar contract", "operational document"]) and not any(k in ac_lower for k in ["quotation of transaction type", "term of", "containing 5 line items", "start new quotation", "sold-to"])
                    has_downstream_contract_ac = any(any(k in o_ac.text.lower() for k in ["manage revenue contracts", "revenue contract", "rar contract", "operational document", "outbound delivery", "create billing document"]) for o_ac in acs if o_ac.id != ac.id)

                    # SAP-Native Fallback Branches via Centralized Flow Registry
                    if is_outbound_delivery_ac:
                        steps = build_outbound_delivery_steps(
                            target_url=target_url,
                            outbound_delivery_url=DEFAULT_OUTBOUND_DELIVERY_URL,
                            include_logoff=True,
                        )
                    elif is_billing_doc_ac:
                        steps = build_billing_document_steps(
                            target_url=target_url,
                            billing_doc_url=DEFAULT_BILLING_DOC_URL,
                            include_logoff=True,
                        )
                    elif is_mrc_ac and total >= 2:
                        steps = build_revenue_contract_steps(
                            target_url=target_url,
                            operational_doc="${OPERATIONAL_DOCUMENT}",
                            mrc_url=DEFAULT_MRC_URL,
                            include_logoff=True,
                        )
                    elif total >= 2 and has_downstream_contract_ac:
                        steps = build_service_quotation_steps(
                            params=params,
                            target_url=target_url,
                            capture_transaction_history=True,
                            include_logoff=True,
                        )
                    elif any(k in req_corpus for k in ["contract", "obligation", "pob", "operational document", "manage contracts", "accounting validation"]):
                        steps = build_monolithic_rar_steps(
                            params=params,
                            target_url=target_url,
                            operational_doc="${OPERATIONAL_DOCUMENT}",
                            mrc_url=DEFAULT_MRC_URL,
                            include_logoff=True,
                        )
                    elif any(k in ac_lower for k in ["end-to-end", "e2e", "procedural flow", "business flow", "complete flow", "lifecycle"]) or (
                        any(k in req_corpus for k in ["quotation", "service quotation", "zqds"]) and
                        any(k in req_corpus for k in ["item", "product", "45157510101"]) and
                        any(k in req_corpus for k in ["dates", "term", "duration"]) and
                        any(k in req_corpus for k in ["price", "ztaf", "release", "accept"])
                    ):
                        steps = build_service_quotation_steps(
                            params=params,
                            target_url=target_url,
                            capture_transaction_history=False,
                            include_logoff=True,
                        )
                    elif any(k in ac_lower for k in ["evidence", "number", "quotation number", "status", "document", "saved quotation"]) and not any(k in ac_lower for k in ["release", "accept"]):
                        steps = build_evidence_capture_steps(params=params, target_url=target_url)
                    elif any(k in ac_lower for k in ["bundle", "installation", "warranty", "relationship", "configured"]):
                        steps = build_bundle_validation_steps(params=params, target_url=target_url)
                    elif any(k in ac_lower for k in ["required", "mandatory", "validation message", "validation"]):
                        steps = build_mandatory_validation_steps(params=params, target_url=target_url)
                    elif any(k in ac_lower for k in ["item", "product", "quantity", "45157510101"]):
                        steps = build_item_entry_steps(params=params, target_url=target_url)
                    elif any(k in ac_lower for k in ["create", "header", "sold-to", "party", "customer", "zqds"]):
                        steps = build_header_creation_steps(params=params, target_url=target_url)
                    elif any(k in ac_lower for k in ["release", "accept"]):
                        steps = build_release_accept_steps()
                    elif any(k in ac_lower for k in ["price", "pricing", "ztaf", "condition"]):
                        steps = build_pricing_condition_steps(pricing_val=pricing_val)
                    elif any(k in ac_lower for k in ["duration", "date", "term"]):
                        steps = build_duration_dates_steps(duration_val=duration_val, time_unit_val=time_unit_val)
                    else:
                        login = build_sap_login_steps(target_url)
                        launch = [
                            TestStep(step_number=6, action=ActionType.CLICK, locator_strategy=LocatorStrategy.TEXT, selector_value="Manage Service Quotations", description="Click Manage Service Quotations tile"),
                            TestStep(step_number=7, action=ActionType.ASSERT_TEXT, locator_strategy=LocatorStrategy.CSS, selector_value="body", expected_value="Service Quotations", description="Verify Service Quotations screen loaded"),
                        ]
                        steps = login + launch
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
            # Dynamic test data: bind ${key} placeholders to values extracted from the AC text (no hardcoding)
            try:
                ac_low_td = ac.text.lower()
                if any(k in ac_low_td for k in ["outbound delivery", "post goods issue", "picking"]) and not any(k in ac_low_td for k in ["start new quotation", "term of quotation"]):
                    merged_td = dict(normalized_tc.test_data or {})
                    merged_td.update(extract_outbound_delivery_parameters(ac.text))
                    merged_td["storage_location"] = merged_td.get("storage_location") if str(merged_td.get("storage_location", "")).isdigit() and len(str(merged_td.get("storage_location", ""))) == 4 else "6020"
                    merged_td["picking_quantity"] = "1"
                    normalized_tc.test_data = merged_td
                elif any(k in ac_low_td for k in ["create billing document", "billing document", "fully invoiced", "billing number"]) and not any(k in ac_low_td for k in ["outbound delivery", "post goods issue", "start new quotation"]):
                    merged_td = dict(normalized_tc.test_data or {})
                    merged_td.update(extract_billing_document_parameters(ac.text))
                    normalized_tc.test_data = merged_td
                else:
                    td_params = extract_sap_quotation_parameters(requirement, ac)
                    if td_params.get("line_items"):
                        merged_td = build_sap_quotation_test_data(td_params)
                        merged_td.update(normalized_tc.test_data or {})
                        normalized_tc.test_data = merged_td
            except Exception as td_err:
                logger.debug("Test data extraction skipped for %s: %s", ac.id, td_err)
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

        # Credentials are never hardcoded: ${...} placeholders are resolved at execution time from settings
        sap_user = "${sap_username}"
        sap_pwd = "${sap_password}"

        steps = list(tc.steps)

        # ----------------------------------------------------------------------
        # PART 1: ENSURE FULL LOGIN STEPS AT BEGINNING (DEDUPLICATED)
        # ----------------------------------------------------------------------
        standard_login_steps = build_sap_login_steps(target_url=sap_url, username=sap_user, password=sap_pwd)

        def is_leading_login_step(s: TestStep) -> bool:
            act = s.action
            s_val = (s.selector_value or "").lower()
            s_desc = (s.description or "").lower()
            s_role = (s.role_name or "").lower()
            s_exp = (s.expected_value or "").lower()

            if act == ActionType.NAVIGATE:
                if idx_start == 0:
                    nav_url = (s.input_value or "").lower()
                    is_deep_app_url = any(
                        h in nav_url
                        for h in ["outbounddelivery-", "billingdocument-", "revenueaccountingcontract-"]
                    )
                    has_later_nav = any(st.action == ActionType.NAVIGATE for st in steps[1:])
                    if is_deep_app_url and not has_later_nav:
                        return False
                    return True
                return False

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

        standard_logoff_steps = build_sap_logoff_steps(start_step_number=901)

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

