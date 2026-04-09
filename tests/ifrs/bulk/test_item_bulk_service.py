"""
Tests for app/services/inventory/bulk.py.
"""

import uuid
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest


class MockItemType:
    """Simple enum-like item type stub for export tests."""

    def __init__(self, value: str):
        self.value = value


class MockItem:
    """Mock inventory item entity for testing."""

    def __init__(
        self,
        item_id: uuid.UUID | None = None,
        organization_id: uuid.UUID | None = None,
        item_code: str = "ITEM-001",
        item_name: str = "Test Item",
        item_type: str = "INVENTORY",
        category_id: uuid.UUID | None = None,
    ):
        self.item_id = item_id or uuid.uuid4()
        self.organization_id = organization_id or uuid.UUID(
            "00000000-0000-0000-0000-000000000001"
        )
        self.item_code = item_code
        self.item_name = item_name
        self.description = "Test description"
        self.item_type = MockItemType(item_type)
        self.category_id = category_id or uuid.uuid4()
        self.unit_of_measure = "EACH"
        self.standard_cost = Decimal("10.00")
        self.sales_price = Decimal("20.00")
        self.purchase_price = Decimal("9.00")
        self.is_active = True
        self.is_stockable = True
        self.is_sellable = True
        self.is_purchasable = True


@pytest.fixture
def mock_item(organization_id):
    """Create a mock inventory item entity."""
    return MockItem(organization_id=organization_id)


class TestBulkExport:
    """Tests for inventory item CSV export."""

    @pytest.mark.asyncio
    async def test_export_csv_headers_include_stock_columns(
        self, mock_db, mock_item, organization_id
    ):
        """CSV export should include On Hand and Available headers."""
        mock_db.scalars.return_value.all.return_value = [mock_item]

        with (
            patch("app.services.inventory.bulk.Item", MagicMock()),
            patch(
                "app.services.inventory.bulk._get_batch_stock_quantities",
                return_value={
                    mock_item.item_id: {
                        "on_hand": Decimal("15.50"),
                        "available": Decimal("12.25"),
                    }
                },
            ),
        ):
            from app.services.inventory.bulk import ItemBulkService

            service = ItemBulkService(mock_db, organization_id)
            response = await service.bulk_export([mock_item.item_id])

            content = (
                response.body.decode()
                if isinstance(response.body, bytes)
                else response.body
            )

            headers = content.split("\n")[0]
            assert "On Hand" in headers
            assert "Available" in headers

    @pytest.mark.asyncio
    async def test_export_csv_data_includes_stock_values(
        self, mock_db, mock_item, organization_id
    ):
        """CSV export should include computed stock quantities."""
        mock_db.scalars.return_value.all.return_value = [mock_item]

        with (
            patch("app.services.inventory.bulk.Item", MagicMock()),
            patch(
                "app.services.inventory.bulk._get_batch_stock_quantities",
                return_value={
                    mock_item.item_id: {
                        "on_hand": Decimal("15.50"),
                        "available": Decimal("12.25"),
                    }
                },
            ),
        ):
            from app.services.inventory.bulk import ItemBulkService

            service = ItemBulkService(mock_db, organization_id)
            response = await service.bulk_export([mock_item.item_id])

            content = (
                response.body.decode()
                if isinstance(response.body, bytes)
                else response.body
            )

            assert "15.50" in content
            assert "12.25" in content
