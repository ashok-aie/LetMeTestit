"""
Centralized Flow Registry for Application Domain Workflows (SAP Fiori, S/4HANA, RAR, Demo App).
Acts as the Single Source of Truth (DRY) for step definitions, locator selectors,
parameter extraction, and few-shot prompt serialization.
"""
from app.flows.sap_flows import (
    extract_sap_quotation_parameters,
    build_sap_login_steps,
    build_sap_logoff_steps,
    build_service_quotation_steps,
    build_service_quotation_drilldown_item_steps,
    build_service_quotation_item_pricing_steps,
    build_revenue_contract_steps,
    build_monolithic_rar_steps,
    build_evidence_capture_steps,
    build_bundle_validation_steps,
    build_mandatory_validation_steps,
    build_item_entry_steps,
    build_header_creation_steps,
    build_release_accept_steps,
    build_pricing_condition_steps,
    build_duration_dates_steps,
    steps_to_few_shot_json,
    DEFAULT_MRC_URL,
)

__all__ = [
    "extract_sap_quotation_parameters",
    "build_sap_login_steps",
    "build_sap_logoff_steps",
    "build_service_quotation_steps",
    "build_service_quotation_drilldown_item_steps",
    "build_service_quotation_item_pricing_steps",
    "build_revenue_contract_steps",
    "build_monolithic_rar_steps",
    "build_evidence_capture_steps",
    "build_bundle_validation_steps",
    "build_mandatory_validation_steps",
    "build_item_entry_steps",
    "build_header_creation_steps",
    "build_release_accept_steps",
    "build_pricing_condition_steps",
    "build_duration_dates_steps",
    "steps_to_few_shot_json",
    "DEFAULT_MRC_URL",
]

