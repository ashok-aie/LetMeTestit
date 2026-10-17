"""
Phase 3 Integration Test: SAP Sales & Material Order Demo App
Verifies all enterprise endpoints, validation errors, and lifecycle state changes.
"""
import pytest
from fastapi.testclient import TestClient
from demo_app.main import app, OrderStatus


@pytest.fixture
def client():
    # Reset DB before tests
    c = TestClient(app)
    c.post("/reset")
    return c


def test_sap_dashboard_loads(client: TestClient):
    """Verify that the SAP S/4HANA dashboard HTML renders with key elements."""
    res = client.get("/")
    assert res.status_code == 200
    assert "SAP" in res.text
    assert "S/4HANA Sales &amp; Material Management" in res.text
    assert "data-testid=\"orders-table\"" in res.text
    assert "SO-45000101" in res.text


def test_sap_create_order_valid(client: TestClient):
    """Verify that a valid material order is created and totals calculated."""
    payload = {
        "customer_id": "CUST-9999",
        "customer_name": "Zenith Steel Works",
        "material_id": "MAT-1001",
        "quantity": "5",
        "priority": "Express",
    }
    res = client.post("/orders/create", data=payload, follow_redirects=True)
    assert res.status_code == 200
    assert "created successfully for CUST-9999" in res.text
    assert "CUST-9999" in res.text
    # 5 * $450 = $2250.00
    assert "$2250.00" in res.text


def test_sap_validation_missing_customer(client: TestClient):
    """Verify enterprise validation error when Sold-to Party is empty."""
    payload = {
        "customer_id": "   ",
        "material_id": "MAT-1001",
        "quantity": "2",
    }
    res = client.post("/orders/create", data=payload, follow_redirects=True)
    assert res.status_code == 200
    assert "Customer ID (Sold-to Party) is mandatory" in res.text
    assert "data-testid=\"error-banner\"" in res.text


def test_sap_validation_invalid_quantity(client: TestClient):
    """Verify enterprise validation error when quantity is zero or negative."""
    payload = {
        "customer_id": "CUST-1001",
        "material_id": "MAT-1001",
        "quantity": "-3",
    }
    res = client.post("/orders/create", data=payload, follow_redirects=True)
    assert res.status_code == 200
    assert "Order Quantity must be a positive integer" in res.text


def test_sap_order_lifecycle_advancement(client: TestClient):
    """Verify order state transitions from Submitted to Approved."""
    # Reset to known seed
    client.post("/reset")
    # SO-45000102 is initially Submitted in seed
    res = client.post("/orders/SO-45000102/advance", follow_redirects=True)
    assert res.status_code == 200
    assert "status advanced to Approved" in res.text

