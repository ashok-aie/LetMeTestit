# Enterprise Test Automation & Quality Engineering Standards

## 1. Core Testing Methodology
- **Arrange-Act-Assert (AAA)**:
  - **Arrange**: Ensure pre-conditions, target navigation, and session state are established.
  - **Act**: Perform the user action (click, fill, select).
  - **Assert**: Validate visible outcome, message banner, or UI state transition.
- **Equivalence Partitioning & Boundary Value Analysis**:
  - Test suites must include positive flows (happy path) and negative validation (boundary / error conditions).
  - Negative tests must assert that the application displays appropriate validation feedback without uncaught 500 errors or unhandled exceptions.

## 2. SAP S/4HANA & Enterprise UI5 Best Practices
- **Resilient Locators**:
  - Never rely on volatile, auto-generated UI5 IDs (e.g. `__xmlview0--btn123`).
  - Prioritize stable semantic selectors:
    - HTML ID attributes (e.g. `#USERNAME_FIELD-inner`, `#PASSWORD_FIELD-inner`, `#LOGIN_LINK`, `#meAreaHeaderButton`).
    - Visible Text with UI5 soft-hyphen fallback (`text="Manage Service Quotations"` or `[aria-label*='...']` / `[title*='...']`).
    - Accessible ARIA roles (`role="button", name="..."`).
- **Deterministic Wait States**:
  - Do not use arbitrary hardcoded delays unless explicitly requested by business criteria (e.g. "wait 20 seconds").
  - Wait for `networkidle` state or element attachment (`visible`, `attached`).
- **Clean Authentication Lifecycle**:
  - Always verify landing state after logon (e.g. presence of `Home` or dashboard header).
  - Always terminate sessions gracefully (click `#meAreaHeaderButton` -> `Sign Out` -> confirm modal -> assert `signed out`).

## 3. Cross-Test Context Chaining (`${OPERATIONAL_DOCUMENT}`)
- **Modular Test Case Decomposition**:
  - Long end-to-end business flows must be decomposed into granular, single-responsibility test cases aligned with individual Acceptance Criteria:
    - **TC-01 (Quotation Creation & Acceptance)**: Creates quotation with line items, adds pricing condition, transitions status to Released, clicks Accept, and opens `Transaction History`.
    - **TC-02 (Downstream RAR Contract Verification)**: Uses captured transaction reference to query `Manage Revenue Contracts` value help, selects the contract, and validates contract details.
- **Dynamic Context Hand-Off**:
  - **Zero Hardcoding**: Never write static document numbers (e.g. `962`) in test steps.
  - In `TC-01`, capture evidence by asserting `Transaction` on the `Transaction History` facet; `TestExecutor` dynamically captures the document ID into `self.runtime_context["operational_document"]` and class-level `_LATEST_OPERATIONAL_DOC`.
  - In `TC-02`, set `input_value="${OPERATIONAL_DOCUMENT}"` in the `Operational Document:` value help step; `TestExecutor` dynamically substitutes the runtime document number.

## 4. CRM WebClient Multi-Item Dynamic Table Entry
- **Strict Row Isolation**:
  - In CRM WebClient tables (e.g. `btadmini_table`), each row has a 1-based index: `table[1]`, `table[2]`, `table[3]`, etc.
  - Never allow quantity or product locators for `row > 1` to fallback to generic selectors matching row 1 (which would overwrite row 1 rather than filling the new line).
  - For `row 1`: use row 1 locators (`btadmini_table[1].ordered_prod`, `btadmini_table[1].quantity`).
  - For `row N (N > 1)`: strictly use row `N` locators (`btadmini_table[N].ordered_prod`, `btadmini_table[N].quantity`).
- **Sequential Commit Protocol**:
  - For each line item, enter `Product ID`, enter `Quantity`, and then immediately press `Enter` to commit the line item and trigger CRM partner/pricing explosion before proceeding to the next row.

## 5. Dynamic Transaction Type Parameterization
- Never hardcode quotation transaction types (`ZQDS`).
- Extract transaction type dynamically from the Acceptance Criteria or User Story preconditions (e.g. `ZQDS`, `ZQDV`, `ZSVO`).
- If unspecified in the story, default to standard `ZQDS`.
- Transaction type selection step: `action=CLICK`, `locator_strategy=TEXT`, `selector_value=ttype_val`, `description="Select Transaction Type {ttype_val} from popup"`.



## 6. Verified Service Quotation Line Item Flow (live-verified 2026-10-22, KAN-32)
- **Per line item (row N)**, in this exact order:
  1. Fill Product ID `btadmini_table[N].ordered_prod` and press `Enter`.
  2. Product Name (`btadmini_table[N].node_description`) is plain text – no navigation.
  3. Fill Quantity `btadmini_table[N].quantity` in the Items table.
  4. Fill Plant `btadmini_table[N].plant` in the Items table Plant column (+ `Enter`).
  5. Click the pencil icon next to the product name: `btadmini_table[N].thtmlb_oca.EDIT_link` -> opens Sales Item Details
     (service/subscription items open "Service Contract Item Details").
  6. Open the item `Price Details` tab; expand the Price Details block if collapsed.
  7. For each price condition: click `Add` (Price Details toolbar) -> Price Element popup (`tableData` rows: name + Price Element ID)
     -> click the condition (by ID e.g. `Z100`, `ZSSP`, or by name e.g. `CE-Bndl Cont Price`) -> enter the value in the row's
     `condline_table[k].kbetr_prt` Price input + `Enter`. If the element already exists (e.g. CE-Bndl Cont Price), close the popup
     and fill the existing row instead of adding a duplicate.
  8. Click `Back` (or `Apply` on service contract items), then re-open `Items`.
- **Amounts**: AC values like `100,000` / `450,000` are thousand-separated -> enter `100000` / `450000`; `100%` -> `100`.
- **Lifecycle verification**: Save -> verify Status (e.g. `Quotation Created`); Edit -> Released -> Save -> verify `Released`;
  Accept -> verify `Completed`. A Save that leaves the document in `: New` state fails the test with the SAP error text.
- **Zero hardcoding**: steps use `${key}` placeholders (`item{N}_product_id`, `item{N}_quantity`, `item{N}_plant`,
  `item{N}_cond{K}_type`, `item{N}_cond{K}_value`, `status_after_save`, ...) bound to the test case `test_data`,
  extracted from the AC text by `extract_sap_line_items` / `extract_sap_status_checks`.

## 7. SAP Direct Application Links & WebGUI Flows (KAN-32 AC-03 & AC-04)
- **Direct Application URLs**:
  - **Manage Service Quotations**: `https://s4srv25.nodomain.com:44325/sap/bc/ui2/flp?sap-client=100&sap-language=EN#BusinessSolutionQuotation-manageV2`
  - **Manage Revenue Contracts**: `https://s4srv25.nodomain.com:44325/sap/bc/ui2/flp?sap-client=100&sap-language=EN#RevenueAccountingContract-manageContract&/?sap-iapp-state--history=TAS60ZN0APGEXK9SB8U7CWP0998E9ZTQEZ7DBW9FR`
  - **Create Outbound Delivery**: `https://s4srv25.nodomain.com:44325/sap/bc/ui2/flp?sap-client=100&sap-language=EN#OutboundDelivery-createInWebGUI?sap-ui-tech-hint=GUI`
  - **Create Billing Document**: `https://s4srv25.nodomain.com:44325/sap/bc/ui2/flp?sap-client=100&sap-language=EN#BillingDocument-createBillingDocuments?sap-ui-tech-hint=GUI`
- **AC-03 (Create Outbound Delivery with Reference — Recorded in `[TC-01]` 24 steps & `[TC-02]` 23 steps)**:
  1. Navigate to `https://s4srv25.nodomain.com:44325/sap/bc/ui2/flp?sap-client=100&sap-language=EN#OutboundDelivery-createInWebGUI?sap-ui-tech-hint=GUI`.
  2. Fill `Shipping Point Required` (`role="textbox"`) with `${plant}` (e.g. `BEV8`).
  3. Fill `Order Required` (`role="textbox"`) with `${OPERATIONAL_DOCUMENT}` (the Sales Order / Transaction ID copied in `AC-01`) and press `Enter`.
  4. Click `Picking` (`role="tab"`).
  5. For each line item `r` in `1..3` (as recorded in `[TC-01]` — 24 steps and `[TC-02]` — 23 steps):
     - Click Storage Location cell `[id="M0\:46\:2\:3B257\:2\[{r}\,4\]_c"]` and fill `All Items` (`role="grid"`) with `${storage_location}` (`6020`).
     - Click Picked Quantity cell `[id="M0\:46\:2\:3B257\:2\[{r}\,8\]_c"]`, fill `All Items` (`role="grid"`) with `${picking_quantity}` (`1`), and press `Enter`.
  6. Click `Post Goods Issue` (`role="button"`).
  7. Verify status message `Outbound Delivery <DELIVERY_NO> saved, material document <MAT_DOC_NO> created` (recorded in `[TC-02]` steps 22–23) and capture the created Delivery / Material number (`${MATERIAL_DOCUMENT}`) for `AC-04`.
- **AC-04 (Create Billing Document — Recorded in `[TC-03]` 9 steps)**:
  1. Navigate to `https://s4srv25.nodomain.com:44325/sap/bc/ui2/flp?sap-client=100&sap-language=EN#BillingDocument-createBillingDocuments?sap-ui-tech-hint=GUI`.
  2. Fill `Documents to Be Processed` (`role="grid"`) with `${MATERIAL_DOCUMENT}` (copied from `AC-03`) and press `Enter`.
  3. Click `Back` (`role="button"`).
  4. Click `Save  Emphasized` (`role="button"`, `Save \u00a0Emphasized`).
  5. Verify `${processing_status}` (`Fully Invoiced`) in the Processing Status and verify Billing Number is created.


