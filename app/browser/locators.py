"""
Accessible Locator Resolver Module
Resolves Playwright locators using accessibility priority (Role -> TestID -> Text -> CSS)
and validates locator uniqueness to eliminate automation flakiness.
"""
import re
from typing import Optional, Literal, Union
from playwright.sync_api import Page, Locator, Frame


class LocatorResolutionError(Exception):
    """Base exception for locator resolution failures."""
    pass


class ElementNotFoundError(LocatorResolutionError):
    """Raised when an element cannot be found on the page."""
    pass


class AmbiguousLocatorError(LocatorResolutionError):
    """Raised when a selector matches multiple elements without an index."""
    pass


class LocatorResolver:
    """Resolves and validates Playwright locators with strict accessibility priority."""

    def __init__(self, page: Page):
        self.page = page

    def _resolve_on_target(
        self,
        target: Union[Page, Frame],
        strategy: Literal["role", "test_id", "text", "css"],
        value: str,
        role_type: Optional[str] = None,
        exact: bool = False,
    ) -> Locator:
        """Resolves a locator on a specific Page or Frame target."""
        if strategy == "role":
            if not role_type:
                raise ValueError("Role strategy requires 'role_type' (e.g., 'button', 'textbox').")
            if role_type == "link" and value.lower() in ("month", "months"):
                return target.get_by_role("link", name=re.compile(r"month", re.I)).or_(target.locator("a:has-text('Month')"))
            elif role_type == "link" and value.lower() in ("year", "years"):
                return target.get_by_role("link", name=re.compile(r"year", re.I)).or_(target.locator("a:has-text('Year')"))
            elif role_type == "button" and value.strip().lower() == "back":
                return (
                    target.locator(
                        "[data-help-id*='cancel'], "
                        "[data-help-id*='I_cancel'], "
                        "a.th-bt[aria-label='Back'], "
                        "a[aria-label='Back']:not([id*='pag_bck']), "
                        "[id*='thtmlb_button'][aria-label='Back'], "
                        "a.th-bt:has-text('Back')"
                    )
                    .or_(target.get_by_role("button", name=value, exact=exact))
                )
            elif role_type == "button" and any(k in value.lower() for k in ("save (ctrl+s)", "save")):
                return (
                    target.locator(
                        "[data-help-id*='I_save'], "
                        "[data-help-id*='save'], "
                        "a[aria-label*='Save (Ctrl+S)'], "
                        "a[title*='Save (Ctrl+S)'], "
                        "[id*='thtmlb_button'][aria-label*='Save'], "
                        "a.th-bt:has-text('Save')"
                    )
                    .or_(target.get_by_role("button", name=value, exact=exact))
                )
            elif role_type == "dialog":
                return target.get_by_role("dialog", name=re.compile(re.escape(value), re.I)).or_(target.locator(f"[role='dialog']:has-text('{value}')")).or_(target.locator(".sapMDialog, [role='dialog']"))
            elif role_type == "textbox" and any(k in value.lower() for k in ("description", "desc")):
                clean_name = value.rstrip(":").strip()
                return (
                    target.locator(
                        "[id*='btadminh_struct.description'], "
                        "input[id*='description' i], "
                        "textarea[id*='description' i], "
                        "[aria-label*='Description' i], "
                        "[title*='Description' i]"
                    )
                    .or_(target.get_by_role("textbox", name=re.compile(r"description", re.I)))
                    .or_(target.get_by_role("textbox", name=clean_name))
                    .or_(target.get_by_role(role_type, name=value, exact=exact))
                )
            elif role_type == "textbox" and any(k in value.lower() for k in ("sold-to", "soldto", "party")):
                clean_name = value.rstrip(":").strip()
                return (
                    target.locator(
                        "input[id*='SoldToParty' i], "
                        "input[id*='sold_to' i], "
                        "input[id*='partner' i], "
                        "[aria-label*='Sold-to' i], "
                        "[title*='Sold-to' i]"
                    )
                    .or_(target.get_by_role("textbox", name=re.compile(r"sold-to", re.I)))
                    .or_(target.get_by_role("textbox", name=clean_name))
                    .or_(target.get_by_role(role_type, name=value, exact=exact))
                )
            elif role_type == "textbox" and any(k in value.lower() for k in ("operational document", "operationaldoc")):
                clean_name = value.rstrip(":").strip()
                return (
                    target.get_by_role("textbox", name=re.compile(r"operational\s*document", re.I))
                    .or_(target.locator("[role='dialog'] input[id*='OperationalDocument' i]"))
                    .or_(target.locator("[role='dialog'] input[id*='operational_document' i]"))
                    .or_(target.locator("[role='dialog'] input[id*='OperationalDoc' i]"))
                    .or_(target.locator("input[aria-label*='Operational Document' i]"))
                    .or_(target.locator("input[id*='OperationalDocument' i]"))
                    .or_(target.locator("[role='dialog'] input[placeholder*='Operational Document' i]"))
                    .or_(target.locator("[role='dialog'] label:has-text('Operational Document') ~ div input"))
                    .or_(target.locator("[role='dialog'] label:has-text('Operational Document') + div input"))
                    .or_(target.get_by_role("textbox", name=clean_name))
                )
            return target.get_by_role(role_type, name=value, exact=exact)

        elif strategy == "test_id":
            locator = target.get_by_test_id(value)
            if locator.count() == 0:
                variants = []
                if value.endswith("s"):
                    variants.append(value[:-1])
                else:
                    variants.append(f"{value}s")

                if "-" in value:
                    parts = value.split("-")
                    if not parts[0].endswith("s"):
                        variants.append(f"{parts[0]}s-{'-'.join(parts[1:])}")
                    elif parts[0].endswith("s"):
                        variants.append(f"{parts[0][:-1]}-{'-'.join(parts[1:])}")

                if "-" in value:
                    variants.append(value.replace("-", "_"))
                elif "_" in value:
                    variants.append(value.replace("_", "-"))

                for v in variants:
                    alt = target.get_by_test_id(v)
                    if alt.count() > 0:
                        return alt

                id_loc = target.locator(f"#{value}")
                if id_loc.count() > 0:
                    return id_loc

                sub_loc = target.locator(f"[data-testid*='{value}']")
                if sub_loc.count() > 0:
                    return sub_loc
            return locator

        elif strategy == "text":
            val_lower = value.lower()
            if any(k in val_lower for k in ("manage revenue contracts", "revenue contracts tile")):
                return target.locator(
                    "[title*='Manage Revenue Contracts'], "
                    "a[aria-label*='Manage Revenue Contracts' i], "
                    "div[aria-label*='Manage Revenue Contracts' i], "
                    "[role='link']:has-text('Manage Revenue Contracts'), "
                    ".sapUshellSearchResultListItem:has-text('Manage Revenue Contracts'), "
                    ".sapMGT:has-text('Manage Revenue Contracts'), "
                    ".sapUshellTile:has-text('Manage Revenue Contracts'), "
                    "[role='option']:has-text('Manage Revenue Contracts'), "
                    "a:has-text('Manage Revenue Contracts'), "
                    "div[role='button']:has-text('Manage Revenue Contracts')"
                ).or_(target.get_by_text("Manage Revenue Contracts", exact=False))
            elif "selection column" in val_lower:
                return target.locator(
                    ".sapUiTableSelCol, "
                    "[aria-label*='Selection column' i], "
                    "[aria-label*='Selection Column' i], "
                    "[role='dialog'] table tbody tr:first-child td:first-child, "
                    "[role='dialog'] .sapUiTableColRowHdr"
                ).or_(target.get_by_text("Selection column", exact=False))
            elif any(k in val_lower for k in ("operational document", "operationaldoc")):
                return (
                    target.get_by_role("textbox", name=re.compile(r"operational\s*document", re.I))
                    .or_(target.locator("[role='dialog'] input[id*='OperationalDocument' i]"))
                    .or_(target.locator("[role='dialog'] input[id*='operational_document' i]"))
                    .or_(target.locator("input[aria-label*='Operational Document' i]"))
                    .or_(target.locator("input[id*='OperationalDocument' i]"))
                    .or_(target.locator("[role='dialog'] label:has-text('Operational Document') ~ div input"))
                )

            locator = target.get_by_text(value, exact=exact)
            safe_val = value.replace('"', '\\"').replace("'", "\\'")
            locator = locator.or_(
                target.locator(f'[aria-label*="{safe_val}" i]')
            ).or_(
                target.locator(f'[title*="{safe_val}" i]')
            )
            return locator

        elif strategy == "css":
            if any(k in value for k in ("meAreaHeaderButton", "userActionsMenuHeaderButton")):
                return target.locator(
                    "#userActionsMenuHeaderButton, #meAreaHeaderButton, "
                    "[id*='userActionsMenuHeaderButton'], [id*='meAreaHeaderButton'], "
                    ".sapUshellShellHeadItm[title*='User'], button[aria-label*='User Settings'], "
                    "button[title*='User Actions'], [data-sap-ui*='userActions']"
                )
            elif any(k in value.lower() for k in ("logoutconfirm", "confirm sign out", "#logoutconfirm", "sign out confirm")):
                return target.locator(
                    "[role='dialog'] button:has-text('OK'), "
                    ".sapMDialog button:has-text('OK'), "
                    ".sapMDialogFooter button:has-text('OK'), "
                    "[role='dialog'] .sapMBtn:has-text('OK'), "
                    "[role='dialog'] bdi:has-text('OK'), "
                    "button[id*='logoutConfirm'], #logoutConfirm"
                )
            elif "logoutbtn" in value.lower() or ("sign out" in value.lower() and "button" in value.lower()):
                return (
                    target.locator(
                        "button:has-text('Sign Out'), #logoutBtn, [id*='logoutBtn'], "
                        "div[role='button']:has-text('Sign Out'), span:has-text('Sign Out'), "
                        "[aria-label*='Sign Out']"
                    )
                    .or_(target.get_by_text("Sign Out"))
                )
            elif "thtmlboverviewpagebox" in value.lower() or ("edit" in value.lower() and ("button" in value.lower() or "tr" in value.lower())):
                return (
                    target.locator(
                        "button:has-text('Edit'), a:has-text('Edit'), [title*='Edit'], [aria-label*='Edit'], "
                        "div[role='button']:has-text('Edit'), span:has-text('Edit'), "
                        "#thtmlbOverviewPageBox tr [title*='Edit'], #thtmlbOverviewPageBox tr [aria-label*='Edit']"
                    )
                    .or_(target.get_by_text("Edit (Ctrl+E)"))
                    .or_(target.get_by_text("Edit"))
                )
            elif any(k in value.lower() for k in ("manage revenue contracts", "revenue contracts tile")):
                return target.locator(
                    "[title*='Manage Revenue Contracts'], "
                    "a[aria-label*='Manage Revenue Contracts' i], "
                    "div[aria-label*='Manage Revenue Contracts' i], "
                    "[role='link']:has-text('Manage Revenue Contracts'), "
                    ".sapUshellSearchResultListItem:has-text('Manage Revenue Contracts'), "
                    ".sapMGT:has-text('Manage Revenue Contracts'), "
                    ".sapUshellTile:has-text('Manage Revenue Contracts'), "
                    "[role='option']:has-text('Manage Revenue Contracts'), "
                    "a:has-text('Manage Revenue Contracts'), "
                    "div[role='button']:has-text('Manage Revenue Contracts')"
                ).or_(target.get_by_text("Manage Revenue Contracts", exact=False))
            elif "selection column" in value.lower():
                return target.locator(
                    ".sapUiTableSelCol, "
                    "[aria-label*='Selection column' i], "
                    "[aria-label*='Selection Column' i], "
                    "[role='dialog'] table tbody tr:first-child td:first-child, "
                    "[role='dialog'] .sapUiTableColRowHdr"
                ).or_(target.get_by_text("Selection column", exact=False))
            elif any(k in value.lower() for k in ("operational document", "operationaldoc")):
                return (
                    target.locator(
                        "[role='dialog'] input[id*='OperationalDocument' i], "
                        "[role='dialog'] input[id*='operational_document' i], "
                        "[role='dialog'] input[id*='OperationalDoc' i], "
                        "[role='dialog'] input[aria-label*='Operational Document' i], "
                        "input[aria-label*='Operational Document' i], "
                        "input[id*='OperationalDocument' i], "
                        "[role='dialog'] label:has-text('Operational Document') ~ div input, "
                        "[role='dialog'] label:has-text('Operational Document') + div input, "
                        "[role='dialog'] input[placeholder*='Operational Document' i]"
                    )
                    .or_(target.get_by_role("textbox", name=re.compile(r"operational\s*document", re.I)))
                )
            elif any(k in value.lower() for k in ("quantity", "qty")):
                return (
                    target.locator(
                        "input[id*='btadmini_table[1].quantity'], "
                        "input[name*='btadmini_table[1].quantity'], "
                        "input[id*='btadmini_table'][id*='quantity'], "
                        "input[name*='btadmini_table'][name*='quantity'], "
                        "input[id*='quantity']:not([readonly]), "
                        "input[id*='quantity'], "
                        "[id*='btadmini_table'] input[id*='quantity'], "
                        "input[aria-label*='Quantity' i], "
                        "input[title*='Quantity' i]"
                    )
                    .or_(target.locator("input[id*='quantity']"))
                )
            elif "," in value:
                # Comma-separated multi-candidate selector
                candidates = [c.strip() for c in value.split(",") if c.strip()]
                combined = None
                for c in candidates:
                    try:
                        if c.startswith("text="):
                            t_val = c[5:].strip("'\"")
                            cand_loc = target.get_by_text(t_val)
                        else:
                            clean_c = re.sub(r"text=['\"]([^'\"]+)['\"]", r":has-text('\1')", c)
                            cand_loc = target.locator(clean_c)
                        combined = cand_loc if combined is None else combined.or_(cand_loc)
                    except Exception:
                        continue
                return combined if combined is not None else target.locator(value)
            elif value.startswith("text="):
                t_val = value[5:].strip("'\"")
                return target.get_by_text(t_val)
            else:
                return target.locator(value)

        else:
            raise ValueError(f"Unsupported locator strategy: {strategy}")

    def resolve(
        self,
        strategy: Literal["role", "test_id", "text", "css"],
        value: str,
        role_type: Optional[str] = None,
        exact: bool = False,
    ) -> Locator:
        """
        Resolves a single unique Locator using the specified strategy on the active Page.
        """
        return self._resolve_on_target(self.page, strategy=strategy, value=value, role_type=role_type, exact=exact)

    def resolve_unique(
        self,
        strategy: Literal["role", "test_id", "text", "css"],
        value: str,
        role_type: Optional[str] = None,
        exact: bool = False,
        timeout_ms: int = 5000,
    ) -> Locator:
        """
        Resolves a locator and validates that it matches an element on the DOM or child frames.
        """
        locator = self.resolve(strategy=strategy, value=value, role_type=role_type, exact=exact)

        try:
            # Wait for at least one element to be attached/visible
            locator.first.wait_for(state="attached", timeout=timeout_ms)
        except Exception as exc:
            # 1. Automatic Iframe Search: Check all child frames (e.g. SAP CRM / WebGUI iframes like __container20-iframe)
            try:
                for frame in self.page.frames:
                    if frame == self.page.main_frame:
                        continue
                    try:
                        frame_loc = self._resolve_on_target(frame, strategy=strategy, value=value, role_type=role_type, exact=exact)
                        if frame_loc.count() > 0:
                            return frame_loc
                    except Exception:
                        continue
            except Exception:
                pass

            # 2. Self-Healing Fallback: check learned selector catalog for matching element
            try:
                from app.storage.repository import get_learned_selectors
                catalog = get_learned_selectors()
                clean_val = value.strip().lower()
                for item in catalog:
                    lbl = item.get("element_label", "").lower()
                    sel = item.get("selector", "")
                    if (clean_val in lbl or lbl in clean_val or clean_val == sel.lower()) and sel != value:
                        fallback_strat = item.get("strategy", "css")
                        fallback_loc = self.resolve(
                            strategy=fallback_strat,
                            value=sel,
                            role_type=item.get("role_type"),
                            exact=False,
                        )
                        try:
                            fallback_loc.first.wait_for(state="attached", timeout=2000)
                            if fallback_loc.count() > 0:
                                return fallback_loc
                        except Exception:
                            continue
            except Exception:
                pass

            raise ElementNotFoundError(
                f"Element not found using strategy '{strategy}' with value '{value}'."
            ) from exc

        count = locator.count()
        if count == 0:
            # Check frames before failing
            for frame in self.page.frames:
                if frame == self.page.main_frame:
                    continue
                try:
                    frame_loc = self._resolve_on_target(frame, strategy=strategy, value=value, role_type=role_type, exact=exact)
                    if frame_loc.count() > 0:
                        return frame_loc
                except Exception:
                    continue
            raise ElementNotFoundError(
                f"Element not found using strategy '{strategy}' with value '{value}'."
            )
        elif count > 1:
            if any(k in value for k in ("meAreaHeaderButton", "userActionsMenuHeaderButton", "Sign Out", "OK")):
                return locator.first
            raise AmbiguousLocatorError(
                f"Ambiguous locator: matched {count} elements using strategy '{strategy}' "
                f"with value '{value}'. Specify a more precise role or test-ID."
            )

        return locator

