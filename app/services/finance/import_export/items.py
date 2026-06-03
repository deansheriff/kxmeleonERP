"""
Items/Inventory Importer.

Imports inventory items from CSV data into the IFRS-based inventory system.
"""

import logging
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models.finance.core_config.numbering_sequence import SequenceType
from app.models.inventory.item import CostingMethod, Item, ItemType
from app.models.inventory.item_category import ItemCategory
from app.services.finance.platform.sequence import SequenceService

from .base import BaseImporter, FieldMapping, ImportConfig

logger = logging.getLogger(__name__)


class ItemCategoryImporter(BaseImporter[ItemCategory]):
    """
    Importer for item categories.

    Creates categories from unique item groups/categories in the source data.
    """

    entity_name = "Item Category"
    model_class = ItemCategory

    def __init__(
        self,
        db: Session,
        config: ImportConfig,
        inventory_account_id: UUID,
        cogs_account_id: UUID,
        revenue_account_id: UUID,
        adjustment_account_id: UUID,
    ):
        super().__init__(db, config)
        self.inventory_account_id = inventory_account_id
        self.cogs_account_id = cogs_account_id
        self.revenue_account_id = revenue_account_id
        self.adjustment_account_id = adjustment_account_id
        self._category_cache: dict[str, UUID] = {}

    def get_field_mappings(self) -> list[FieldMapping]:
        return []

    def get_unique_key(self, row: dict[str, Any]) -> str:
        value = (
            row.get("Category Name")
            or row.get("category_name")
            or row.get("Item Group")
            or row.get("Category")
            or "Default"
        )
        return str(value).strip()

    def check_duplicate(self, row: dict[str, Any]) -> ItemCategory | None:
        category_name = self.get_unique_key(row)
        category_code = self._make_category_code(category_name)

        if category_code in self._category_cache:
            return self.db.get(ItemCategory, self._category_cache[category_code])

        existing = self.db.execute(
            select(ItemCategory).where(
                ItemCategory.organization_id == self.config.organization_id,
                ItemCategory.category_code == category_code,
            )
        ).scalar_one_or_none()

        if existing:
            self._category_cache[category_code] = existing.category_id

        return existing

    def create_entity(self, row: dict[str, Any]) -> ItemCategory:
        category_name = self.get_unique_key(row)
        category_code = self._make_category_code(category_name)

        category = ItemCategory(
            category_id=uuid4(),
            organization_id=self.config.organization_id,
            category_code=category_code,
            category_name=category_name[:100],
            description=f"Imported category: {category_name}",
            inventory_account_id=self.inventory_account_id,
            cogs_account_id=self.cogs_account_id,
            revenue_account_id=self.revenue_account_id,
            inventory_adjustment_account_id=self.adjustment_account_id,
            is_active=True,
        )

        self._category_cache[category_code] = category.category_id
        return category

    def _make_category_code(self, name: str) -> str:
        return name.upper().replace(" ", "_")[:30]

    def get_category_id(self, category_name: str) -> UUID | None:
        code = self._make_category_code(category_name)
        return self._category_cache.get(code)

    def ensure_categories(self, rows: list[dict[str, Any]]) -> None:
        """Ensure all required categories exist."""
        unique_categories = set()
        for row in rows:
            cat_name = (
                row.get("Category Name")
                or row.get("category_name")
                or row.get("Item Group")
                or row.get("Category")
                or "Default"
            )
            if cat_name:
                unique_categories.add(cat_name.strip())

        for cat_name in unique_categories:
            row = {"Category Name": cat_name}
            if not self.check_duplicate(row):
                category = self.create_entity(row)
                self.db.add(category)
                self.db.flush()


class ItemImporter(BaseImporter[Item]):
    """
    Importer for inventory items from CSV data.

    Expected CSV columns (flexible - maps common naming conventions):
    - Item Name / Name / Product Name: Item name (required)
    - Item Code / SKU / Product Code: Item code (required)
    - Description / Item Description: Description
    - Item Type / Type: INVENTORY, SERVICE, NON_INVENTORY, KIT
    - Category Name / Item Group / Category: Category for the item
    - Unit / UOM / Base Unit: Base unit of measure
    - Purchase Price / Cost / Unit Cost: Purchase/cost price
    - Selling Price / Sales Price / List Price: Selling price
    - Currency Code / Currency: Currency code (defaults to configured organization currency)
    - Reorder Point / Reorder Level: Reorder point
    - Track Inventory: Whether to track inventory (true/false)
    - Is Taxable / Taxable: Whether taxable
    - Status / Is Active: Active status
    """

    entity_name = "Item"
    model_class = Item

    def __init__(
        self,
        db: Session,
        config: ImportConfig,
        inventory_account_id: UUID,
        cogs_account_id: UUID,
        revenue_account_id: UUID,
        adjustment_account_id: UUID,
    ):
        super().__init__(db, config)
        self._code_counter = 0
        self._category_importer = ItemCategoryImporter(
            db,
            config,
            inventory_account_id,
            cogs_account_id,
            revenue_account_id,
            adjustment_account_id,
        )

    def get_field_mappings(self) -> list[FieldMapping]:
        """Define flexible field mappings supporting various CSV formats."""
        return [
            # Name mappings - try multiple common column names
            FieldMapping("Item Name", "item_name", required=False),
            FieldMapping("item_name", "item_name", required=False),
            FieldMapping("Name", "item_name_alt", required=False),
            FieldMapping("Product Name", "item_name_alt2", required=False),
            # Code mappings
            FieldMapping("Item Code", "item_code", required=False),
            FieldMapping("item_code", "item_code", required=False),
            FieldMapping("SKU", "sku", required=False),
            FieldMapping("sku", "sku", required=False),
            FieldMapping("Product Code", "product_code", required=False),
            # Description
            FieldMapping("Description", "description", required=False),
            FieldMapping("description", "description", required=False),
            FieldMapping("Item Description", "description_alt", required=False),
            # Type
            FieldMapping("Item Type", "item_type_str", required=False),
            FieldMapping("item_type_str", "item_type_str", required=False),
            FieldMapping("Type", "type_alt", required=False),
            FieldMapping("Costing Method", "costing_method_str", required=False),
            FieldMapping("costing_method_str", "costing_method_str", required=False),
            FieldMapping("Cost Method", "costing_method_str", required=False),
            # Category
            FieldMapping("Category Name", "category_name", required=False),
            FieldMapping("category_name", "category_name", required=False),
            FieldMapping("Item Group", "item_group", required=False),
            FieldMapping("Category", "category_alt", required=False),
            # UOM
            FieldMapping("Base UOM", "base_uom", required=False, default="EACH"),
            FieldMapping("base_uom", "base_uom", required=False, default="EACH"),
            FieldMapping("Unit", "base_uom", required=False, default="EACH"),
            FieldMapping("UOM", "uom_alt", required=False),
            FieldMapping("Base Unit", "base_unit_alt", required=False),
            FieldMapping("Purchase UOM", "purchase_uom", required=False),
            FieldMapping("purchase_uom", "purchase_uom", required=False),
            FieldMapping("Purchase Unit", "purchase_uom", required=False),
            FieldMapping("Sales UOM", "sales_uom", required=False),
            FieldMapping("sales_uom", "sales_uom", required=False),
            FieldMapping("Sales Unit", "sales_uom", required=False),
            # Pricing
            FieldMapping(
                "Standard Cost",
                "standard_cost",
                required=False,
                transformer=self.parse_decimal,
            ),
            FieldMapping(
                "standard_cost",
                "standard_cost",
                required=False,
                transformer=self.parse_decimal,
            ),
            FieldMapping(
                "Purchase Price",
                "purchase_cost",
                required=False,
                transformer=self.parse_decimal,
            ),
            FieldMapping(
                "purchase_cost",
                "purchase_cost",
                required=False,
                transformer=self.parse_decimal,
            ),
            FieldMapping(
                "Cost", "cost_alt", required=False, transformer=self.parse_decimal
            ),
            FieldMapping(
                "Unit Cost",
                "unit_cost_alt",
                required=False,
                transformer=self.parse_decimal,
            ),
            FieldMapping(
                "Selling Price",
                "list_price",
                required=False,
                transformer=self.parse_decimal,
            ),
            FieldMapping(
                "list_price",
                "list_price",
                required=False,
                transformer=self.parse_decimal,
            ),
            FieldMapping(
                "Sales Price",
                "sales_price_alt",
                required=False,
                transformer=self.parse_decimal,
            ),
            FieldMapping(
                "List Price",
                "list_price_alt",
                required=False,
                transformer=self.parse_decimal,
            ),
            # Currency
            FieldMapping(
                "Currency Code",
                "currency_code",
                required=False,
                default=settings.default_functional_currency_code,
            ),
            FieldMapping(
                "currency_code",
                "currency_code",
                required=False,
                default=settings.default_functional_currency_code,
            ),
            FieldMapping("Currency", "currency_alt", required=False),
            # Stock management
            FieldMapping(
                "Lead Time Days",
                "lead_time_days",
                required=False,
                transformer=lambda v: int(float(v)) if v else None,
            ),
            FieldMapping(
                "lead_time_days",
                "lead_time_days",
                required=False,
                transformer=lambda v: int(float(v)) if v else None,
            ),
            FieldMapping(
                "Reorder Point",
                "reorder_point",
                required=False,
                transformer=self.parse_decimal,
            ),
            FieldMapping(
                "reorder_point",
                "reorder_point",
                required=False,
                transformer=self.parse_decimal,
            ),
            FieldMapping(
                "Reorder Level",
                "reorder_level_alt",
                required=False,
                transformer=self.parse_decimal,
            ),
            FieldMapping(
                "Reorder Quantity",
                "reorder_quantity",
                required=False,
                transformer=self.parse_decimal,
            ),
            FieldMapping(
                "reorder_quantity",
                "reorder_quantity",
                required=False,
                transformer=self.parse_decimal,
            ),
            FieldMapping(
                "Minimum Stock",
                "minimum_stock",
                required=False,
                transformer=self.parse_decimal,
            ),
            FieldMapping(
                "minimum_stock",
                "minimum_stock",
                required=False,
                transformer=self.parse_decimal,
            ),
            FieldMapping(
                "Maximum Stock",
                "maximum_stock",
                required=False,
                transformer=self.parse_decimal,
            ),
            FieldMapping(
                "maximum_stock",
                "maximum_stock",
                required=False,
                transformer=self.parse_decimal,
            ),
            # Flags
            FieldMapping(
                "Track Inventory",
                "track_inventory",
                required=False,
                transformer=self.parse_boolean,
                default=True,
            ),
            FieldMapping(
                "track_inventory",
                "track_inventory",
                required=False,
                transformer=self.parse_boolean,
                default=True,
            ),
            FieldMapping(
                "Track Lots",
                "track_lots",
                required=False,
                transformer=self.parse_boolean,
                default=False,
            ),
            FieldMapping(
                "track_lots",
                "track_lots",
                required=False,
                transformer=self.parse_boolean,
                default=False,
            ),
            FieldMapping(
                "Track Serial Numbers",
                "track_serial_numbers",
                required=False,
                transformer=self.parse_boolean,
                default=False,
            ),
            FieldMapping(
                "track_serial_numbers",
                "track_serial_numbers",
                required=False,
                transformer=self.parse_boolean,
                default=False,
            ),
            FieldMapping(
                "Is Taxable",
                "is_taxable",
                required=False,
                transformer=self.parse_boolean,
                default=True,
            ),
            FieldMapping(
                "Taxable", "taxable_alt", required=False, transformer=self.parse_boolean
            ),
            FieldMapping("Status", "status_str", required=False),
            FieldMapping(
                "Is Active",
                "is_active",
                required=False,
                transformer=self.parse_boolean,
                default=True,
            ),
            FieldMapping(
                "Is Purchaseable",
                "is_purchaseable",
                required=False,
                transformer=self.parse_boolean,
                default=True,
            ),
            FieldMapping(
                "is_purchaseable",
                "is_purchaseable",
                required=False,
                transformer=self.parse_boolean,
                default=True,
            ),
            FieldMapping(
                "Is Saleable",
                "is_saleable",
                required=False,
                transformer=self.parse_boolean,
                default=True,
            ),
            FieldMapping(
                "is_saleable",
                "is_saleable",
                required=False,
                transformer=self.parse_boolean,
                default=True,
            ),
            # Additional
            FieldMapping("Barcode", "barcode", required=False),
            FieldMapping("barcode", "barcode", required=False),
            FieldMapping(
                "Manufacturer Part Number", "manufacturer_part_number", required=False
            ),
            FieldMapping(
                "manufacturer_part_number",
                "manufacturer_part_number",
                required=False,
            ),
            FieldMapping("MPN", "mpn_alt", required=False),
            FieldMapping(
                "Weight", "weight", required=False, transformer=self.parse_decimal
            ),
            FieldMapping(
                "weight", "weight", required=False, transformer=self.parse_decimal
            ),
            FieldMapping("Weight Unit", "weight_uom", required=False),
            FieldMapping("weight_uom", "weight_uom", required=False),
        ]

    def validate_row(self, row: dict[str, Any], row_num: int) -> bool:
        """Validate Inventory item rows against item master requirements."""
        is_valid = super().validate_row(row, row_num)
        item_name = str(
            row.get("Item Name")
            or row.get("item_name")
            or row.get("Name")
            or row.get("Product Name")
            or ""
        ).strip()
        if not item_name:
            self.result.add_error(
                row_num,
                "Item name is required",
                "Item Name",
            )
            is_valid = False
        return is_valid

    def get_unique_key(self, row: dict[str, Any]) -> str:
        """Unique key is item code or SKU."""
        code = str(
            row.get("Item Code")
            or row.get("item_code")
            or row.get("SKU")
            or row.get("sku")
            or row.get("Product Code")
            or ""
        ).strip()
        if code:
            return code
        # Fallback to name
        name = str(
            row.get("Item Name")
            or row.get("item_name")
            or row.get("Name")
            or row.get("Product Name")
            or ""
        ).strip()
        return name

    def check_duplicate(self, row: dict[str, Any]) -> Item | None:
        """Check if item already exists."""
        key = self.get_unique_key(row)
        if not key:
            return None

        # Check by code
        existing = self.db.execute(
            select(Item).where(
                Item.organization_id == self.config.organization_id,
                Item.item_code == key,
            )
        ).scalar_one_or_none()

        if existing:
            return existing

        # Check by name
        name = str(
            row.get("Item Name")
            or row.get("item_name")
            or row.get("Name")
            or row.get("Product Name")
            or ""
        ).strip()
        if name:
            existing = self.db.execute(
                select(Item).where(
                    Item.organization_id == self.config.organization_id,
                    Item.item_name == name,
                )
            ).scalar_one_or_none()

        return existing

    def create_entity(self, row: dict[str, Any]) -> Item:
        """Create a new item from transformed row data."""
        # Get item name (try multiple fields)
        item_name = str(
            row.get("item_name")
            or row.get("item_name_alt")
            or row.get("item_name_alt2")
            or "Unknown Item"
        ).strip()

        # Get item code (try multiple fields or generate)
        item_code = str(
            row.get("item_code") or row.get("sku") or row.get("product_code") or ""
        ).strip()
        if not item_code:
            item_code = SequenceService.get_next_number(
                self.db,
                self.config.organization_id,
                SequenceType.ITEM,
            )

        # Get description
        description = row.get("description") or row.get("description_alt")

        # Determine item type
        type_str = str(
            row.get("item_type_str") or row.get("type_alt") or "INVENTORY"
        ).upper()
        item_type = self._parse_item_type(type_str)

        # Get category
        category_name = str(
            row.get("category_name")
            or row.get("item_group")
            or row.get("category_alt")
            or "Default"
        )
        category_id = self._category_importer.get_category_id(category_name)
        if category_id is None:
            category_row = {"Category Name": category_name}
            category = self._category_importer.check_duplicate(category_row)
            if not category:
                category = self._category_importer.create_entity(category_row)
                self.db.add(category)
                self.db.flush()
            category_id = category.category_id

        # Get UOM
        base_uom = str(
            row.get("base_uom")
            or row.get("uom_alt")
            or row.get("base_unit_alt")
            or "EACH"
        )[:20]
        purchase_uom = str(row.get("purchase_uom") or base_uom)[:20]
        sales_uom = str(row.get("sales_uom") or base_uom)[:20]

        # Get pricing
        purchase_cost = (
            row.get("purchase_cost") or row.get("cost_alt") or row.get("unit_cost_alt")
        )
        standard_cost = row.get("standard_cost")
        list_price = (
            row.get("list_price")
            or row.get("sales_price_alt")
            or row.get("list_price_alt")
        )

        # Get currency
        currency_code = str(
            row.get("currency_code")
            or row.get("currency_alt")
            or settings.default_functional_currency_code
        )[:3]

        # Get stock management
        reorder_point = row.get("reorder_point") or row.get("reorder_level_alt")

        # Get flags
        track_inventory = row.get("track_inventory", True)
        if item_type in (ItemType.SERVICE, ItemType.NON_INVENTORY):
            track_inventory = False
        track_lots = bool(row.get("track_lots") or False)
        track_serial_numbers = bool(row.get("track_serial_numbers") or False)
        is_taxable = row.get("is_taxable") or row.get("taxable_alt")
        if is_taxable is None:
            is_taxable = True

        is_active = row.get("is_active", True)
        status_val = row.get("status_str")
        if status_val:
            is_active = str(status_val).lower() not in ("inactive", "disabled", "false")

        item = Item(
            item_id=uuid4(),
            organization_id=self.config.organization_id,
            item_code=item_code[:50],
            item_name=item_name[:200],
            description=description,
            item_type=item_type,
            category_id=category_id,
            base_uom=base_uom,
            purchase_uom=purchase_uom,
            sales_uom=sales_uom,
            costing_method=self._parse_costing_method(row.get("costing_method_str")),
            standard_cost=standard_cost,
            last_purchase_cost=purchase_cost,
            currency_code=currency_code,
            list_price=list_price,
            track_inventory=track_inventory
            if item_type == ItemType.INVENTORY
            else False,
            track_lots=track_lots if item_type == ItemType.INVENTORY else False,
            track_serial_numbers=track_serial_numbers
            if item_type == ItemType.INVENTORY
            else False,
            reorder_point=reorder_point,
            reorder_quantity=row.get("reorder_quantity"),
            minimum_stock=row.get("minimum_stock"),
            maximum_stock=row.get("maximum_stock"),
            lead_time_days=row.get("lead_time_days"),
            barcode=row.get("barcode"),
            manufacturer_part_number=row.get("manufacturer_part_number")
            or row.get("mpn_alt"),
            weight=row.get("weight"),
            weight_uom=row.get("weight_uom"),
            is_taxable=is_taxable,
            is_active=is_active,
            is_purchaseable=row.get("is_purchaseable", True),
            is_saleable=row.get("is_saleable", True),
        )

        return item

    def _parse_item_type(self, type_str: str) -> ItemType:
        """Parse item type string to enum."""
        type_map = {
            "INVENTORY": ItemType.INVENTORY,
            "GOODS": ItemType.INVENTORY,
            "PRODUCT": ItemType.INVENTORY,
            "SERVICE": ItemType.SERVICE,
            "SERVICES": ItemType.SERVICE,
            "NON_INVENTORY": ItemType.NON_INVENTORY,
            "NON-INVENTORY": ItemType.NON_INVENTORY,
            "NONINVENTORY": ItemType.NON_INVENTORY,
            "KIT": ItemType.KIT,
            "BUNDLE": ItemType.KIT,
        }
        return type_map.get(type_str.upper().replace(" ", "_"), ItemType.INVENTORY)

    def _parse_costing_method(self, value: Any) -> CostingMethod:
        """Parse costing method text into the local enum."""
        method = str(value or "WEIGHTED_AVERAGE").strip().upper().replace(" ", "_")
        method = method.replace("-", "_")
        method_map = {
            "FIFO": CostingMethod.FIFO,
            "WEIGHTED_AVERAGE": CostingMethod.WEIGHTED_AVERAGE,
            "WAC": CostingMethod.WEIGHTED_AVERAGE,
            "AVERAGE": CostingMethod.WEIGHTED_AVERAGE,
            "SPECIFIC_IDENTIFICATION": CostingMethod.SPECIFIC_IDENTIFICATION,
            "SPECIFIC_ID": CostingMethod.SPECIFIC_IDENTIFICATION,
            "STANDARD_COST": CostingMethod.STANDARD_COST,
            "STANDARD": CostingMethod.STANDARD_COST,
        }
        return method_map.get(method, CostingMethod.WEIGHTED_AVERAGE)

    def import_file(self, file_path):
        """Override to ensure categories are created first."""
        import csv
        from pathlib import Path

        file_path = Path(file_path)
        if not file_path.exists():
            self.result.add_error(0, f"File not found: {file_path}", None)
            return self.result

        with open(file_path, encoding=self.config.encoding) as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        # Ensure categories exist
        self._category_importer.ensure_categories(rows)
        self.db.flush()

        return super().import_rows(rows)

    def import_rows(self, rows: list[dict[str, Any]]):
        """Import in-memory rows after ensuring referenced categories exist."""
        self._category_importer.ensure_categories(rows)
        self.db.flush()
        return super().import_rows(rows)

    def import_xlsx_file(self, file_path):
        """Override XLSX import to ensure categories are created first."""
        from pathlib import Path

        file_path = Path(file_path)
        if not file_path.exists():
            self.result.add_error(0, f"File not found: {file_path}", None)
            return self.result

        rows = self.parse_xlsx_file(file_path)
        self._category_importer.ensure_categories(rows)
        self.db.flush()
        return super().import_rows(rows)

    def import_xls_file(self, file_path):
        """Override XLS import to ensure categories are created first."""
        from pathlib import Path

        file_path = Path(file_path)
        if not file_path.exists():
            self.result.add_error(0, f"File not found: {file_path}", None)
            return self.result

        rows = self.parse_xls_file(file_path)
        self._category_importer.ensure_categories(rows)
        self.db.flush()
        return super().import_rows(rows)
