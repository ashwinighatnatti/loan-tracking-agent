"""Collateral Information section. A loan can have several collateral properties; the property select
shows one at a time, and choosing another re-renders this section and the Insurance Lines below it."""
from __future__ import annotations

from typing import List, Optional, Union

from playwright.sync_api import Page

from loan_agent.loan_schema.loan import Collateral

from .base import Section
from .insurance_line import InsuranceLines


class CollateralInformation(Section):
    ROOT = '[data-section="collateral-information"]'
    PROPERTY_SELECT = '[data-field="collateral_property"]'

    # Mirrors COLLATERAL_ALIASES in loan-detail-page.html, inverted (page data-field -> schema field).
    FIELD_MAP = {
        "property_description": "property_description",
        "property_usage": "property_usage",
        "number_of_property": "number_of_property",
        "occupancy_status": "occupancy_status",
        "property_address1": "property_address_1",
        "property_city": "city",
        "property_state": "state",
        "property_zip": "zip",
        "property_type": "property_type",
        "appraised_value": "appraised_value",
        "lien_position": "lien_position",
        "flood_zone": "flood_zone",
        "flood_waiver": "flood_waiver",
        "flood_required": "flood_required",
        "loma_on_file": "loma_on_file",
        "property_id": "property_id",
        "insurable_value": "insurable_value",
        "actual_cash_value": "actual_cash_value",
        "required_hazard_coverage": "required_hazard_coverage",
        "required_flood_coverage": "required_flood_coverage",
        "grandfathered": "grandfathered",
        "track_only": "chk_track_only",
    }

    def __init__(self, page: Page):
        super().__init__(page)
        self.insurance_lines = InsuranceLines(page)

    def property_names(self) -> List[str]:
        return [t.strip() for t in self.root.locator(f"{self.PROPERTY_SELECT} option").all_text_contents()]

    def read(self) -> Collateral:
        """The collateral currently shown, with its insurance lines."""
        collateral = Collateral.from_dict(self.read_mapped())
        collateral.property_info = self.root.locator(self.PROPERTY_SELECT).evaluate(
            "el => el.selectedIndex < 0 ? '' : el.options[el.selectedIndex].text.trim()")
        # "21 BIRCHWOOD CT BAYONNE, NJ 07002", as in loan.json
        street = " ".join(filter(None, (collateral.property_address_1, collateral.city)))
        region = " ".join(filter(None, (collateral.state, collateral.zip)))
        collateral.property_address = ", ".join(filter(None, (street, region)))
        collateral.insurance_lines = self.insurance_lines.read(linked_property_id=collateral.property_id)
        return collateral

    def read_all(self) -> List[Collateral]:
        """Every collateral on the loan: selects each property in turn and reads it."""
        count = self.root.locator(f"{self.PROPERTY_SELECT} option").count()
        if count <= 1:
            return [self.read()]
        out = []
        for i in range(count):
            self.select(i)
            out.append(self.read())
        self.select(0)
        return out

    # -- actions -------------------------------------------------------------
    def select(self, which: Union[int, str]) -> None:
        """Show a collateral by index or by its property name as listed in the select."""
        select = self.root.locator(self.PROPERTY_SELECT)
        if isinstance(which, int):
            select.select_option(index=which)
        else:
            select.select_option(label=which)

    def save(self, values: Optional[dict] = None) -> None:
        """Optionally write `values` (schema or page field names), then Save Collateral."""
        if values:
            self.set_fields(values)
        self.click("btn-save-collateral")

    def add_new_line(self, line_type: str) -> None:
        self.set_field("line_type", line_type)
        self.click("btn-add-new-line-to-property")
