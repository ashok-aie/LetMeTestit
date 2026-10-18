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

