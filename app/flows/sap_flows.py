"""
SAP Flow Definitions and Step Synthesis Registry.
Acts as the Single Source of Truth for SAP S/4HANA Fiori, Service Quotations,
and RAR (Revenue Accounting and Reporting) end-to-end testing.
"""
import re
import json
from typing import List, Tuple, Dict, Any, Optional

from app.config import settings
from app.models.requirements import JiraRequirement, AcceptanceCriterion
from app.models.test_suite import TestStep, ActionType, LocatorStrategy

DEFAULT_MRC_URL = (
    "https://s4srv25.nodomain.com:44325/sap/bc/ui2/flp?sap-client=100&sap-language=EN"
    "#RevenueAccountingContract-manageContract&/?sap-iapp-state--history=TAS60ZN0APGEXK9SB8U7CWP0998E9ZTQEZ7DBW9FR"
)

DEFAULT_OUTBOUND_DELIVERY_URL = (
    "https://s4srv25.nodomain.com:44325/sap/bc/ui2/flp?sap-client=100&sap-language=EN"
    "#OutboundDelivery-createInWebGUI?sap-ui-tech-hint=GUI"
)

DEFAULT_BILLING_DOC_URL = (
    "https://s4srv25.nodomain.com:44325/sap/bc/ui2/flp?sap-client=100&sap-language=EN"
    "#BillingDocument-createBillingDocuments?sap-ui-tech-hint=GUI"
)


def extract_sap_quotation_parameters(
    requirement: JiraRequirement,
    ac: Optional[AcceptanceCriterion] = None,
) -> Dict[str, Any]:
    """
    Extracts all structured test parameters for SAP Service Quotations from
    the requirement summary, description, and acceptance criterion text.
    """
    clean_summary = requirement.summary.replace("</untrusted_requirement>", "").strip()
    ac_text = ac.text if ac else ""
    combined_corpus = f"{clean_summary} {requirement.description_text} {ac_text}".strip()

    # Description extraction
    desc_val = "RAR Test"
    m_desc = re.search(
        r"description\s*(?:as|is|:)?\s*['\"]?([^'\"\n\r,;]+?)['\"]?(?:\n|\r|,|;|\d+\s+|sold-to|\s+and|\s+with|\.|$)",
        combined_corpus,
        re.IGNORECASE,
    )
    if m_desc and m_desc.group(1).strip():
        desc_val = m_desc.group(1).strip()

    # Sold-to Party extraction
    soldto_val = "Brugmann Hospital"
    m_soldto = re.search(
        r"sold-to\s*(?:party)?\s*(?:as|is|:)?\s*['\"]?([^'\"\n\r,;]+?)['\"]?(?:\n|\r|;|\d+\s+|\s+and|\s+with|\s+press|\.|$)",
        combined_corpus,
        re.IGNORECASE,
    )
    if m_soldto and m_soldto.group(1).strip():
        soldto_val = m_soldto.group(1).strip()

    # Single Product fallback extraction
    prod_val = "45157510101"
    m_prod = re.search(
        r"(?:product\s*id|product)\s*(?:as|is|:)?\s*['\"]?([0-9]{5,})['\"]?",
        combined_corpus,
        re.IGNORECASE,
    )
    if m_prod and m_prod.group(1).strip():
        prod_val = m_prod.group(1).strip()

    # Single Quantity fallback extraction
    qty_val = "1"
    m_qty = re.search(r"quantity.*?(?:is|as|:|enter|\b)\s*([0-9]+)", combined_corpus, re.IGNORECASE)
    if m_qty:
        qty_val = m_qty.group(1).strip()
    else:
        m_qty2 = re.search(r"(\d+)\s*quantity", combined_corpus, re.IGNORECASE)
        if m_qty2:
            qty_val = m_qty2.group(1).strip()

    # Multi-product extraction: supports 1 or more line items with individual quantities
    paired_items: List[Tuple[str, str]] = []
    pair_pattern = re.compile(
        r"(?:product\s*(?:id)?\s*(?:is|as|:)?\s*['\"]?([0-9]{6,12})['\"]?.*?(?:and\s*(?:its\s*)?)?quantity\s*(?:is|as|:)?\s*['\"]?(\d+)['\"]?|"
        r"quantity\s*(?:is|as|:)?\s*['\"]?(\d+)['\"]?.*?product\s*(?:id)?\s*(?:is|as|:)?\s*['\"]?([0-9]{6,12})['\"]?)",
        re.IGNORECASE | re.DOTALL,
    )

    # 1. Prioritize explicit AC text for item-quantity pairings
    if ac_text:
        for m in pair_pattern.finditer(ac_text):
            if m.group(1) and m.group(2):
                paired_items.append((m.group(1).strip(), m.group(2).strip()))
            elif m.group(3) and m.group(4):
                paired_items.append((m.group(4).strip(), m.group(3).strip()))

    # 2. Supplement from broader requirement context if not already captured
    for m in pair_pattern.finditer(combined_corpus):
        p_id = (m.group(1) or m.group(4)).strip()
        p_qty = (m.group(2) or m.group(3)).strip()
        if not any(p == p_id for p, _ in paired_items):
            paired_items.append((p_id, p_qty))

    m_list = re.search(r"(?:product\s*(?:id)?s?\s*(?:is|are|:))\s*([0-9,\s\n\rand]+)", combined_corpus, re.IGNORECASE)
    list_prods: List[str] = []
    if m_list:
        chunk = m_list.group(1)
        raw_nums = re.findall(r"\b([0-9]{6,12})\b", chunk)
        for n in raw_nums:
            if n not in list_prods and n not in ("8000000631", "8000000653", "44325"):
                list_prods.append(n)

    all_sap_materials = re.findall(r"\b(45[0-9]{8,10})\b", combined_corpus)

    combined_prods: List[str] = []
    for p, _ in paired_items:
        if p not in combined_prods:
            combined_prods.append(p)
    for p in list_prods:
        if p not in combined_prods:
            combined_prods.append(p)
    for p in all_sap_materials:
        if p not in combined_prods:
            combined_prods.append(p)

    if not combined_prods:
        combined_prods = [prod_val]

    # Global quantity fallback or 'for each' quantity
    m_each_qty = re.search(r"quantity\s*(?:is|as|:|enter|\b)\s*([0-9]+)\s*(?:for\s*each|each)", combined_corpus, re.IGNORECASE)
    default_qty = qty_val
    if m_each_qty:
        default_qty = m_each_qty.group(1).strip()

    paired_dict = dict(paired_items)
    extracted_items = [(p, paired_dict.get(p, default_qty)) for p in combined_prods]

    # Duration extraction
    duration_val = "1"
    m_dur = re.search(
        r"(?:duration\s*(?:as|is|:)?\s*['\"]?(\d+)['\"]?|term\s*(?:of\s*quotation)?\s*.*?(\d+))",
        combined_corpus,
        re.IGNORECASE,
    )
    if m_dur:
        duration_val = (m_dur.group(1) or m_dur.group(2)).strip()

    # Time Unit extraction
    time_unit_val = "Year"
    m_tu = re.search(r"time\s*unit\s*(?:as|is|:)?\s*['\"]?([a-zA-Z]+)['\"]?", combined_corpus, re.IGNORECASE)
    if m_tu:
        raw_tu = m_tu.group(1).strip()
        time_unit_val = "Month" if "month" in raw_tu.lower() else ("Day" if "day" in raw_tu.lower() else "Year")
    else:
        m_term_unit = re.search(r"term\s*(?:of\s*quotation)?\s*.*?\d+\s*([a-zA-Z]+)", combined_corpus, re.IGNORECASE)
        if m_term_unit:
            raw_tu = m_term_unit.group(1).strip()
            time_unit_val = "Month" if "month" in raw_tu.lower() else ("Day" if "day" in raw_tu.lower() else "Year")

    # Pricing Condition extraction: prioritize standard SAP pricing condition codes (e.g. ZTAF, PR00, PPR0, ZPR0)
    pricing_val = "ZTAF"
    m_code = re.search(r"\b(ZTAF|PR00|PPR0|ZPR0|EDI1|K004|K005|RA00)\b", combined_corpus, re.IGNORECASE)
    if m_code:
        pricing_val = m_code.group(1).strip().upper()
    else:
        stopwords = {
            "condition", "conditions", "type", "addition", "element", "details",
            "tab", "popup", "is", "as", "and", "the", "a", "for", "price", "pricing",
            "zqds", "zqdv", "srvq", "srvo", "ce-direct", "sales", "direct"
        }
        # 1. Prioritize quoted pricing element e.g. 'ZTAF'
        m_price_quoted = re.search(
            r"(?:price\s*condition|pricing\s*element|condition\s*type|pricing)\s*(?:as|is|:)?\s*['\"]([a-zA-Z0-9_\-]+)['\"]?",
            combined_corpus,
            re.IGNORECASE,
        )
        if m_price_quoted and m_price_quoted.group(1).strip().lower() not in stopwords:
            pricing_val = m_price_quoted.group(1).strip()
        else:
            # 2. General pattern with stopword rejection
            for m in re.finditer(
                r"(?:price\s*condition|pricing\s*element|condition\s*type|pricing)\s*(?:as|is|:)?\s*['\"]?([a-zA-Z0-9_\-]+)['\"]?",
                combined_corpus,
                re.IGNORECASE,
            ):
                candidate = m.group(1).strip()
                if candidate.lower() not in stopwords:
                    pricing_val = candidate
                    break

    # Pricing scope: determine if condition is applied across all line items or only item 1
    price_all_items = False
    all_items_patterns = [
        r"(?:for|to|on)\s*all\s*(?:the\s*)?(?:product\s*ids?|products|line\s*items?|items)",
        r"(?:done|repeat|add|apply|enter|same)\s*(?:this\s*)?(?:for\s*)?(?:all|each)\s*(?:the\s*)?(?:product\s*ids?|products|line\s*items?|items)",
        r"for\s*each\s*(?:the\s*)?(?:product\s*ids?|products|line\s*items?|items)",
        r"(?:each|all)\s*(?:product|item).*?(?:price\s*condition|pricing|ztaf)",
        r"(?:price\s*condition|pricing|ztaf).*?(?:each|all)\s*(?:product|item)",
        r"line\s*item\s*\d+.*?price\s*condition",
        r"(?:go\s*to|click\s*on)\s*product",
    ]
    if any(re.search(p, combined_corpus, re.IGNORECASE) for p in all_items_patterns):
        price_all_items = True
    else:
        pricing_mentions = len(re.findall(r"(?:price\s*condition|pricing\s*element|ZTAF)", combined_corpus, re.IGNORECASE))
        if pricing_mentions >= 2 and len(extracted_items) >= 2:
            if not re.search(r"price\s*condition.*?added\s*to\s*item\s*1\b", combined_corpus, re.IGNORECASE):
                price_all_items = True

    # Transaction Type extraction (prioritize AC text)
    ttype_val = None
    if ac_text:
        m_ttype = re.search(r"transaction\s*type\s*(?:as|is|:)?\s*['\"]?([a-zA-Z0-9_\-]+)", ac_text, re.IGNORECASE)
        if m_ttype and m_ttype.group(1).strip():
            ttype_val = m_ttype.group(1).strip()

    if not ttype_val:
        m_ttype2 = re.search(r"(?:select\s+)?transaction\s*type\s*(?:as|is|:)?\s*['\"]?([a-zA-Z0-9_\-]+)", combined_corpus, re.IGNORECASE)
        if m_ttype2 and m_ttype2.group(1).strip():
            ttype_val = m_ttype2.group(1).strip()

    if not ttype_val:
        ttype_val = "ZQDS"

    line_items = extract_sap_line_items(ac_text or combined_corpus)
    status_checks = extract_sap_status_checks(ac_text or combined_corpus)

    return {
        "desc_val": desc_val,
        "soldto_val": soldto_val,
        "prod_val": prod_val,
        "qty_val": qty_val,
        "duration_val": duration_val,
        "time_unit_val": time_unit_val,
        "pricing_val": pricing_val,
        "price_all_items": price_all_items,
        "ttype_val": ttype_val,
        "extracted_items": extracted_items,
        "line_items": line_items,
        "status_checks": status_checks,
    }


_Q = r"['\u2018\u2019\u201c\u201d\"`]"


def extract_sap_line_items(text: str) -> List[Dict[str, Any]]:
    """
    Parses structured 'Line Item N: Product ID <NAME> '<ID>', add Quantity X, Plant Y, ... 'Z100' with 100% ...,
    Add Price 450,000 to <ELEMENT> under Price Element' blocks from the acceptance criterion text.
    Returns one dict per line item; nothing is hardcoded - all values come from the AC text.
    """
    items: List[Dict[str, Any]] = []
    if not text:
        return items
    seg_re = re.compile(
        r"Line\s*Item\s*\d+\s*:(.*?)(?=Line\s*Item\s*\d+\s*:|Return\s+to\s+the\s+quotation|Save\s+the\s+Quotation|$)",
        re.IGNORECASE | re.DOTALL,
    )
    for m in seg_re.finditer(text):
        seg = m.group(1)
        m_pid = re.search(rf"{_Q}?\s*(\d{{6,12}})\s*{_Q}?", seg)
        if not m_pid:
            continue
        pid = m_pid.group(1)
        name = ""
        m_name = re.search(rf"Product\s*ID\s*(.*?)\s*{_Q}?\s*{pid}", seg, re.IGNORECASE | re.DOTALL)
        if m_name:
            name = re.sub(rf"{_Q}", "", m_name.group(1)).strip(" ,:-")
        m_qty = re.search(r"Quantity\s*(?:as|is|:|of)?\s*(\d+)", seg, re.IGNORECASE)
        m_plant = re.search(r"Plant\s*(?:as|is|:)?\s*([A-Z0-9]{3,5})\b", seg)
        conditions: List[Dict[str, str]] = []
        for cm in re.finditer(rf"{_Q}([A-Z][A-Z0-9]{{3}}){_Q}\s*with\s*([\d.,]+\s*%?)", seg):
            code, val = cm.group(1), cm.group(2).strip().replace(" ", "")
            if not any(c["code"] == code for c in conditions):
                conditions.append({"code": code, "value": val})
        for pm in re.finditer(r"Add\s*Price\s*([\d.,]+)\s*to\s*(.+?)\s*under\s*Price\s*Element", seg, re.IGNORECASE | re.DOTALL):
            el = re.sub(r"\s+", " ", pm.group(2)).strip(" '\u2018\u2019\"")
            conditions.append({"code": el, "value": pm.group(1).strip()})
        if not conditions:
            for cm_plain in re.finditer(r"(?:price\s*condition|pricing\s*element|condition\s*type)\s*(?:as|is|:)?\s*['\"\u2018\u2019]?([A-Z][A-Z0-9]{3})\b", seg, re.IGNORECASE):
                code = cm_plain.group(1).upper()
                if not any(c["code"] == code for c in conditions):
                    conditions.append({"code": code, "value": ""})
        items.append({
            "product_id": pid,
            "product_name": name,
            "quantity": m_qty.group(1) if m_qty else "1",
            "plant": m_plant.group(1) if m_plant else "",
            "conditions": conditions,
            "sales_item_details": bool(re.search(r"sales\s*item\s*details|go\s*to\s*product", seg, re.IGNORECASE)),
        })
    return items


def extract_sap_status_checks(text: str) -> Dict[str, str]:
    """Extracts 'verify the Status ...' expectations after Save / Release / Accept and the service contract target status."""
    checks: Dict[str, str] = {}
    if not text:
        return checks
    for m in re.finditer(r"verify\s+(?:that\s+)?(?:the\s+)?status\s*(?:is|:|as|=)?\s*([A-Za-z][A-Za-z ]*?)\s*(?:[\n\r.,;]|$)", text, re.IGNORECASE):
        status = m.group(1).strip()
        ctx = text[max(0, m.start() - 140): m.start()].lower()
        if "service contract" in ctx or "transaction" in ctx:
            checks.setdefault("service_contract_status", status)
        elif "accept" in ctx:
            checks.setdefault("status_after_accept", status)
        elif "release" in ctx:
            checks.setdefault("status_released", status)
        elif "save" in ctx:
            checks.setdefault("status_after_save", status)
    m_sc = re.search(
        rf"service\s*contract.*?status\s*(?:from\s*)?{_Q}?\s*\w+\s*{_Q}?\s*to\s*{_Q}?\s*([A-Za-z ]+?)\s*(?:{_Q}|[\n\r.,;]|$)",
        text,
        re.IGNORECASE | re.DOTALL,
    )
    if m_sc:
        checks["service_contract_status"] = m_sc.group(1).strip()
    elif re.search(r"service\s*contract", text, re.IGNORECASE):
        checks.setdefault("service_contract_status", "Completed")
    return checks


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")


def build_sap_quotation_test_data(params: Dict[str, Any]) -> Dict[str, str]:
    """Builds the dynamic test_data dictionary referenced by ${key} placeholders in generated steps."""
    td: Dict[str, str] = {
        "transaction_type": params.get("ttype_val", ""),
        "quotation_description": params.get("desc_val", ""),
        "sold_to_party": params.get("soldto_val", ""),
        "term_duration": params.get("duration_val", ""),
        "term_time_unit": params.get("time_unit_val", ""),
    }
    for i, it in enumerate(params.get("line_items") or [], 1):
        td[f"item{i}_product_id"] = it["product_id"]
        td[f"item{i}_product_name"] = it.get("product_name", "")
        td[f"item{i}_quantity"] = it.get("quantity", "1")
        td[f"item{i}_plant"] = it.get("plant", "")
        for j, c in enumerate(it.get("conditions") or [], 1):
            td[f"item{i}_cond{j}_type"] = c["code"]
            td[f"item{i}_cond{j}_value"] = c["value"]
    td.update(params.get("status_checks") or {})
    return {k: v for k, v in td.items() if v not in (None, "")}


def build_sales_item_details_steps(line_items: List[Dict[str, Any]], start_step_number: int = 17) -> List[TestStep]:
    """
    Verified Service Quotation line item flow (Items table + Sales Item Details), fully placeholder-driven:
      Product ID + Enter -> Product Name -> Quantity -> Plant (Items table) -> pencil (edit) icon ->
      Price Details -> [Add -> condition type -> value] per condition -> Back -> Items.
    """
    steps: List[TestStep] = []
    n = start_step_number

    def add(**kw):
        nonlocal n
        steps.append(TestStep(step_number=n, **kw))
        n += 1

    for i, it in enumerate(line_items, 1):
        prod_sel = (
            f"[id*='btadmini_table[{i}].ordered_prod'], input[name*='btadmini_table[{i}].ordered_prod'], "
            f"[data-help-id*='I_ordered_prod:R_{i}'], [id*='table[{i}]'][id*='ordered_prod']"
        )
        pid, pname = f"${{item{i}_product_id}}", f"${{item{i}_product_name}}"
        add(action=ActionType.FILL, locator_strategy=LocatorStrategy.CSS, selector_value=prod_sel, input_value=pid,
            description=f"Enter Product ID {pid} ({pname}) for item {i}")
        add(action=ActionType.FILL, locator_strategy=LocatorStrategy.CSS, selector_value=prod_sel, input_value="Enter",
            description=f"Press Enter to commit Product ID {pid} for item {i}")
        add(action=ActionType.CLICK, locator_strategy=LocatorStrategy.CSS,
            selector_value=(f"[id*='btadmini_table[{i}].description'] a, [id*='btadmini_table[{i}].ordered_prod'] a, "
                            f"text='{pname}', text='{pid}', [id*='btadmini_table[{i}]'] a"),
            description=f"Click Product Name {pname} to view item {i} details")
        add(action=ActionType.FILL, locator_strategy=LocatorStrategy.ROLE, role_name="textbox", selector_value="Quantity:",
            input_value=f"${{item{i}_quantity}}", description=f"Enter Quantity ${{item{i}_quantity}} for item {i} in item details")
        if it.get("plant"):
            add(action=ActionType.FILL, locator_strategy=LocatorStrategy.CSS,
                selector_value=f"input[id$='btadmini_table[{i}].plant'], [id*='btadmini_table[{i}]'][id*='plant' i]",
                input_value=f"${{item{i}_plant}}", description=f"Enter Plant ${{item{i}_plant}} in Items table for item {i}")
        if it.get("conditions"):
            add(action=ActionType.CLICK, locator_strategy=LocatorStrategy.CSS,
                selector_value=f"[id*='btadmini_table[{i}].thtmlb_oca.EDIT']",
                description=f"Click pencil (edit) icon next to product name to open Sales Item Details for item {i}")
            add(action=ActionType.CLICK, locator_strategy=LocatorStrategy.ROLE, role_name="option", selector_value="Price Details",
                description=f"Open Price Details tab for item {i}")
            for j, _c in enumerate(it["conditions"], 1):
                ct, cv = f"${{item{i}_cond{j}_type}}", f"${{item{i}_cond{j}_value}}"
                add(action=ActionType.CLICK, locator_strategy=LocatorStrategy.ROLE, role_name="button", selector_value="Add",
                    description=f"Click Add Pricing Element button for {ct} on item {i}")
                add(action=ActionType.CLICK, locator_strategy=LocatorStrategy.TEXT, selector_value=ct,
                    description=f"Select condition type {ct} from popup for item {i}")
                if _c.get("value"):
                    add(action=ActionType.FILL, locator_strategy=LocatorStrategy.ROLE, role_name="textbox", selector_value=f"{ct} rate:",
                        input_value=cv, description=f"Enter rate '{cv}' for condition {ct} on item {i}")
        add(action=ActionType.CLICK, locator_strategy=LocatorStrategy.ROLE, role_name="button", selector_value="Back",
            description=f"Click Back to return to quotation from item {i}")
        add(action=ActionType.CLICK, locator_strategy=LocatorStrategy.ROLE, role_name="option", selector_value="Items",
            description=f"Open Items tab after item {i}")
    return steps


def build_lifecycle_with_status_steps(status_checks: Dict[str, str], start_step_number: int = 1) -> List[TestStep]:
    """Save -> verify status, Edit -> Released -> Save -> verify, Accept -> verify (only checks present in the AC are added)."""
    base = build_service_quotation_lifecycle_steps(start_step_number)
    save1, edit, lc_dd, released, save2, accept = base
    if status_checks.get("status_released"):
        released.selector_value = "${status_released}"
        released.description = "Change status to ${status_released}"

    def verify(key: str, when: str) -> List[TestStep]:
        if not status_checks.get(key):
            return []
        return [TestStep(step_number=1, action=ActionType.ASSERT_TEXT, locator_strategy=LocatorStrategy.CSS,
                         selector_value="body", expected_value=f"${{{key}}}",
                         description=f"Verify Status is ${{{key}}} {when}")]

    steps = ([save1] + verify("status_after_save", "after Save") + [edit, lc_dd, released, save2] +
             verify("status_released", "after Save") + [accept] + verify("status_after_accept", "after Accept"))
    for k, s in enumerate(steps, start_step_number):
        s.step_number = k
    return steps


def placeholder_header_params(params: Dict[str, Any]) -> Dict[str, Any]:
    """Returns a params copy whose header values are ${key} placeholders bound to build_sap_quotation_test_data keys."""
    ph = dict(params)
    ph.update({
        "include_dates": params.get("ttype_val", "ZQDS").strip().upper() != "ZQDV",
        "ttype_val": "${transaction_type}",
        "desc_val": "${quotation_description}",
        "soldto_val": "${sold_to_party}",
        "duration_val": "${term_duration}",
        "time_unit_val": "${term_time_unit}",
    })
    return ph


def build_sap_login_steps(
    target_url: str,
    username: Optional[str] = None,
    password: Optional[str] = None,
) -> List[TestStep]:
    """Generates standard deterministic SAP Logon steps (Steps 1-5)."""
    user_val = username if username is not None else (settings.sap_username or "MYRAR1").strip()
    pwd_val = password if password is not None else (settings.sap_password or "Pass23#$").strip()

    return [
        TestStep(
            step_number=1,
            action=ActionType.NAVIGATE,
            input_value=target_url,
            description="Open SAP Fiori Logon screen",
        ),
        TestStep(
            step_number=2,
            action=ActionType.FILL,
            locator_strategy=LocatorStrategy.CSS,
            selector_value="#USERNAME_FIELD-inner",
            input_value=user_val,
            description="Enter SAP username",
        ),
        TestStep(
            step_number=3,
            action=ActionType.FILL,
            locator_strategy=LocatorStrategy.CSS,
            selector_value="#PASSWORD_FIELD-inner",
            input_value=pwd_val,
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


def build_sap_logoff_steps(start_step_number: int = 1) -> List[TestStep]:
    """Generates standard deterministic SAP Logoff steps (4 steps)."""
    return [
        TestStep(
            step_number=start_step_number,
            action=ActionType.CLICK,
            locator_strategy=LocatorStrategy.CSS,
            selector_value="#userActionsMenuHeaderButton, #meAreaHeaderButton",
            description="Click User Profile Avatar Menu",
        ),
        TestStep(
            step_number=start_step_number + 1,
            action=ActionType.CLICK,
            locator_strategy=LocatorStrategy.CSS,
            selector_value="button:has-text('Sign Out'), text='Sign Out'",
            description="Click Sign Out",
        ),
        TestStep(
            step_number=start_step_number + 2,
            action=ActionType.CLICK,
            locator_strategy=LocatorStrategy.CSS,
            selector_value="button:has-text('OK'), text='OK'",
            description="Confirm Sign Out dialog",
        ),
        TestStep(
            step_number=start_step_number + 3,
            action=ActionType.ASSERT_TEXT,
            locator_strategy=LocatorStrategy.CSS,
            selector_value="body",
            expected_value="logged off",
            description="Verify returned to Logoff screen",
        ),
    ]


def build_service_quotation_header_steps(
    params: Dict[str, Any],
    target_url: str,
    username: Optional[str] = None,
    password: Optional[str] = None,
    include_dates: Optional[bool] = None,
) -> List[TestStep]:
    """Generates initial Service Quotation navigation, header, and dates steps (Steps 1-16 or Steps 1-12 without dates)."""
    login_steps = build_sap_login_steps(target_url, username=username, password=password)
    ttype_val = params.get("ttype_val", "ZQDS")
    desc_val = params.get("desc_val", "RAR Test")
    soldto_val = params.get("soldto_val", "Brugmann Hospital")
    duration_val = params.get("duration_val", "1")
    time_unit_val = params.get("time_unit_val", "Year")

    # Dates tab is omitted for ZQDV (CE-Direct Sales) as this transaction type
    # routes directly from Sold-To Party to Items without a header Dates tab.
    if include_dates is None:
        if "include_dates" in params:
            include_dates = bool(params["include_dates"])
        else:
            include_dates = (ttype_val.strip().upper() != "ZQDV")

    flow_steps = [
        TestStep(
            step_number=6,
            action=ActionType.CLICK,
            locator_strategy=LocatorStrategy.TEXT,
            selector_value="Manage Service Quotations",
            description="Click Manage Service Quotations tile",
        ),
        TestStep(
            step_number=7,
            action=ActionType.CLICK,
            locator_strategy=LocatorStrategy.CSS,
            selector_value="button:has-text('New Create'), button:has-text('Create'), [title*='Create'], #btnCreate",
            description="Click Create button on Service Quotations worklist",
        ),
        TestStep(
            step_number=8,
            action=ActionType.CLICK,
            locator_strategy=LocatorStrategy.TEXT,
            selector_value=ttype_val,
            description=f"Select Transaction Type {ttype_val} from popup",
        ),
        TestStep(
            step_number=9,
            action=ActionType.FILL,
            locator_strategy=LocatorStrategy.ROLE,
            role_name="textbox",
            selector_value="Description:",
            input_value=desc_val,
            description=f"Enter Quotation Description '{desc_val}'",
        ),
        TestStep(
            step_number=10,
            action=ActionType.FILL,
            locator_strategy=LocatorStrategy.ROLE,
            role_name="textbox",
            selector_value="Sold-To Party:",
            input_value=soldto_val,
            description=f"Enter Sold-to Party customer '{soldto_val}'",
        ),
        TestStep(
            step_number=11,
            action=ActionType.FILL,
            locator_strategy=LocatorStrategy.ROLE,
            role_name="textbox",
            selector_value="Sold-To Party:",
            input_value="Enter",
            description="Press Enter to commit Sold-to Party",
        ),
    ]

    if include_dates:
        flow_steps.extend([
            TestStep(
                step_number=12,
                action=ActionType.CLICK,
                locator_strategy=LocatorStrategy.ROLE,
                role_name="option",
                selector_value="Dates",
                description="Open Dates tab",
            ),
            TestStep(
                step_number=13,
                action=ActionType.FILL,
                locator_strategy=LocatorStrategy.CSS,
                selector_value="#C16_W64_V65_DatesTable_bottom_div tr:has-text('Term of Quotation') input, #C16_W64_V65_DatesTable_bottom_div tr:has-text('Term of Quotation') [role='textbox']",
                input_value=duration_val,
                description=f"Enter Term of Quotation Duration as {duration_val}",
            ),
            TestStep(
                step_number=14,
                action=ActionType.CLICK,
                locator_strategy=LocatorStrategy.CSS,
                selector_value="[id='C16_W64_V65_btdate_table[4].time_unit-btn']",
                description="Open Time Unit dropdown",
            ),
            TestStep(
                step_number=15,
                action=ActionType.CLICK,
                locator_strategy=LocatorStrategy.ROLE,
                role_name="link",
                selector_value=time_unit_val,
                description=f"Select Time Unit {time_unit_val}",
            ),
            TestStep(
                step_number=16,
                action=ActionType.CLICK,
                locator_strategy=LocatorStrategy.ROLE,
                role_name="option",
                selector_value="Items",
                description="Open Items tab",
            ),
        ])
    else:
        flow_steps.append(
            TestStep(
                step_number=12,
                action=ActionType.CLICK,
                locator_strategy=LocatorStrategy.ROLE,
                role_name="option",
                selector_value="Items",
                description="Open Items tab",
            )
        )

    return login_steps + flow_steps


def build_service_quotation_item_steps(
    extracted_items: List[Tuple[str, str]],
    start_step_number: int = 17,
) -> List[TestStep]:
    """Generates row-isolated multi-product line item input steps."""
    cur_snum = start_step_number
    steps: List[TestStep] = []

    for idx, (p_id, p_qty) in enumerate(extracted_items, start=1):
        if idx > 1:
            prod_sel = (
                f"[id*='btadmini_table[{idx}].ordered_prod'], "
                f"input[name*='btadmini_table[{idx}].ordered_prod'], "
                f"[data-help-id*='I_ordered_prod:R_{idx}'], "
                f"[id='C13_W49_V50_V54_btadmini_table[{idx}].ordered_prod']"
            )
            qty_sel = (
                f"input[id*='btadmini_table[{idx}].quantity'], "
                f"input[id*='table[{idx}]'][id*='quantity'], "
                f"input[name*='btadmini_table[{idx}].quantity'], "
                f"input[data-help-id*='I_quantity:R_{idx}'], "
                f"[id='C13_W49_V50_V54_btadmini_table[{idx}].quantity']"
            )
        else:
            prod_sel = (
                "[id*='btadmini_table[1].ordered_prod'], "
                "[id*='table[1]'][id*='ordered_prod'], "
                "input[name*='btadmini_table[1].ordered_prod'], "
                "[data-help-id*='I_ordered_prod:R_1'], "
                "[id*='ordered_prod'], "
                "[id='C13_W49_V50_V54_btadmini_table[1].ordered_prod']"
            )
            qty_sel = (
                "input[id*='btadmini_table[1].quantity'], "
                "input[id*='table[1]'][id*='quantity'], "
                "input[name*='btadmini_table[1].quantity'], "
                "input[data-help-id*='I_quantity:R_1'], "
                "[id='C13_W49_V50_V54_btadmini_table[1].quantity'], "
                "input[id*='quantity']:not([readonly]), "
                "input[aria-label*='Quantity' i]"
            )

        steps.extend([
            TestStep(
                step_number=cur_snum,
                action=ActionType.FILL,
                locator_strategy=LocatorStrategy.CSS,
                selector_value=prod_sel,
                input_value=p_id,
                description=f"Enter Product ID {p_id} for item {idx}",
            ),
            TestStep(
                step_number=cur_snum + 1,
                action=ActionType.FILL,
                locator_strategy=LocatorStrategy.CSS,
                selector_value=qty_sel,
                input_value=p_qty,
                description=f"Enter Quantity {p_qty} for item {idx}",
            ),
            TestStep(
                step_number=cur_snum + 2,
                action=ActionType.FILL,
                locator_strategy=LocatorStrategy.CSS,
                selector_value=qty_sel,
                input_value="Enter",
                description=f"Press Enter to commit line item {idx}",
            ),
        ])
        cur_snum += 3

    return steps


def build_service_quotation_pricing_steps(
    pricing_val: str = "ZTAF",
    start_step_number: int = 1,
) -> List[TestStep]:
    """Generates pricing condition configuration steps on item 1."""
    return [
        TestStep(
            step_number=start_step_number,
            action=ActionType.CLICK,
            locator_strategy=LocatorStrategy.TEXT,
            selector_value="VELLYS SATELLITE STATION SKU1",
            description="Click Product Name to view item 1 details",
        ),
        TestStep(
            step_number=start_step_number + 1,
            action=ActionType.CLICK,
            locator_strategy=LocatorStrategy.ROLE,
            role_name="option",
            selector_value="Price Details",
            description="Open Price Details tab for item 1",
        ),
        TestStep(
            step_number=start_step_number + 2,
            action=ActionType.CLICK,
            locator_strategy=LocatorStrategy.ROLE,
            role_name="button",
            selector_value="Add",
            description="Click Add Pricing Element button for item 1",
        ),
        TestStep(
            step_number=start_step_number + 3,
            action=ActionType.CLICK,
            locator_strategy=LocatorStrategy.TEXT,
            selector_value=pricing_val,
            description=f"Select condition type {pricing_val} from popup",
        ),
        TestStep(
            step_number=start_step_number + 4,
            action=ActionType.CLICK,
            locator_strategy=LocatorStrategy.ROLE,
            role_name="button",
            selector_value="Back",
            description="Click Back to return to quotation",
        ),
    ]


def build_service_quotation_item_pricing_steps(
    item_index: int = 1,
    pricing_val: str = "ZTAF",
    start_step_number: int = 1,
) -> List[TestStep]:
    """Generates pricing condition configuration steps for a specific line item index (1..N)."""
    if item_index == 1:
        click_selector = (
            "[id*='btadmini_table[1].description'] a, "
            "[id*='btadmini_table[1].ordered_prod'] a, "
            "text='VELLYS SATELLITE STATION SKU1', "
            "[id*='btadmini_table[1]'] a"
        )
        desc = "Click Product Name to view item 1 details"
    else:
        click_selector = (
            f"[id*='btadmini_table[{item_index}].description'] a, "
            f"[id*='btadmini_table[{item_index}].ordered_prod'] a, "
            f"[id*='btadmini_table[{item_index}]'] a"
        )
        desc = f"Click Product Name to view item {item_index} details"

    return [
        TestStep(
            step_number=start_step_number,
            action=ActionType.CLICK,
            locator_strategy=LocatorStrategy.CSS,
            selector_value=click_selector,
            description=desc,
        ),
        TestStep(
            step_number=start_step_number + 1,
            action=ActionType.CLICK,
            locator_strategy=LocatorStrategy.ROLE,
            role_name="option",
            selector_value="Price Details",
            description=f"Open Price Details tab for item {item_index}",
        ),
        TestStep(
            step_number=start_step_number + 2,
            action=ActionType.CLICK,
            locator_strategy=LocatorStrategy.ROLE,
            role_name="button",
            selector_value="Add",
            description=f"Click Add Pricing Element button for item {item_index}",
        ),
        TestStep(
            step_number=start_step_number + 3,
            action=ActionType.CLICK,
            locator_strategy=LocatorStrategy.TEXT,
            selector_value=pricing_val,
            description=f"Select condition type {pricing_val} from popup for item {item_index}",
        ),
        TestStep(
            step_number=start_step_number + 4,
            action=ActionType.CLICK,
            locator_strategy=LocatorStrategy.ROLE,
            role_name="button",
            selector_value="Back",
            description=f"Click Back to return to quotation from item {item_index}",
        ),
        TestStep(
            step_number=start_step_number + 5,
            action=ActionType.CLICK,
            locator_strategy=LocatorStrategy.ROLE,
            role_name="option",
            selector_value="Items",
            description=f"Open Items tab after item {item_index}",
        ),
    ]


def build_service_quotation_lifecycle_steps(start_step_number: int = 1) -> List[TestStep]:
    """Generates Save, Edit, Released, Save, and Accept quotation steps."""
    return [
        TestStep(
            step_number=start_step_number,
            action=ActionType.CLICK,
            locator_strategy=LocatorStrategy.ROLE,
            role_name="button",
            selector_value="Save (Ctrl+S)",
            description="Click Save button to persist quotation",
        ),
        TestStep(
            step_number=start_step_number + 1,
            action=ActionType.CLICK,
            locator_strategy=LocatorStrategy.CSS,
            selector_value="button:has-text('Edit'), a:has-text('Edit'), [title*='Edit'], [aria-label*='Edit']",
            description="Click Edit button",
        ),
        TestStep(
            step_number=start_step_number + 2,
            action=ActionType.CLICK,
            locator_strategy=LocatorStrategy.CSS,
            selector_value="#C9_W36_V39_V40_btadminh_lcstatus-btn, [id*='btadminh_lcstatus-btn']",
            description="Open Lifecycle Status dropdown",
        ),
        TestStep(
            step_number=start_step_number + 3,
            action=ActionType.CLICK,
            locator_strategy=LocatorStrategy.ROLE,
            role_name="link",
            selector_value="Released",
            description="Change status to Released",
        ),
        TestStep(
            step_number=start_step_number + 4,
            action=ActionType.CLICK,
            locator_strategy=LocatorStrategy.ROLE,
            role_name="button",
            selector_value="Save (Ctrl+S)",
            description="Click Save button to persist Released status",
        ),
        TestStep(
            step_number=start_step_number + 5,
            action=ActionType.CLICK,
            locator_strategy=LocatorStrategy.CSS,
            selector_value="button:has-text('Accept'), [title*='Accept'], a:has-text('Accept'), [role='menuitem']:has-text('Accept')",
            description="Click Accept quotation button",
        ),
    ]


def build_service_quotation_history_steps(start_step_number: int = 1) -> List[TestStep]:
    """Generates steps to capture Operational Document / Transaction ID from Transaction History."""
    return [
        TestStep(
            step_number=start_step_number,
            action=ActionType.CLICK,
            locator_strategy=LocatorStrategy.TEXT,
            selector_value="Transaction History",
            description="Click Transaction History tab",
        ),
        TestStep(
            step_number=start_step_number + 1,
            action=ActionType.ASSERT_TEXT,
            locator_strategy=LocatorStrategy.CSS,
            selector_value="body",
            expected_value="Transaction",
            description="Capture Operational Document / Transaction ID as test evidence",
        ),
    ]


def build_service_quotation_drilldown_item_steps(
    extracted_items: List[Tuple[str, str]],
    pricing_val: str = "ZTAF",
    start_step_number: int = 17,
) -> List[TestStep]:
    """
    Generates procedural line item steps:
    For each line item (1..N):
    1. Enters Product ID into the Items overview table.
    2. Presses Enter to commit Product ID and generate product link.
    3. (Does NOT enter quantity in the table) Clicks into the item details screen (Sales Item Details).
    4. Enters Quantity on the Sales Item Details page.
    5. Navigates to Price Details tab.
    6. Adds pricing condition (e.g. ZTAF).
    7. Clicks Back to return to the quotation.
    8. Clicks the Items tab so the table and all rows remain visible for next item.
    """
    cur_snum = start_step_number
    steps: List[TestStep] = []

    for idx, (p_id, p_qty) in enumerate(extracted_items, start=1):
        if idx > 1:
            prod_sel = (
                f"[id*='btadmini_table[{idx}].ordered_prod'], "
                f"input[name*='btadmini_table[{idx}].ordered_prod'], "
                f"[data-help-id*='I_ordered_prod:R_{idx}'], "
                f"[id='C13_W49_V50_V54_btadmini_table[{idx}].ordered_prod']"
            )
            item_link_sel = (
                f"[id*='btadmini_table[{idx}].description'] a, "
                f"[id*='btadmini_table[{idx}].ordered_prod'] a, "
                f"text='{p_id}', "
                f"[id*='btadmini_table[{idx}]'] a"
            )
        else:
            prod_sel = (
                "[id*='btadmini_table[1].ordered_prod'], "
                "[id*='table[1]'][id*='ordered_prod'], "
                "input[name*='btadmini_table[1].ordered_prod'], "
                "[data-help-id*='I_ordered_prod:R_1'], "
                "[id*='ordered_prod'], "
                "[id='C13_W49_V50_V54_btadmini_table[1].ordered_prod']"
            )
            item_link_sel = (
                "[id*='btadmini_table[1].description'] a, "
                "[id*='btadmini_table[1].ordered_prod'] a, "
                f"text='{p_id}', "
                "text='VELLYS SATELLITE STATION SKU1', "
                "[id*='btadmini_table[1]'] a"
            )

        # 1. Enter Product ID in table row
        steps.append(
            TestStep(
                step_number=cur_snum,
                action=ActionType.FILL,
                locator_strategy=LocatorStrategy.CSS,
                selector_value=prod_sel,
                input_value=p_id,
                description=f"Enter Product ID {p_id} for item {idx}",
            )
        )
        cur_snum += 1

        # 2. Press Enter to commit row & generate clickable link
        steps.append(
            TestStep(
                step_number=cur_snum,
                action=ActionType.FILL,
                locator_strategy=LocatorStrategy.CSS,
                selector_value=prod_sel,
                input_value="Enter",
                description=f"Press Enter to commit Product ID {p_id} for item {idx}",
            )
        )
        cur_snum += 1

        # 3. Click Product Name to open Sales Item Details screen
        steps.append(
            TestStep(
                step_number=cur_snum,
                action=ActionType.CLICK,
                locator_strategy=LocatorStrategy.CSS,
                selector_value=item_link_sel,
                description=f"Click Product Name to view item {idx} details",
            )
        )
        cur_snum += 1

        # 4. Enter Quantity on item details screen (Sales Item Details)
        steps.append(
            TestStep(
                step_number=cur_snum,
                action=ActionType.FILL,
                locator_strategy=LocatorStrategy.CSS,
                selector_value="input[id*='quantity']:not([readonly]), input[name*='quantity'], input[aria-label*='Quantity' i], [aria-label*='Quantity:' i], input[title*='Quantity' i]",
                input_value=p_qty,
                description=f"Enter Quantity {p_qty} for item {idx} in item details",
            )
        )
        cur_snum += 1

        # 5. Open Price Details tab for item
        steps.append(
            TestStep(
                step_number=cur_snum,
                action=ActionType.CLICK,
                locator_strategy=LocatorStrategy.ROLE,
                role_name="option",
                selector_value="Price Details",
                description=f"Open Price Details tab for item {idx}",
            )
        )
        cur_snum += 1

        # 6. Click Add Pricing Element button
        steps.append(
            TestStep(
                step_number=cur_snum,
                action=ActionType.CLICK,
                locator_strategy=LocatorStrategy.ROLE,
                role_name="button",
                selector_value="Add",
                description=f"Click Add Pricing Element button for item {idx}",
            )
        )
        cur_snum += 1

        # 7. Select condition type (e.g. ZTAF)
        steps.append(
            TestStep(
                step_number=cur_snum,
                action=ActionType.CLICK,
                locator_strategy=LocatorStrategy.TEXT,
                selector_value=pricing_val,
                description=f"Select condition type {pricing_val} from popup for item {idx}",
            )
        )
        cur_snum += 1

        # 8. Click Back button to return to quotation
        steps.append(
            TestStep(
                step_number=cur_snum,
                action=ActionType.CLICK,
                locator_strategy=LocatorStrategy.ROLE,
                role_name="button",
                selector_value="Back",
                description=f"Click Back to return to quotation from item {idx}",
            )
        )
        cur_snum += 1

        # 9. Click Items tab to return to the items overview table (critical for next item or document review)
        steps.append(
            TestStep(
                step_number=cur_snum,
                action=ActionType.CLICK,
                locator_strategy=LocatorStrategy.ROLE,
                role_name="option",
                selector_value="Items",
                description=f"Open Items tab after item {idx}",
            )
        )
        cur_snum += 1

    return steps


def build_service_quotation_steps(
    params: Dict[str, Any],
    target_url: str,
    capture_transaction_history: bool = True,
    include_logoff: bool = True,
    username: Optional[str] = None,
    password: Optional[str] = None,
    include_dates: Optional[bool] = None,
) -> List[TestStep]:
    """
    Builds a full Service Quotation test case (Header -> Items -> Pricing -> Lifecycle -> History -> Logoff).
    Used as TC-01 when split into multi-AC suites.
    """
    # Structured 'Line Item N:' ACs -> verified, placeholder-driven Sales Item Details flow (values live in test_data)
    if params.get("line_items"):
        steps = build_service_quotation_header_steps(
            placeholder_header_params(params),
            target_url,
            username=username,
            password=password,
            include_dates=include_dates,
        )
        steps.extend(build_sales_item_details_steps(params["line_items"], start_step_number=len(steps) + 1))
        steps.extend(build_lifecycle_with_status_steps(params.get("status_checks") or {}, start_step_number=len(steps) + 1))
        if capture_transaction_history:
            steps.extend(build_service_quotation_history_steps(start_step_number=len(steps) + 1))
            if (params.get("status_checks") or {}).get("service_contract_status"):
                for d in (
                    dict(action=ActionType.CLICK, locator_strategy=LocatorStrategy.CSS, selector_value="tr:has-text('Service Contract') a",
                         description="Click Transaction hyperlink for Service Contract in Transaction History"),
                    dict(action=ActionType.CLICK, locator_strategy=LocatorStrategy.CSS,
                         selector_value="button:has-text('Edit'), a:has-text('Edit'), [title*='Edit'], [aria-label*='Edit']",
                         description="Click Edit button on Service contract"),
                    dict(action=ActionType.CLICK, locator_strategy=LocatorStrategy.CSS,
                         selector_value="[id*='btadminh_lcstatus-btn'], [id*='lcstatus-btn']", description="Open Service contract Status dropdown"),
                    dict(action=ActionType.CLICK, locator_strategy=LocatorStrategy.ROLE, role_name="link", selector_value="${service_contract_status}",
                         description="Change Service contract Status from 'Open' to '${service_contract_status}'"),
                    dict(action=ActionType.CLICK, locator_strategy=LocatorStrategy.ROLE, role_name="button", selector_value="Save (Ctrl+S)",
                         description="Click Save button to persist status on Service contract"),
                    dict(action=ActionType.ASSERT_TEXT, locator_strategy=LocatorStrategy.CSS, selector_value="body",
                         expected_value="${service_contract_status}", description="Verify Service contract Status is ${service_contract_status}"),
                    dict(action=ActionType.CLICK, locator_strategy=LocatorStrategy.CSS, selector_value="#backBtn",
                         description="Click SAP Back button (< left to SAP logo) to navigate back to Transaction History"),
                    dict(action=ActionType.ASSERT_TEXT, locator_strategy=LocatorStrategy.CSS, selector_value="body",
                         expected_value="Transaction", description="Capture the Transaction ID from Transaction History to use in next test cases"),
                ):
                    steps.append(TestStep(step_number=len(steps) + 1, **d))
        if include_logoff:
            steps.extend(build_sap_logoff_steps(start_step_number=len(steps) + 1))
        for idx, s in enumerate(steps, 1):
            s.step_number = idx
        return steps

    steps = build_service_quotation_header_steps(
        params,
        target_url,
        username=username,
        password=password,
        include_dates=include_dates,
    )

    items = params.get("extracted_items") or [(params.get("prod_val", "45157510101"), params.get("qty_val", "1"))]
    pricing_val = params.get("pricing_val", "ZTAF")
    price_all_items = params.get("price_all_items", False)

    if price_all_items:
        drilldown_steps = build_service_quotation_drilldown_item_steps(
            extracted_items=items,
            pricing_val=pricing_val,
            start_step_number=len(steps) + 1,
        )
        steps.extend(drilldown_steps)
    else:
        item_steps = build_service_quotation_item_steps(items, start_step_number=len(steps) + 1)
        steps.extend(item_steps)
        pricing_steps = build_service_quotation_pricing_steps(pricing_val, start_step_number=len(steps) + 1)
        steps.extend(pricing_steps)

    lifecycle_steps = build_service_quotation_lifecycle_steps(start_step_number=len(steps) + 1)
    steps.extend(lifecycle_steps)

    if capture_transaction_history:
        history_steps = build_service_quotation_history_steps(start_step_number=len(steps) + 1)
        steps.extend(history_steps)

    if include_logoff:
        logoff_steps = build_sap_logoff_steps(start_step_number=len(steps) + 1)
        steps.extend(logoff_steps)

    for idx, s in enumerate(steps, 1):
        s.step_number = idx
    return steps


def build_revenue_contract_steps(
    target_url: str,
    operational_doc: str = "${OPERATIONAL_DOCUMENT}",
    mrc_url: Optional[str] = None,
    username: Optional[str] = None,
    password: Optional[str] = None,
    include_logoff: bool = True,
) -> List[TestStep]:
    """
    Builds dedicated Manage Revenue Contracts verification steps.
    Used as TC-02 with dynamic Operational Document handoff.
    """
    login_steps = build_sap_login_steps(target_url, username=username, password=password)
    target_mrc = mrc_url or DEFAULT_MRC_URL

    val_help_sel = (
        "[id*='RevenueAccountingContract-vhi'], "
        "[id*='RevenueContract-vhi'], "
        "div:has(> label:has-text('Revenue Contract')) .sapMInputValHelpInner, "
        "label:has-text('Revenue Contract') ~ div .sapMInputValHelpInner, "
        "[id='fin.rar.manage.contract::sap.suite.ui.generic.template.ListReport.view.ListReport::C_RAContrWithPostedBalanceTP--listReportFilter-filterItemControl_BASIC-RevenueAccountingContract-vhi']"
    )

    flow_steps = [
        TestStep(
            step_number=6,
            action=ActionType.NAVIGATE,
            input_value=target_mrc,
            description="Navigate directly to Manage Revenue Contracts application",
        ),
        TestStep(
            step_number=7,
            action=ActionType.CLICK,
            locator_strategy=LocatorStrategy.CSS,
            selector_value=val_help_sel,
            description="Click Revenue Accounting Contract Value Help",
        ),
        TestStep(
            step_number=8,
            action=ActionType.FILL,
            locator_strategy=LocatorStrategy.ROLE,
            role_name="textbox",
            selector_value="Operational Document:",
            input_value=operational_doc,
            description="Enter captured Operational Document into Operational Document:",
        ),
        TestStep(
            step_number=9,
            action=ActionType.FILL,
            locator_strategy=LocatorStrategy.ROLE,
            role_name="textbox",
            selector_value="Operational Document:",
            input_value="Enter",
            description="Press 'Enter' into Operational Document:",
        ),
        TestStep(
            step_number=10,
            action=ActionType.CLICK,
            locator_strategy=LocatorStrategy.TEXT,
            selector_value="Selection column",
            description="Click Selection column",
        ),
        TestStep(
            step_number=11,
            action=ActionType.CLICK,
            locator_strategy=LocatorStrategy.ROLE,
            role_name="dialog",
            selector_value="Revenue Contract",
            description="Click Revenue Contract dialog",
        ),
        TestStep(
            step_number=12,
            action=ActionType.CLICK,
            locator_strategy=LocatorStrategy.ROLE,
            role_name="button",
            selector_value="OK",
            description="Click OK",
        ),
        TestStep(
            step_number=13,
            action=ActionType.CLICK,
            locator_strategy=LocatorStrategy.ROLE,
            role_name="button",
            selector_value="Go",
            description="Click Go",
        ),
        TestStep(
            step_number=14,
            action=ActionType.ASSERT_TEXT,
            locator_strategy=LocatorStrategy.CSS,
            selector_value="body",
            expected_value="Revenue Contract",
            description="Verify Revenue Contract loaded",
        ),
        TestStep(
            step_number=15,
            action=ActionType.CLICK,
            locator_strategy=LocatorStrategy.CSS,
            selector_value="a:has-text('Revenue Contract'), tr[data-sap-ui-rowindex='0'] a, td a[id*='RevenueContract']",
            description="Click on Revenue Contract to view details",
        ),
    ]

    all_steps = login_steps + flow_steps
    if include_logoff:
        logoff_steps = build_sap_logoff_steps(start_step_number=len(all_steps) + 1)
        all_steps.extend(logoff_steps)

    for idx, s in enumerate(all_steps, 1):
        s.step_number = idx
    return all_steps


def extract_outbound_delivery_parameters(ac_text: str) -> Dict[str, str]:
    """Dynamically extracts Outbound Delivery parameters (Plant/Shipping Point, Storage Location, Picking Quantity) from AC text."""
    plant_val = "BEV8"
    storage_loc_val = "6020"
    picking_qty_val = "1"
    if ac_text:
        m_plant = re.search(rf"(?:plant|shipping\s*point)\s*(?:as|is|:)?\s*{_Q}?\s*([A-Z0-9]{{3,5}})\s*{_Q}?", ac_text, re.IGNORECASE)
        if m_plant:
            plant_val = m_plant.group(1).strip().upper()
        m_sloc = re.search(rf"storage\s*location\s*(?:as|is|:)?\s*{_Q}?\s*([A-Z0-9]{{3,6}})\s*{_Q}?", ac_text, re.IGNORECASE)
        if m_sloc:
            storage_loc_val = m_sloc.group(1).strip()
        m_pqty = re.search(rf"picking\s*quantity\s*(?:as|is|:)?\s*{_Q}?\s*(\d+)\s*{_Q}?", ac_text, re.IGNORECASE)
        if m_pqty:
            picking_qty_val = m_pqty.group(1).strip()
    return {
        "plant": plant_val,
        "order_number": "${OPERATIONAL_DOCUMENT}",
        "storage_location": storage_loc_val,
        "picking_quantity": picking_qty_val,
    }


def extract_billing_document_parameters(ac_text: str) -> Dict[str, str]:
    """Dynamically extracts Billing Document parameters (Processing Status, Document reference) from AC text."""
    proc_status = "Fully Invoiced"
    if ac_text:
        m_status = re.search(r"(fully\s+invoiced|to\s+be\s+processed|partially\s+invoiced)", ac_text, re.IGNORECASE)
        if m_status:
            proc_status = m_status.group(1).strip().title()
    return {
        "document_number": "${MATERIAL_DOCUMENT}",
        "processing_status": proc_status,
    }


def build_outbound_delivery_steps(
    target_url: str,
    order_number: str = "${OPERATIONAL_DOCUMENT}",
    plant: str = "${plant}",
    storage_location: str = "${storage_location}",
    picking_quantity: str = "${picking_quantity}",
    outbound_delivery_url: Optional[str] = None,
    username: Optional[str] = None,
    password: Optional[str] = None,
    include_logoff: bool = True,
) -> List[TestStep]:
    """
    Builds dedicated Create Outbound Delivery with Reference (AC-03) steps.
    Uses dynamic ${key} placeholders bound to test_data and runtime context (${OPERATIONAL_DOCUMENT}).
    """
    login_steps = build_sap_login_steps(target_url, username=username, password=password)
    target_od_url = outbound_delivery_url or DEFAULT_OUTBOUND_DELIVERY_URL

    flow_steps = [
        TestStep(
            step_number=6,
            action=ActionType.NAVIGATE,
            input_value=target_od_url,
            description="Navigate to Create Outbound Delivery with reference",
        ),
        TestStep(
            step_number=7,
            action=ActionType.FILL,
            locator_strategy=LocatorStrategy.ROLE,
            role_name="textbox",
            selector_value="Shipping Point Required",
            input_value=plant,
            description=f"Select Plant / Shipping Point as '{plant}'",
        ),
        TestStep(
            step_number=8,
            action=ActionType.FILL,
            locator_strategy=LocatorStrategy.ROLE,
            role_name="textbox",
            selector_value="Order Required",
            input_value=order_number,
            description=f"Enter Order Number '{order_number}' copied from AC-01",
        ),
        TestStep(
            step_number=9,
            action=ActionType.FILL,
            locator_strategy=LocatorStrategy.ROLE,
            role_name="textbox",
            selector_value="Order Required",
            input_value="Enter",
            description="Press 'Enter' into Order Required to open delivery items",
        ),
        TestStep(
            step_number=10,
            action=ActionType.CLICK,
            locator_strategy=LocatorStrategy.ROLE,
            role_name="tab",
            selector_value="Picking",
            description="Click on 'Picking' Tab",
        ),
        TestStep(
            step_number=11,
            action=ActionType.CLICK,
            locator_strategy=LocatorStrategy.CSS,
            selector_value='[id="M0\\:46\\:2\\:3B257\\:2\\[1\\,4\\]_c"]',
            description="Select Storage Location cell (Row 1) in Picking tab",
        ),
        TestStep(
            step_number=12,
            action=ActionType.FILL,
            locator_strategy=LocatorStrategy.ROLE,
            role_name="grid",
            selector_value="All Items",
            input_value=storage_location,
            description=f"Enter Storage Location as '{storage_location}' (Row 1)",
        ),
        TestStep(
            step_number=13,
            action=ActionType.CLICK,
            locator_strategy=LocatorStrategy.CSS,
            selector_value='[id="M0\\:46\\:2\\:3B257\\:2\\[1\\,8\\]_c"]',
            description="Select Picking Quantity cell (Row 1) in Picking tab",
        ),
        TestStep(
            step_number=14,
            action=ActionType.FILL,
            locator_strategy=LocatorStrategy.ROLE,
            role_name="grid",
            selector_value="All Items",
            input_value=picking_quantity,
            description=f"Enter picking quantity as '{picking_quantity}' (Row 1)",
        ),
        TestStep(
            step_number=15,
            action=ActionType.FILL,
            locator_strategy=LocatorStrategy.ROLE,
            role_name="grid",
            selector_value="All Items",
            input_value="Enter",
            description="Press 'Enter' into All Items (Row 1)",
        ),
        TestStep(
            step_number=16,
            action=ActionType.CLICK,
            locator_strategy=LocatorStrategy.CSS,
            selector_value='[id="M0\\:46\\:2\\:3B257\\:2\\[2\\,4\\]_c"]',
            description="Select Storage Location cell (Row 2) in Picking tab",
        ),
        TestStep(
            step_number=17,
            action=ActionType.FILL,
            locator_strategy=LocatorStrategy.ROLE,
            role_name="grid",
            selector_value="All Items",
            input_value=storage_location,
            description=f"Enter Storage Location as '{storage_location}' (Row 2)",
        ),
        TestStep(
            step_number=18,
            action=ActionType.CLICK,
            locator_strategy=LocatorStrategy.CSS,
            selector_value='[id="M0\\:46\\:2\\:3B257\\:2\\[2\\,8\\]_c"]',
            description="Select Picking Quantity cell (Row 2) in Picking tab",
        ),
        TestStep(
            step_number=19,
            action=ActionType.FILL,
            locator_strategy=LocatorStrategy.ROLE,
            role_name="grid",
            selector_value="All Items",
            input_value=picking_quantity,
            description=f"Enter picking quantity as '{picking_quantity}' (Row 2)",
        ),
        TestStep(
            step_number=20,
            action=ActionType.FILL,
            locator_strategy=LocatorStrategy.ROLE,
            role_name="grid",
            selector_value="All Items",
            input_value="Enter",
            description="Press 'Enter' into All Items (Row 2)",
        ),
        TestStep(
            step_number=21,
            action=ActionType.CLICK,
            locator_strategy=LocatorStrategy.CSS,
            selector_value='[id="M0\\:46\\:2\\:3B257\\:2\\[3\\,4\\]_c"]',
            description="Select Storage Location cell (Row 3) in Picking tab",
        ),
        TestStep(
            step_number=22,
            action=ActionType.FILL,
            locator_strategy=LocatorStrategy.ROLE,
            role_name="grid",
            selector_value="All Items",
            input_value=storage_location,
            description=f"Enter Storage Location as '{storage_location}' (Row 3)",
        ),
        TestStep(
            step_number=23,
            action=ActionType.CLICK,
            locator_strategy=LocatorStrategy.CSS,
            selector_value='[id="M0\\:46\\:2\\:3B257\\:2\\[3\\,8\\]_c"]',
            description="Select Picking Quantity cell (Row 3) in Picking tab",
        ),
        TestStep(
            step_number=24,
            action=ActionType.FILL,
            locator_strategy=LocatorStrategy.ROLE,
            role_name="grid",
            selector_value="All Items",
            input_value=picking_quantity,
            description=f"Enter picking quantity as '{picking_quantity}' (Row 3)",
        ),
        TestStep(
            step_number=25,
            action=ActionType.FILL,
            locator_strategy=LocatorStrategy.ROLE,
            role_name="grid",
            selector_value="All Items",
            input_value="Enter",
            description="Press 'Enter' into All Items (Row 3)",
        ),
        TestStep(
            step_number=26,
            action=ActionType.CLICK,
            locator_strategy=LocatorStrategy.ROLE,
            role_name="button",
            selector_value="Post Goods Issue",
            description="Click on 'Post Goods Issue'",
        ),
        TestStep(
            step_number=27,
            action=ActionType.ASSERT_TEXT,
            locator_strategy=LocatorStrategy.CSS,
            selector_value="body",
            expected_value="Outbound Delivery",
            description="Verify Outbound Delivery and Material document is created and capture Material number",
        ),
    ]

    all_steps = login_steps + flow_steps
    if include_logoff:
        logoff_steps = build_sap_logoff_steps(start_step_number=len(all_steps) + 1)
        all_steps.extend(logoff_steps)

    for idx, s in enumerate(all_steps, 1):
        s.step_number = idx
    return all_steps


def build_billing_document_steps(
    target_url: str,
    document_number: str = "${MATERIAL_DOCUMENT}",
    processing_status: str = "${processing_status}",
    billing_doc_url: Optional[str] = None,
    username: Optional[str] = None,
    password: Optional[str] = None,
    include_logoff: bool = True,
) -> List[TestStep]:
    """
    Builds dedicated Create Billing Document (AC-04) steps.
    Uses dynamic ${key} placeholders bound to test_data and runtime context (${MATERIAL_DOCUMENT}).
    """
    login_steps = build_sap_login_steps(target_url, username=username, password=password)
    target_bd_url = billing_doc_url or DEFAULT_BILLING_DOC_URL

    flow_steps = [
        TestStep(
            step_number=6,
            action=ActionType.NAVIGATE,
            input_value=target_bd_url,
            description="Navigate to Create Billing Document",
        ),
        TestStep(
            step_number=7,
            action=ActionType.FILL,
            locator_strategy=LocatorStrategy.ROLE,
            role_name="grid",
            selector_value="Documents to Be Processed",
            input_value=document_number,
            description=f"Enter the Document number '{document_number}' copied in the previous test case into Documents to Be Processed",
        ),
        TestStep(
            step_number=8,
            action=ActionType.FILL,
            locator_strategy=LocatorStrategy.ROLE,
            role_name="grid",
            selector_value="Documents to Be Processed",
            input_value="Enter",
            description="Press 'Enter' into Documents to Be Processed",
        ),
        TestStep(
            step_number=9,
            action=ActionType.CLICK,
            locator_strategy=LocatorStrategy.ROLE,
            role_name="button",
            selector_value="Back",
            description="Click Back",
        ),
        TestStep(
            step_number=10,
            action=ActionType.CLICK,
            locator_strategy=LocatorStrategy.ROLE,
            role_name="button",
            selector_value="Save \u00a0Emphasized",
            description="Click Save to create Billing Document",
        ),
        TestStep(
            step_number=11,
            action=ActionType.ASSERT_TEXT,
            locator_strategy=LocatorStrategy.CSS,
            selector_value="body",
            expected_value=processing_status,
            description=f"Select the Document and check if it is '{processing_status}' in the Processing Status and verify Billing Number is created",
        ),
    ]

    all_steps = login_steps + flow_steps
    if include_logoff:
        logoff_steps = build_sap_logoff_steps(start_step_number=len(all_steps) + 1)
        all_steps.extend(logoff_steps)

    for idx, s in enumerate(all_steps, 1):
        s.step_number = idx
    return all_steps


def build_monolithic_rar_steps(
    params: Dict[str, Any],
    target_url: str,
    operational_doc: str = "${OPERATIONAL_DOCUMENT}",
    mrc_url: Optional[str] = None,
    username: Optional[str] = None,
    password: Optional[str] = None,
    include_logoff: bool = True,
) -> List[TestStep]:
    """Builds a complete monolithic SAP Service Quotation + Downstream RAR Contract verification."""
    # Service quotation up through Transaction History (without logoff)
    quotation_steps = build_service_quotation_steps(
        params=params,
        target_url=target_url,
        capture_transaction_history=True,
        include_logoff=False,
        username=username,
        password=password,
    )

    target_mrc = mrc_url or DEFAULT_MRC_URL
    val_help_sel = (
        "[id*='RevenueAccountingContract-vhi'], "
        "[id*='RevenueContract-vhi'], "
        "div:has(> label:has-text('Revenue Contract')) .sapMInputValHelpInner, "
        "label:has-text('Revenue Contract') ~ div .sapMInputValHelpInner, "
        "[id='fin.rar.manage.contract::sap.suite.ui.generic.template.ListReport.view.ListReport::C_RAContrWithPostedBalanceTP--listReportFilter-filterItemControl_BASIC-RevenueAccountingContract-vhi']"
    )

    cur = len(quotation_steps) + 1
    downstream_steps = [
        TestStep(
            step_number=cur,
            action=ActionType.NAVIGATE,
            input_value=target_mrc,
            description="Navigate directly to Manage Revenue Contracts application",
        ),
        TestStep(
            step_number=cur + 1,
            action=ActionType.CLICK,
            locator_strategy=LocatorStrategy.CSS,
            selector_value=val_help_sel,
            description="Click Revenue Accounting Contract Value Help",
        ),
        TestStep(
            step_number=cur + 2,
            action=ActionType.FILL,
            locator_strategy=LocatorStrategy.ROLE,
            role_name="textbox",
            selector_value="Operational Document:",
            input_value=operational_doc,
            description="Enter captured Operational Document into Operational Document:",
        ),
        TestStep(
            step_number=cur + 3,
            action=ActionType.FILL,
            locator_strategy=LocatorStrategy.ROLE,
            role_name="textbox",
            selector_value="Operational Document:",
            input_value="Enter",
            description="Press 'Enter' into Operational Document:",
        ),
        TestStep(
            step_number=cur + 4,
            action=ActionType.CLICK,
            locator_strategy=LocatorStrategy.TEXT,
            selector_value="Selection column",
            description="Click Selection column",
        ),
        TestStep(
            step_number=cur + 5,
            action=ActionType.CLICK,
            locator_strategy=LocatorStrategy.ROLE,
            role_name="dialog",
            selector_value="Revenue Contract",
            description="Click Revenue Contract dialog",
        ),
        TestStep(
            step_number=cur + 6,
            action=ActionType.CLICK,
            locator_strategy=LocatorStrategy.ROLE,
            role_name="button",
            selector_value="OK",
            description="Click OK",
        ),
        TestStep(
            step_number=cur + 7,
            action=ActionType.CLICK,
            locator_strategy=LocatorStrategy.ROLE,
            role_name="button",
            selector_value="Go",
            description="Click Go",
        ),
        TestStep(
            step_number=cur + 8,
            action=ActionType.ASSERT_TEXT,
            locator_strategy=LocatorStrategy.CSS,
            selector_value="body",
            expected_value="Revenue Contract",
            description="Verify Revenue Contract loaded",
        ),
    ]

    all_steps = quotation_steps + downstream_steps
    if include_logoff:
        logoff_steps = build_sap_logoff_steps(start_step_number=len(all_steps) + 1)
        all_steps.extend(logoff_steps)

    for idx, s in enumerate(all_steps, 1):
        s.step_number = idx
    return all_steps


def build_evidence_capture_steps(
    params: Dict[str, Any],
    target_url: str,
    username: Optional[str] = None,
    password: Optional[str] = None,
) -> List[TestStep]:
    """Generates steps for evidence capture (saved quotation number and status)."""
    login_steps = build_sap_login_steps(target_url, username=username, password=password)
    flow_steps = [
        TestStep(
            step_number=6,
            action=ActionType.CLICK,
            locator_strategy=LocatorStrategy.TEXT,
            selector_value="Manage Service Quotations",
            description="Click Manage Service Quotations tile",
        ),
        TestStep(
            step_number=7,
            action=ActionType.CLICK,
            locator_strategy=LocatorStrategy.ROLE,
            role_name="button",
            selector_value="Save (Ctrl+S)",
            description="Click Save button to persist quotation",
        ),
        TestStep(
            step_number=8,
            action=ActionType.ASSERT_TEXT,
            locator_strategy=LocatorStrategy.CSS,
            selector_value="body",
            expected_value="saved",
            description="Verify quotation saved confirmation in status bar",
        ),
        TestStep(
            step_number=9,
            action=ActionType.ASSERT_TEXT,
            locator_strategy=LocatorStrategy.CSS,
            selector_value="body",
            expected_value="Quotation",
            description="Capture saved quotation number and status as test evidence",
        ),
    ]
    logoff_steps = build_sap_logoff_steps(start_step_number=len(login_steps) + len(flow_steps) + 1)
    all_steps = login_steps + flow_steps + logoff_steps
    for idx, s in enumerate(all_steps, 1):
        s.step_number = idx
    return all_steps


def build_bundle_validation_steps(
    params: Dict[str, Any],
    target_url: str,
    username: Optional[str] = None,
    password: Optional[str] = None,
) -> List[TestStep]:
    """Generates steps for bundle item explosion and validation."""
    login_steps = build_sap_login_steps(target_url, username=username, password=password)
    prod_val = params.get("prod_val", "45157510101")
    flow_steps = [
        TestStep(
            step_number=6,
            action=ActionType.CLICK,
            locator_strategy=LocatorStrategy.ROLE,
            role_name="option",
            selector_value="Items",
            description="Open Items tab",
        ),
        TestStep(
            step_number=7,
            action=ActionType.FILL,
            locator_strategy=LocatorStrategy.CSS,
            selector_value="[id*='ordered_prod'], input[id*='ordered_prod']",
            input_value=prod_val,
            description=f"Enter Product ID {prod_val}",
        ),
        TestStep(
            step_number=8,
            action=ActionType.FILL,
            locator_strategy=LocatorStrategy.CSS,
            selector_value="[id*='ordered_prod'], input[id*='ordered_prod']",
            input_value="Enter",
            description="Press Enter to trigger bundle explosion and partner derivations",
        ),
        TestStep(
            step_number=9,
            action=ActionType.ASSERT_TEXT,
            locator_strategy=LocatorStrategy.CSS,
            selector_value="body",
            expected_value=prod_val,
            description="Verify main product row visible in Items table",
        ),
        TestStep(
            step_number=10,
            action=ActionType.ASSERT_TEXT,
            locator_strategy=LocatorStrategy.CSS,
            selector_value="body",
            expected_value="Service",
            description="Verify configured service, installation, and warranty bundle items present",
        ),
    ]
    logoff_steps = build_sap_logoff_steps(start_step_number=len(login_steps) + len(flow_steps) + 1)
    all_steps = login_steps + flow_steps + logoff_steps
    for idx, s in enumerate(all_steps, 1):
        s.step_number = idx
    return all_steps


def build_mandatory_validation_steps(
    params: Dict[str, Any],
    target_url: str,
    username: Optional[str] = None,
    password: Optional[str] = None,
) -> List[TestStep]:
    """Generates negative test steps verifying mandatory Sold-to Party validation error."""
    login_steps = build_sap_login_steps(target_url, username=username, password=password)
    ttype_val = params.get("ttype_val", "ZQDS")
    flow_steps = [
        TestStep(
            step_number=6,
            action=ActionType.CLICK,
            locator_strategy=LocatorStrategy.TEXT,
            selector_value="Manage Service Quotations",
            description="Click Manage Service Quotations tile",
        ),
        TestStep(
            step_number=7,
            action=ActionType.CLICK,
            locator_strategy=LocatorStrategy.CSS,
            selector_value="button:has-text('New Create'), button:has-text('Create'), [title*='Create'], #btnCreate",
            description="Click Create button on Service Quotations worklist",
        ),
        TestStep(
            step_number=8,
            action=ActionType.CLICK,
            locator_strategy=LocatorStrategy.TEXT,
            selector_value=ttype_val,
            description=f"Select Transaction Type {ttype_val} from popup",
        ),
        TestStep(
            step_number=9,
            action=ActionType.FILL,
            locator_strategy=LocatorStrategy.ROLE,
            role_name="textbox",
            selector_value="Sold-To Party:",
            input_value="",
            description="Leave mandatory Sold-to Party field empty",
        ),
        TestStep(
            step_number=10,
            action=ActionType.FILL,
            locator_strategy=LocatorStrategy.ROLE,
            role_name="textbox",
            selector_value="Sold-To Party:",
            input_value="Enter",
            description="Press Enter to trigger backend validation",
        ),
        TestStep(
            step_number=11,
            action=ActionType.CLICK,
            locator_strategy=LocatorStrategy.ROLE,
            role_name="button",
            selector_value="Save (Ctrl+S)",
            description="Attempt Save with missing mandatory field",
        ),
        TestStep(
            step_number=12,
            action=ActionType.ASSERT_TEXT,
            locator_strategy=LocatorStrategy.CSS,
            selector_value="[data-testid='error-banner'], .sap-error-banner, body",
            expected_value="Validation Error",
            description="Verify mandatory Sold-to Party validation error-banner or status message displayed",
        ),
    ]
    logoff_steps = build_sap_logoff_steps(start_step_number=len(login_steps) + len(flow_steps) + 1)
    all_steps = login_steps + flow_steps + logoff_steps
    for idx, s in enumerate(all_steps, 1):
        s.step_number = idx
    return all_steps


def build_item_entry_steps(
    params: Dict[str, Any],
    target_url: str,
    username: Optional[str] = None,
    password: Optional[str] = None,
) -> List[TestStep]:
    """Generates steps for isolated line item entry and persistence."""
    login_steps = build_sap_login_steps(target_url, username=username, password=password)
    items_tab_step = [
        TestStep(
            step_number=6,
            action=ActionType.CLICK,
            locator_strategy=LocatorStrategy.ROLE,
            role_name="option",
            selector_value="Items",
            description="Open Items tab",
        )
    ]
    items = params.get("extracted_items") or [(params.get("prod_val", "45157510101"), params.get("qty_val", "1"))]
    loop_steps = build_service_quotation_item_steps(items, start_step_number=7)
    s_idx = len(login_steps) + len(items_tab_step) + len(loop_steps) + 1
    prod_val = params.get("prod_val", "45157510101")
    qty_val = params.get("qty_val", "1")

    trail_steps = [
        TestStep(
            step_number=s_idx,
            action=ActionType.CLICK,
            locator_strategy=LocatorStrategy.ROLE,
            role_name="button",
            selector_value="Save (Ctrl+S)",
            description="Click Save button to persist quotation line items",
        ),
        TestStep(
            step_number=s_idx + 1,
            action=ActionType.ASSERT_TEXT,
            locator_strategy=LocatorStrategy.CSS,
            selector_value="body",
            expected_value=prod_val,
            description=f"Assert main product {prod_val} and quantity {qty_val} saved correctly",
        ),
    ]
    all_steps = login_steps + items_tab_step + loop_steps + trail_steps
    logoff_steps = build_sap_logoff_steps(start_step_number=len(all_steps) + 1)
    all_steps.extend(logoff_steps)
    for idx, s in enumerate(all_steps, 1):
        s.step_number = idx
    return all_steps


def build_header_creation_steps(
    params: Dict[str, Any],
    target_url: str,
    username: Optional[str] = None,
    password: Optional[str] = None,
) -> List[TestStep]:
    """Generates steps for creating quotation header with sold-to party."""
    login_steps = build_sap_login_steps(target_url, username=username, password=password)
    ttype_val = params.get("ttype_val", "ZQDS")
    desc_val = params.get("desc_val", "RAR Test")
    soldto_val = params.get("soldto_val", "Brugmann Hospital")

    flow_steps = [
        TestStep(
            step_number=6,
            action=ActionType.CLICK,
            locator_strategy=LocatorStrategy.TEXT,
            selector_value="Manage Service Quotations",
            description="Click Manage Service Quotations tile",
        ),
        TestStep(
            step_number=7,
            action=ActionType.CLICK,
            locator_strategy=LocatorStrategy.CSS,
            selector_value="button:has-text('New Create'), button:has-text('Create'), [title*='Create'], #btnCreate",
            description="Click Create button on Service Quotations worklist",
        ),
        TestStep(
            step_number=8,
            action=ActionType.CLICK,
            locator_strategy=LocatorStrategy.TEXT,
            selector_value=ttype_val,
            description=f"Select Transaction Type {ttype_val} (CE-Direct Sales) from popup",
        ),
        TestStep(
            step_number=9,
            action=ActionType.FILL,
            locator_strategy=LocatorStrategy.ROLE,
            role_name="textbox",
            selector_value="Description:",
            input_value=desc_val,
            description=f"Enter Quotation Description '{desc_val}'",
        ),
        TestStep(
            step_number=10,
            action=ActionType.FILL,
            locator_strategy=LocatorStrategy.ROLE,
            role_name="textbox",
            selector_value="Sold-To Party:",
            input_value=soldto_val,
            description=f"Enter Sold-to Party customer '{soldto_val}'",
        ),
        TestStep(
            step_number=11,
            action=ActionType.FILL,
            locator_strategy=LocatorStrategy.ROLE,
            role_name="textbox",
            selector_value="Sold-To Party:",
            input_value="Enter",
            description="Press Enter to commit Sold-to Party and trigger partner determination",
        ),
        TestStep(
            step_number=12,
            action=ActionType.ASSERT_TEXT,
            locator_strategy=LocatorStrategy.CSS,
            selector_value="body",
            expected_value=soldto_val,
            description="Assert quotation created with required transaction type and sold-to party",
        ),
    ]
    all_steps = login_steps + flow_steps
    logoff_steps = build_sap_logoff_steps(start_step_number=len(all_steps) + 1)
    all_steps.extend(logoff_steps)
    for idx, s in enumerate(all_steps, 1):
        s.step_number = idx
    return all_steps


def build_release_accept_steps() -> List[TestStep]:
    """Generates standalone release and accept action steps."""
    return [
        TestStep(
            step_number=1,
            action=ActionType.CLICK,
            locator_strategy=LocatorStrategy.CSS,
            selector_value="button:has-text('Edit'), a:has-text('Edit'), [title*='Edit'], [aria-label*='Edit']",
            description="Click Edit button",
        ),
        TestStep(
            step_number=2,
            action=ActionType.CLICK,
            locator_strategy=LocatorStrategy.CSS,
            selector_value="#C9_W36_V39_V40_btadminh_lcstatus-btn, [id*='btadminh_lcstatus-btn']",
            description="Open Lifecycle Status dropdown",
        ),
        TestStep(
            step_number=3,
            action=ActionType.CLICK,
            locator_strategy=LocatorStrategy.ROLE,
            role_name="link",
            selector_value="Released",
            description="Change status to Released",
        ),
        TestStep(
            step_number=4,
            action=ActionType.CLICK,
            locator_strategy=LocatorStrategy.ROLE,
            role_name="button",
            selector_value="Save (Ctrl+S)",
            description="Click Save button",
        ),
        TestStep(
            step_number=5,
            action=ActionType.CLICK,
            locator_strategy=LocatorStrategy.CSS,
            selector_value="button:has-text('Accept'), [title*='Accept'], a:has-text('Accept'), [role='menuitem']:has-text('Accept')",
            description="Click Accept button on header toolbar",
        ),
        TestStep(
            step_number=6,
            action=ActionType.ASSERT_TEXT,
            locator_strategy=LocatorStrategy.CSS,
            selector_value="body",
            expected_value="Accepted",
            description="Verify quotation status updated to Accepted",
        ),
    ]


def build_pricing_condition_steps(pricing_val: str = "ZTAF") -> List[TestStep]:
    """Generates standalone pricing condition addition steps."""
    return [
        TestStep(
            step_number=1,
            action=ActionType.CLICK,
            locator_strategy=LocatorStrategy.ROLE,
            role_name="option",
            selector_value="Price Details",
            description="Click Price Details tab",
        ),
        TestStep(
            step_number=2,
            action=ActionType.CLICK,
            locator_strategy=LocatorStrategy.ROLE,
            role_name="button",
            selector_value="Add",
            description="Click Add Pricing Element button",
        ),
        TestStep(
            step_number=3,
            action=ActionType.CLICK,
            locator_strategy=LocatorStrategy.TEXT,
            selector_value=pricing_val,
            description=f"Select condition type {pricing_val} from popup",
        ),
        TestStep(
            step_number=4,
            action=ActionType.CLICK,
            locator_strategy=LocatorStrategy.ROLE,
            role_name="button",
            selector_value="Back",
            description="Click Back to return to quotation",
        ),
        TestStep(
            step_number=5,
            action=ActionType.ASSERT_TEXT,
            locator_strategy=LocatorStrategy.CSS,
            selector_value="body",
            expected_value=pricing_val,
            description=f"Verify condition type {pricing_val} present in pricing elements",
        ),
    ]


def build_duration_dates_steps(
    duration_val: str = "24",
    time_unit_val: str = "Month",
) -> List[TestStep]:
    """Generates standalone duration and dates configuration steps."""
    return [
        TestStep(
            step_number=1,
            action=ActionType.CLICK,
            locator_strategy=LocatorStrategy.ROLE,
            role_name="option",
            selector_value="Dates",
            description="Open Dates tab",
        ),
        TestStep(
            step_number=2,
            action=ActionType.FILL,
            locator_strategy=LocatorStrategy.CSS,
            selector_value="#C16_W64_V65_DatesTable_bottom_div tr:has-text('Term of Quotation') input, #C16_W64_V65_DatesTable_bottom_div tr:has-text('Term of Quotation') [role='textbox']",
            input_value=duration_val,
            description=f"Go to Term of Quotation and enter Duration as {duration_val}",
        ),
        TestStep(
            step_number=3,
            action=ActionType.CLICK,
            locator_strategy=LocatorStrategy.CSS,
            selector_value="[id='C16_W64_V65_btdate_table[4].time_unit-btn']",
            description="Open Time Unit dropdown",
        ),
        TestStep(
            step_number=4,
            action=ActionType.CLICK,
            locator_strategy=LocatorStrategy.ROLE,
            role_name="link",
            selector_value=time_unit_val,
            description=f"Select time unit {time_unit_val}",
        ),
        TestStep(
            step_number=5,
            action=ActionType.ASSERT_TEXT,
            locator_strategy=LocatorStrategy.CSS,
            selector_value="body",
            expected_value=time_unit_val,
            description="Verify duration and validity dates section displayed",
        ),
    ]


def steps_to_few_shot_json(steps: List[TestStep], redact_credentials: bool = True) -> str:
    """
    Serializes a list of TestStep objects to a pretty-printed JSON string suitable
    for inclusion in LLM prompt few-shot examples, with optional credential masking.
    """
    data = []
    for s in steps:
        s_dict: Dict[str, Any] = {
            "step_number": s.step_number,
            "action": s.action.value,
        }
        if s.locator_strategy:
            s_dict["locator_strategy"] = s.locator_strategy.value
        if s.role_name:
            s_dict["role_name"] = s.role_name
        if s.selector_value:
            s_dict["selector_value"] = s.selector_value
        if s.input_value is not None:
            val = s.input_value
            if redact_credentials and s.action == ActionType.FILL:
                if "#USERNAME_FIELD" in (s.selector_value or ""):
                    val = "<CONFIGURED_USERNAME>"
                elif "#PASSWORD_FIELD" in (s.selector_value or ""):
                    val = "<CONFIGURED_PASSWORD>"
            s_dict["input_value"] = val
        if s.expected_value is not None:
            s_dict["expected_value"] = s.expected_value
        if s.description:
            s_dict["description"] = s.description
        data.append(s_dict)

    return json.dumps(data, indent=2)
