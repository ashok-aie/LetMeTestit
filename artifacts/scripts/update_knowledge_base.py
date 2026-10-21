import sys
sys.path.insert(0, ".")
import json
from datetime import datetime, timezone
from app.storage.repository import save_learned_selector, save_reusable_flow, save_golden_example, list_golden_examples, GOLDEN_FILE
from app.models.test_suite import TestStep, TestCase, ActionType, LocatorStrategy, TestCategory

# Load the verified test case from SUITE-KAN-25.json
with open("data/cases/SUITE-KAN-25.json", "r", encoding="utf-8") as f:
    case_data = json.load(f)

first_tc = case_data["suite_data"]["test_cases"][0]
raw_steps = first_tc["steps"]

# Build fully parameterized steps (NO hardcoded credentials, doc numbers, or customer IDs)
parameterized_steps = []
for s in raw_steps:
    s_copy = dict(s)
    snum = s_copy["step_number"]
    
    # Replace any hardcoded execution values with dynamic placeholders
    if snum == 2:
        s_copy["input_value"] = "${SAP_USERNAME}"
    elif snum == 3:
        s_copy["input_value"] = "${SAP_PASSWORD}"
    elif snum == 9:
        s_copy["input_value"] = "${QUOTATION_DESCRIPTION}"
    elif snum == 10:
        s_copy["input_value"] = "${SOLD_TO_PARTY}"
    elif snum == 13:
        s_copy["input_value"] = "${TERM_DURATION}"
    elif snum == 17:
        s_copy["input_value"] = "${PRODUCT_ID}"
    elif snum == 18:
        s_copy["input_value"] = "${QUANTITY}"
    elif snum == 33:
        s_copy["input_value"] = "${MANAGE_REVENUE_CONTRACTS_URL}"
    elif snum == 35:
        s_copy["input_value"] = "${OPERATIONAL_DOCUMENT}"
    
    parameterized_steps.append(TestStep(**s_copy))

print(f"Created {len(parameterized_steps)} parameterized steps without hardcoded values.")

# 1. Update element catalog for all Steps 32-45
catalog_entries = [
    {
        "element_label": "Transaction Evidence Assertion & ID Capture",
        "selector": "body",
        "strategy": "css",
        "action": "assert_text",
        "role_type": None,
        "notes": "Step 32: Captures Sales Order Transaction ID from btdocflow into ${OPERATIONAL_DOCUMENT}"
    },
    {
        "element_label": "Revenue Accounting Contract Value Help Button",
        "selector": "[id*='RevenueAccountingContract-vhi'], [id*='RevenueContract-vhi'], div:has(> label:has-text('Revenue Contract')) .sapMInputValHelpInner, label:has-text('Revenue Contract') ~ div .sapMInputValHelpInner, [id='fin.rar.manage.contract::sap.suite.ui.generic.template.ListReport.view.ListReport::C_RAContrWithPostedBalanceTP--listReportFilter-filterItemControl_BASIC-RevenueAccountingContract-vhi']",
        "strategy": "css",
        "action": "click",
        "role_type": None,
        "notes": "Step 34: Opens Revenue Contract Value Help Dialog"
    },
    {
        "element_label": "RAR Value Help Operational Document Input",
        "selector": "Operational Document:",
        "strategy": "role",
        "action": "fill",
        "role_type": "textbox",
        "notes": "Step 35: Filter input for Operational Document (${OPERATIONAL_DOCUMENT})"
    },
    {
        "element_label": "RAR Value Help Selection Column",
        "selector": "Selection column",
        "strategy": "text",
        "action": "click",
        "role_type": None,
        "notes": "Step 37: Select all items matching operational document"
    },
    {
        "element_label": "RAR Value Help Dialog Container",
        "selector": "Revenue Contract",
        "strategy": "role",
        "action": "click",
        "role_type": "dialog",
        "notes": "Step 38: Focus value help modal dialog"
    },
    {
        "element_label": "RAR Value Help Dialog OK Button",
        "selector": "OK",
        "strategy": "role",
        "action": "click",
        "role_type": "button",
        "notes": "Step 39: Commit contract selection from dialog"
    },
    {
        "element_label": "Manage Revenue Contracts Go Button",
        "selector": "Go",
        "strategy": "role",
        "action": "click",
        "role_type": "button",
        "notes": "Step 40: Execute filter query on Manage Revenue Contracts worklist"
    },
    {
        "element_label": "Revenue Contract Details Loaded Assertion",
        "selector": "body",
        "strategy": "css",
        "action": "assert_text",
        "role_type": None,
        "notes": "Step 41: Asserts contract loaded and navigates to contract details page"
    },
    {
        "element_label": "SAP Fiori Avatar Menu Button",
        "selector": "Avatar",
        "strategy": "role",
        "action": "click",
        "role_type": "button",
        "notes": "Step 42: Opens top-right user profile / Me area menu"
    },
    {
        "element_label": "SAP Fiori Sign Out Button",
        "selector": "Sign Out",
        "strategy": "role",
        "action": "click",
        "role_type": "button",
        "notes": "Step 43: Initiates session logout"
    },
    {
        "element_label": "SAP Fiori Sign Out Dialog Confirm Button",
        "selector": "OK",
        "strategy": "role",
        "action": "click",
        "role_type": "button",
        "notes": "Step 44: Confirms logout in sap.m.Dialog modal"
    },
    {
        "element_label": "SAP Fiori Logoff Completed Assertion",
        "selector": "body",
        "strategy": "css",
        "action": "assert_text",
        "role_type": None,
        "notes": "Step 45: Asserts returned to ICF logout screen"
    }
]

for entry in catalog_entries:
    save_learned_selector(
        element_label=entry["element_label"],
        selector=entry["selector"],
        strategy=entry["strategy"],
        action=entry["action"],
        role_type=entry.get("role_type"),
        app_domain="SAP S/4HANA",
        notes=entry["notes"]
    )

print(f"Catalog updated: {len(catalog_entries)} additional steps cataloged.")

# 2. Add Complete Reusable Flow for Steps 1-45
save_reusable_flow(
    flow_name="SAP RAR - Service Quotation to Revenue Contract Full Lifecycle (Steps 1-45)",
    description="Complete end-to-end parameterized SAP RAR business flow: Launchpad logon, quotation header creation (ZQDS), dates & duration, line item entry, pricing condition (ZTAF), save, edit status to Released, save, Accept quotation, extract Transaction ID from Transaction History as ${OPERATIONAL_DOCUMENT}, navigate to Manage Revenue Contracts, search by ${OPERATIONAL_DOCUMENT}, select contract items, navigate to contract object page, and sign out.",
    category="SAP Revenue Accounting & Reporting (RAR)",
    steps=parameterized_steps
)

print("Saved reusable flow: 'SAP RAR - Service Quotation to Revenue Contract Full Lifecycle (Steps 1-45)'")

# 3. Add Golden Example for Steps 1-45
sample_tc = TestCase(
    id="TC-SAP-RAR-E2E-45",
    requirement_key="KAN-25",
    source_ac_id="AC-01",
    title="SAP RAR End-to-End: Service Quotation Creation to Revenue Accounting Contract (Steps 1-45)",
    objective="Validate complete end-to-end procedural flow from Service Quotation creation, item pricing, lifecycle release, quotation acceptance, transaction ID capture, to Revenue Accounting Contract query, selection, details inspection, and secure logoff.",
    expected_result="Revenue Accounting Contract is located via dynamic ${OPERATIONAL_DOCUMENT}, contract details are loaded, and user session is gracefully terminated.",
    category=TestCategory.POSITIVE,
    preconditions=["SAP Fiori Launchpad available", "Valid SAP credentials configured", "Service product SKU available in plant"],
    test_data={
        "username": "${SAP_USERNAME}",
        "password": "${SAP_PASSWORD}",
        "quotation_description": "RAR flow test",
        "sold_to_party": "Brugmann Hospital",
        "term_duration": "1",
        "product_id": "45157510101",
        "quantity": "1",
        "condition_type": "ZTAF",
        "operational_document": "${OPERATIONAL_DOCUMENT}"
    },
    steps=parameterized_steps
)

save_golden_example(
    pattern="SAP RAR End-to-End Service Quotation to Revenue Contract (45 Steps)",
    description="Verified 45-step exemplar flow with zero hardcoded values. Captures Sales Order Transaction ID dynamically and queries Revenue Accounting Contract.",
    test_case=sample_tc,
    example_id="GOLDEN-SAP-RAR-END-TO-END-45"
)

print("Saved golden example: 'GOLDEN-SAP-RAR-END-TO-END-45'")
