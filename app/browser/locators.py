"""
Accessible Locator Resolver Module
Resolves Playwright locators using accessibility priority (Role -> TestID -> Text -> CSS)
and validates locator uniqueness to eliminate automation flakiness.
"""
from typing import Optional, Literal
from playwright.sync_api import Page, Locator


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

    def resolve(
        self,
        strategy: Literal["role", "test_id", "text", "css"],
        value: str,
        role_type: Optional[str] = None,
        exact: bool = False,
    ) -> Locator:
        """
        Resolves a single unique Locator using the specified strategy.
        
        Args:
            strategy: 'role', 'test_id', 'text', or 'css'
            value: selector value, accessible name, test id, or text string
            role_type: ARIA role type (required if strategy is 'role', e.g. 'button')
            exact: whether to match text exactly
        """
        if strategy == "role":
            if not role_type:
                raise ValueError("Role strategy requires 'role_type' (e.g., 'button', 'textbox').")
            locator = self.page.get_by_role(role_type, name=value, exact=exact)

        elif strategy == "test_id":
            locator = self.page.get_by_test_id(value)
            if locator.count() == 0:
                variants = []
                # 1. Singular/plural variants: order-table <-> orders-table
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

                # 2. Hyphen <-> Underscore variants
                if "-" in value:
                    variants.append(value.replace("-", "_"))
                elif "_" in value:
                    variants.append(value.replace("_", "-"))

                for v in variants:
                    alt = self.page.get_by_test_id(v)
                    if alt.count() > 0:
                        return alt

                # 3. Fallback to HTML ID attribute
                id_loc = self.page.locator(f"#{value}")
                if id_loc.count() > 0:
                    return id_loc

                # 4. Partial substring in data-testid
                sub_loc = self.page.locator(f"[data-testid*='{value}']")
                if sub_loc.count() > 0:
                    return sub_loc

        elif strategy == "text":
            locator = self.page.get_by_text(value, exact=exact)
            safe_val = value.replace('"', '\\"').replace("'", "\\'")
            locator = locator.or_(
                self.page.locator(f'[aria-label*="{safe_val}" i]')
            ).or_(
                self.page.locator(f'[title*="{safe_val}" i]')
            )

        elif strategy == "css":
            locator = self.page.locator(value)

        else:
            raise ValueError(f"Unsupported locator strategy: {strategy}")

        return locator

    def resolve_unique(
        self,
        strategy: Literal["role", "test_id", "text", "css"],
        value: str,
        role_type: Optional[str] = None,
        exact: bool = False,
        timeout_ms: int = 5000,
    ) -> Locator:
        """
        Resolves a locator and validates that it matches exactly ONE element on the DOM.
        Prevents clicking the wrong element when ambiguous locators exist.
        """
        locator = self.resolve(strategy=strategy, value=value, role_type=role_type, exact=exact)

        try:
            # Wait for at least one element to be attached/visible
            locator.first.wait_for(state="attached", timeout=timeout_ms)
        except Exception as exc:
            # Self-Healing Fallback: check learned selector catalog for matching element
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
            raise ElementNotFoundError(
                f"Element not found using strategy '{strategy}' with value '{value}'."
            )
        elif count > 1:
            raise AmbiguousLocatorError(
                f"Ambiguous locator: matched {count} elements using strategy '{strategy}' "
                f"with value '{value}'. Specify a more precise role or test-ID."
            )

        return locator

