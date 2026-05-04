from __future__ import annotations

from datetime import date
from io import BytesIO
from decimal import Decimal
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from starlette.datastructures import FormData
from starlette.datastructures import UploadFile

from app.services.operations.inv_web import OperationsInventoryWebService


def test_extract_uploads_returns_multiple_images() -> None:
    first = UploadFile(
        filename="one.png",
        file=BytesIO(b"one"),
        headers={"content-type": "image/png"},
    )
    second = UploadFile(
        filename="two.webp",
        file=BytesIO(b"two"),
        headers={"content-type": "image/webp"},
    )

    uploads = OperationsInventoryWebService._extract_uploads(
        FormData([("images", first), ("images", second)]),
        "images",
    )

    assert uploads == [first, second]


def test_validate_return_image_uploads_accepts_supported_images() -> None:
    upload = UploadFile(
        filename="evidence.png",
        file=BytesIO(b"image-bytes"),
        headers={"content-type": "image/png"},
    )

    OperationsInventoryWebService._validate_return_image_uploads([upload])


def test_validate_return_image_uploads_rejects_non_images() -> None:
    upload = UploadFile(
        filename="evidence.pdf",
        file=BytesIO(b"pdf-bytes"),
        headers={"content-type": "application/pdf"},
    )

    with pytest.raises(ValueError, match="Only image files are allowed"):
        OperationsInventoryWebService._validate_return_image_uploads([upload])


@pytest.mark.asyncio
async def test_bulk_record_count_lines_response_uses_checked_lines_only(monkeypatch) -> None:
    service = OperationsInventoryWebService()
    request = MagicMock()
    request.form = AsyncMock(
        return_value=FormData(
            [
                ("selected_line_ids", "11111111-1111-1111-1111-111111111111"),
                ("selected_line_ids", "22222222-2222-2222-2222-222222222222"),
                ("counted_quantity_11111111-1111-1111-1111-111111111111", "12.5"),
                ("counted_quantity_22222222-2222-2222-2222-222222222222", "8"),
                ("counted_quantity_33333333-3333-3333-3333-333333333333", "99"),
            ]
        )
    )
    auth = MagicMock(organization_id=uuid.uuid4(), user_id=uuid.uuid4())
    db = MagicMock()

    captured: dict[str, object] = {}

    def fake_record_count_bulk(
        db, organization_id, count_id, inputs, counted_by_user_id
    ):
        captured["db"] = db
        captured["organization_id"] = organization_id
        captured["count_id"] = count_id
        captured["inputs"] = inputs
        captured["counted_by_user_id"] = counted_by_user_id
        return []

    monkeypatch.setattr(
        "app.services.inventory.count.InventoryCountService.record_count_bulk",
        fake_record_count_bulk,
    )

    response = await service.bulk_record_count_lines_response(
        request=request,
        count_id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        auth=auth,
        db=db,
    )

    assert response.status_code == 303
    assert (
        response.headers["location"]
        == "/inventory/counts/aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
    )
    inputs = captured["inputs"]
    assert len(inputs) == 2
    assert inputs[0].counted_quantity == Decimal("12.5")
    assert inputs[1].counted_quantity == Decimal("8")


def test_export_count_csv_response_returns_csv_for_posted_count() -> None:
    service = OperationsInventoryWebService()
    count_id = uuid.uuid4()
    item_id = uuid.uuid4()
    warehouse_id = uuid.uuid4()
    auth = MagicMock(organization_id=uuid.uuid4())
    db = MagicMock()

    count = MagicMock()
    count.count_id = count_id
    count.organization_id = auth.organization_id
    count.count_number = "CNT-00042"
    count.count_date = date(2026, 5, 4)
    count.status.value = "POSTED"

    line = MagicMock()
    line.item_id = item_id
    line.warehouse_id = warehouse_id
    line.system_quantity = Decimal("10")
    line.counted_quantity = Decimal("8")
    line.final_quantity = Decimal("8")
    line.variance_quantity = Decimal("-2")
    line.variance_value = Decimal("-50")
    line.reason_code = "DAMAGE"
    line.notes = "Broken cartons"

    item = MagicMock()
    item.item_id = item_id
    item.item_code = "ITEM-001"
    item.item_name = "Test Item"

    warehouse = MagicMock()
    warehouse.warehouse_id = warehouse_id
    warehouse.warehouse_name = "Main Warehouse"

    db.get.return_value = count

    class _FakeScalarResult:
        def __init__(self, values):
            self._values = values

        def all(self):
            return self._values

    db.scalars.side_effect = [
        _FakeScalarResult([item]),
        _FakeScalarResult([warehouse]),
    ]

    from app.models.inventory.inventory_count import CountStatus
    from app.services.inventory.count import InventoryCountService

    count.status = CountStatus.POSTED

    list_lines_original = InventoryCountService.list_lines
    InventoryCountService.list_lines = MagicMock(return_value=[line])
    try:
        response = service.export_count_csv_response(str(count_id), auth, db)
    finally:
        InventoryCountService.list_lines = list_lines_original

    assert response.media_type == "text/csv"
    assert (
        response.headers["Content-Disposition"]
        == 'attachment; filename="stock_count_CNT-00042.csv"'
    )
    body = response.body.decode()
    assert "Count Number,Count Date,Status,Item Code,Item Name,Warehouse" in body
    assert (
        "CNT-00042,2026-05-04,POSTED,ITEM-001,Test Item,Main Warehouse,10,8,8,-2,-50,DAMAGE,Broken cartons"
        in body
    )
