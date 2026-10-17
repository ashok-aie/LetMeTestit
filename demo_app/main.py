"""
SAP Fiori Style Material & Sales Order Demo Application
Provides a realistic enterprise ERP screen for deterministic Playwright test automation.
"""
from typing import List, Optional
from enum import Enum
from datetime import datetime
from fastapi import FastAPI, Request, Form, HTTPException, status
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

app = FastAPI(title="SAP S/4HANA Sales & Material Order Management")
templates = Jinja2Templates(directory="demo_app/templates")


class OrderStatus(str, Enum):
    DRAFT = "Draft"
    SUBMITTED = "Submitted"
    APPROVED = "Approved"
    DISPATCHED = "Dispatched"
    COMPLETED = "Completed"
    CANCELLED = "Cancelled"


class DeliveryPriority(str, Enum):
    STANDARD = "Standard"
    URGENT = "Urgent"
    EXPRESS = "Express"


# Catalog of available materials with unit prices
MATERIAL_CATALOG = {
    "MAT-1001": {"name": "Industrial Steel Coil (Grade A)", "unit_price": 450.00, "unit": "TO"},
    "MAT-2002": {"name": "Titanium Hex Bolts (Box 500)", "unit_price": 120.00, "unit": "BX"},
    "MAT-3003": {"name": "Hydraulic High-Pressure Valve", "unit_price": 850.00, "unit": "PC"},
    "MAT-4004": {"name": "Polyethylene Raw Resin Pellets", "unit_price": 280.00, "unit": "KG"},
}


class OrderItem(BaseModel):
    material_id: str
    material_name: str
    quantity: int
    unit_price: float
    total_price: float
    unit: str


class SalesOrder(BaseModel):
    order_id: str
    customer_id: str
    customer_name: str
    created_at: str
    status: OrderStatus
    priority: DeliveryPriority
    items: List[OrderItem]
    total_amount: float


# In-memory database with deterministic initial seed data
INITIAL_ORDERS: List[SalesOrder] = [
    SalesOrder(
        order_id="SO-45000101",
        customer_id="CUST-1001",
        customer_name="Global Heavy Industries Ltd",
        created_at="2026-10-10 09:30",
        status=OrderStatus.APPROVED,
        priority=DeliveryPriority.STANDARD,
        items=[
            OrderItem(
                material_id="MAT-1001",
                material_name=MATERIAL_CATALOG["MAT-1001"]["name"],
                quantity=4,
                unit_price=450.00,
                total_price=1800.00,
                unit="TO",
            )
        ],
        total_amount=1800.00,
    ),
    SalesOrder(
        order_id="SO-45000102",
        customer_id="CUST-2002",
        customer_name="Aerospace Precision Components",
        created_at="2026-10-11 08:15",
        status=OrderStatus.SUBMITTED,
        priority=DeliveryPriority.URGENT,
        items=[
            OrderItem(
                material_id="MAT-2002",
                material_name=MATERIAL_CATALOG["MAT-2002"]["name"],
                quantity=10,
                unit_price=120.00,
                total_price=1200.00,
                unit="BX",
            )
        ],
        total_amount=1200.00,
    ),
]

# Active runtime store
orders_db: List[SalesOrder] = [order.model_copy(deep=True) for order in INITIAL_ORDERS]
order_counter = 45000103


@app.get("/health")
def health_check():
    """Health check endpoint for automated orchestrators."""
    return {"status": "healthy", "service": "SAP_SalesOrder_Demo", "timestamp": datetime.utcnow().isoformat()}


@app.get("/", response_class=HTMLResponse)
def index(request: Request, error: Optional[str] = None, success: Optional[str] = None):
    """Renders the main SAP Fiori Material & Sales Order management dashboard."""
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "orders": orders_db,
            "catalog": MATERIAL_CATALOG,
            "error_msg": error,
            "success_msg": success,
            "total_orders": len(orders_db),
            "pending_approval": sum(1 for o in orders_db if o.status == OrderStatus.SUBMITTED),
        },
    )


@app.post("/orders/create")
def create_order(
    customer_id: str = Form(""),
    customer_name: str = Form(""),
    material_id: str = Form(""),
    quantity: str = Form(""),
    priority: str = Form("Standard"),
):
    """Creates a new Sales/Material Order with enterprise validation rules."""
    global order_counter

    # 1. Validation: Customer ID
    clean_cust_id = customer_id.strip()
    if not clean_cust_id:
        return RedirectResponse(
            url="/?error=Validation+Error:+Customer+ID+(Sold-to+Party)+is+mandatory.",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    # 2. Validation: Material Selection
    if material_id not in MATERIAL_CATALOG:
        return RedirectResponse(
            url="/?error=Validation+Error:+Please+select+a+valid+Material+from+the+SAP+catalog.",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    # 3. Validation: Quantity
    try:
        qty_int = int(quantity.strip())
        if qty_int <= 0:
            raise ValueError()
    except (ValueError, AttributeError):
        return RedirectResponse(
            url="/?error=Validation+Error:+Order+Quantity+must+be+a+positive+integer+greater+than+zero.",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    if qty_int > 500:
        return RedirectResponse(
            url="/?error=Validation+Error:+Single+order+quantity+exceeds+plant+limit+(max+500).",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    mat_info = MATERIAL_CATALOG[material_id]
    item_total = round(qty_int * mat_info["unit_price"], 2)

    new_order = SalesOrder(
        order_id=f"SO-{order_counter}",
        customer_id=clean_cust_id,
        customer_name=customer_name.strip() or f"Customer {clean_cust_id}",
        created_at=datetime.now().strftime("%Y-%m-%d %H:%M"),
        status=OrderStatus.SUBMITTED,
        priority=DeliveryPriority(priority) if priority in DeliveryPriority._value2member_map_ else DeliveryPriority.STANDARD,
        items=[
            OrderItem(
                material_id=material_id,
                material_name=mat_info["name"],
                quantity=qty_int,
                unit_price=mat_info["unit_price"],
                total_price=item_total,
                unit=mat_info["unit"],
            )
        ],
        total_amount=item_total,
    )
    order_counter += 1
    orders_db.insert(0, new_order)

    return RedirectResponse(
        url=f"/?success=Sales+Order+{new_order.order_id}+created+successfully+for+{clean_cust_id}.",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@app.post("/orders/{order_id}/advance")
def advance_order_status(order_id: str):
    """Advances an order along its enterprise lifecycle: Submitted -> Approved -> Dispatched -> Completed."""
    for order in orders_db:
        if order.order_id == order_id:
            if order.status == OrderStatus.SUBMITTED:
                order.status = OrderStatus.APPROVED
            elif order.status == OrderStatus.APPROVED:
                order.status = OrderStatus.DISPATCHED
            elif order.status == OrderStatus.DISPATCHED:
                order.status = OrderStatus.COMPLETED
            return RedirectResponse(
                url=f"/?success=Order+{order_id}+status+advanced+to+{order.status.value}.",
                status_code=status.HTTP_303_SEE_OTHER,
            )
    return RedirectResponse(url=f"/?error=Order+{order_id}+not+found.", status_code=status.HTTP_303_SEE_OTHER)


@app.post("/orders/{order_id}/cancel")
def cancel_order(order_id: str):
    """Cancels an existing order if not already completed."""
    for order in orders_db:
        if order.order_id == order_id:
            if order.status == OrderStatus.COMPLETED:
                return RedirectResponse(
                    url=f"/?error=Cannot+cancel+completed+order+{order_id}.",
                    status_code=status.HTTP_303_SEE_OTHER,
                )
            order.status = OrderStatus.CANCELLED
            return RedirectResponse(
                url=f"/?success=Order+{order_id}+cancelled+successfully.",
                status_code=status.HTTP_303_SEE_OTHER,
            )
    return RedirectResponse(url=f"/?error=Order+{order_id}+not+found.", status_code=status.HTTP_303_SEE_OTHER)


@app.post("/reset")
def reset_database():
    """Resets the demo orders database back to the deterministic initial state."""
    global orders_db, order_counter
    orders_db = [order.model_copy(deep=True) for order in INITIAL_ORDERS]
    order_counter = 45000103
    return RedirectResponse(
        url="/?success=Enterprise+database+reset+to+initial+seed+state.",
        status_code=status.HTTP_303_SEE_OTHER,
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("demo_app.main:app", host="127.0.0.1", port=8000, reload=False)
