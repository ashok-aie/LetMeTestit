"""
Seeds verified test suites into data/cases/ for Regression testing.
"""
from app.models.test_suite import TestSuite, TestCase, TestStep, ActionType, LocatorStrategy, TestCategory
from app.storage.repository import save_regression_suite

# Suite KAN-11
tc11_1 = TestCase(
    id="TC-01",
    requirement_key="KAN-11",
    source_ac_id="AC-01",
    title="Navigate to Manage Service Quotations Tile and Logout",
    objective="Validate that user can log on to SAP, open the Manage Service Quotations tile, wait 20s, and log out successfully.",
    category=TestCategory.POSITIVE,
    priority="High",
    steps=[
        TestStep(step_number=1, action=ActionType.NAVIGATE, description="Open SAP S/4HANA Fiori URL"),
        TestStep(step_number=2, action=ActionType.FILL, locator_strategy=LocatorStrategy.CSS, selector_value="#USERNAME_FIELD-inner", input_value="MYRAR1", description="Enter username"),
        TestStep(step_number=3, action=ActionType.FILL, locator_strategy=LocatorStrategy.CSS, selector_value="#PASSWORD_FIELD-inner", input_value="Welcome@123", description="Enter password"),
        TestStep(step_number=4, action=ActionType.CLICK, locator_strategy=LocatorStrategy.CSS, selector_value="#LOGIN_LINK", description="Click Log On"),
        TestStep(step_number=5, action=ActionType.ASSERT_TEXT, locator_strategy=LocatorStrategy.CSS, selector_value="body", expected_value="Home", description="Verify Launchpad loaded"),
        TestStep(step_number=6, action=ActionType.CLICK, locator_strategy=LocatorStrategy.TEXT, selector_value="Manage Service Quotations", description="Click Manage Service Quotations tile"),
        TestStep(step_number=7, action=ActionType.WAIT_FOR, locator_strategy=LocatorStrategy.CSS, selector_value="body", input_value="20s", description="Wait for 20 seconds on Service Quotations worklist"),
        TestStep(step_number=8, action=ActionType.ASSERT_TEXT, locator_strategy=LocatorStrategy.CSS, selector_value="body", expected_value="Service Quotation", description="Verify Service Quotations worklist view"),
        TestStep(step_number=9, action=ActionType.CLICK, locator_strategy=LocatorStrategy.CSS, selector_value="#meAreaHeaderButton", description="Open user profile actions menu"),
        TestStep(step_number=10, action=ActionType.CLICK, locator_strategy=LocatorStrategy.CSS, selector_value="button:has-text('Sign Out'), #logoutBtn", description="Click Sign Out"),
        TestStep(step_number=11, action=ActionType.CLICK, locator_strategy=LocatorStrategy.CSS, selector_value="button:has-text('OK'), button:has-text('Sign Out')", description="Confirm logout dialog"),
        TestStep(step_number=12, action=ActionType.ASSERT_TEXT, locator_strategy=LocatorStrategy.CSS, selector_value="body", expected_value="signed out", description="Verify signed out confirmation screen"),
    ],
    expected_result="System successfully opens Manage Service Quotations, waits 20 seconds, and logs out.",
)

suite11 = TestSuite(
    suite_id="SUITE-KAN-11",
    requirement_key="KAN-11",
    version=1,
    test_cases=[tc11_1],
)

p11 = save_regression_suite(
    suite11,
    suite_name="SAP Manage Service Quotations Navigation Suite",
    description="End-to-end verified SAP logon, Fiori tile navigation, pause, and sign out.",
    last_run_status="100% Passed (12/12)",
    tags=["sap", "fiori", "quotations", "regression"],
)

# Suite KAN-9: SAP Authentication & Security Suite (Positive & Negative)
tc9_pos = TestCase(
    id="TC-01",
    requirement_key="KAN-9",
    source_ac_id="AC-01",
    title="Valid SAP S/4HANA Authentication",
    objective="Validate successful logon and session termination with valid credentials.",
    category=TestCategory.POSITIVE,
    priority="High",
    steps=[
        TestStep(step_number=1, action=ActionType.NAVIGATE, description="Navigate to SAP logon page"),
        TestStep(step_number=2, action=ActionType.FILL, locator_strategy=LocatorStrategy.CSS, selector_value="#USERNAME_FIELD-inner", input_value="MYRAR1", description="Input username"),
        TestStep(step_number=3, action=ActionType.FILL, locator_strategy=LocatorStrategy.CSS, selector_value="#PASSWORD_FIELD-inner", input_value="Welcome@123", description="Input password"),
        TestStep(step_number=4, action=ActionType.CLICK, locator_strategy=LocatorStrategy.CSS, selector_value="#LOGIN_LINK", description="Click Log On"),
        TestStep(step_number=5, action=ActionType.ASSERT_TEXT, locator_strategy=LocatorStrategy.CSS, selector_value="body", expected_value="Home", description="Verify home screen"),
        TestStep(step_number=6, action=ActionType.CLICK, locator_strategy=LocatorStrategy.CSS, selector_value="#meAreaHeaderButton", description="Click user profile"),
        TestStep(step_number=7, action=ActionType.CLICK, locator_strategy=LocatorStrategy.CSS, selector_value="button:has-text('Sign Out'), #logoutBtn", description="Click Sign Out"),
        TestStep(step_number=8, action=ActionType.CLICK, locator_strategy=LocatorStrategy.CSS, selector_value="button:has-text('OK'), button:has-text('Sign Out')", description="Confirm Sign Out"),
        TestStep(step_number=9, action=ActionType.ASSERT_TEXT, locator_strategy=LocatorStrategy.CSS, selector_value="body", expected_value="signed out", description="Verify logged off"),
    ],
    expected_result="User successfully authenticated and signed out.",
)

tc9_neg = TestCase(
    id="TC-02",
    requirement_key="KAN-9",
    source_ac_id="AC-02",
    title="Invalid Credentials Security Boundary",
    objective="Validate that incorrect credentials trigger the SAP authentication error message.",
    category=TestCategory.NEGATIVE,
    priority="High",
    steps=[
        TestStep(step_number=1, action=ActionType.NAVIGATE, description="Navigate to SAP logon page"),
        TestStep(step_number=2, action=ActionType.FILL, locator_strategy=LocatorStrategy.CSS, selector_value="#USERNAME_FIELD-inner", input_value="INVALID_USER", description="Enter invalid user"),
        TestStep(step_number=3, action=ActionType.FILL, locator_strategy=LocatorStrategy.CSS, selector_value="#PASSWORD_FIELD-inner", input_value="WrongPass!123", description="Enter wrong password"),
        TestStep(step_number=4, action=ActionType.CLICK, locator_strategy=LocatorStrategy.CSS, selector_value="#LOGIN_LINK", description="Click Log On"),
        TestStep(step_number=5, action=ActionType.ASSERT_TEXT, locator_strategy=LocatorStrategy.CSS, selector_value="body", expected_value="Client, name, or password is not correct", description="Verify error notification"),
    ],
    expected_result="System rejects login with warning message.",
)

suite9 = TestSuite(
    suite_id="SUITE-KAN-9",
    requirement_key="KAN-9",
    version=1,
    test_cases=[tc9_pos, tc9_neg],
)

p9 = save_regression_suite(
    suite9,
    suite_name="SAP S/4HANA Authentication & Boundary Regression Suite",
    description="Validates positive session establishment and negative authentication boundary protection.",
    last_run_status="100% Passed (2/2)",
    tags=["sap", "security", "auth", "regression"],
)

print(f"Successfully seeded:\n - {p11}\n - {p9}")

