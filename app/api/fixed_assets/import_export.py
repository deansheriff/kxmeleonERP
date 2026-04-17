"""
Fixed Assets Import API Endpoints.

CSV import endpoints for fixed assets and asset categories.
"""

from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import require_tenant_auth
from app.db import get_db_session
from app.services.auth_dependencies import (
    get_current_org_id,
    get_current_user_id,
    require_tenant_permission,
)
from app.services.fixed_assets.import_export import AssetImporter
from app.services.finance.import_export import (
    ImportConfig,
    ImportResult,
    PreviewResult,
    find_account_by_name_pattern,
    find_account_by_subledger_type,
)
from app.services.finance.import_export.import_service import ImportService
from app.services.upload_utils import get_env_max_bytes, write_upload_to_temp


router = APIRouter(
    prefix="/import",
    tags=["fixed-assets-import"],
    dependencies=[Depends(require_tenant_auth)],
)


class EntityType(str, Enum):
    """Supported entity types for fixed asset import."""

    ASSETS = "assets"


class ImportResultResponse(BaseModel):
    """Response model for import results."""

    entity_type: str
    status: str
    total_rows: int
    imported_count: int
    skipped_count: int
    duplicate_count: int
    error_count: int
    success_rate: str
    duration_seconds: float
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    @classmethod
    def from_import_result(cls, result: ImportResult) -> ImportResultResponse:
        return cls(
            entity_type=result.entity_type,
            status=result.status.value,
            total_rows=result.total_rows,
            imported_count=result.imported_count,
            skipped_count=result.skipped_count,
            duplicate_count=result.duplicate_count,
            error_count=result.error_count,
            success_rate=f"{result.success_rate:.1f}%",
            duration_seconds=round(result.duration_seconds, 2),
            errors=[str(e) for e in result.errors[:50]],
            warnings=[str(w) for w in result.warnings[:50]],
        )


class ColumnMappingResponse(BaseModel):
    """Column mapping with confidence score."""

    source: str
    target: str
    confidence: float
    samples: list[str] = Field(default_factory=list)


class ImportPreviewResponse(BaseModel):
    """Enhanced response for import preview."""

    entity_type: str
    total_rows: int
    sample_data: list[dict[str, Any]]
    detected_columns: list[str]
    required_columns: list[str]
    optional_columns: list[str]
    missing_required: list[str]
    column_mappings: list[ColumnMappingResponse]
    validation_errors: list[str]
    detected_format: str
    is_valid: bool

    @classmethod
    def from_preview_result(cls, result: PreviewResult) -> ImportPreviewResponse:
        return cls(
            entity_type=result.entity_type,
            total_rows=result.total_rows,
            sample_data=result.sample_data,
            detected_columns=result.detected_columns,
            required_columns=result.required_columns,
            optional_columns=result.optional_columns,
            missing_required=result.missing_required,
            column_mappings=[
                ColumnMappingResponse(
                    source=m.source_column,
                    target=m.target_field,
                    confidence=m.confidence,
                    samples=m.sample_values[:3],
                )
                for m in result.column_mappings
            ],
            validation_errors=result.validation_errors,
            detected_format=result.detected_format,
            is_valid=result.is_valid,
        )


@router.get("/supported-types")
async def get_supported_types(
    auth: dict = Depends(require_tenant_permission("fa:assets:import:read")),
) -> dict[str, Any]:
    """Get list of supported fixed asset entity types."""
    return {
        "entity_types": [
            {
                "type": "assets",
                "name": "Fixed Assets",
                "description": "Import fixed assets and depreciation schedules",
                "required_columns": ["Asset Name"],
                "optional_columns": [
                    "Asset Number",
                    "Acquisition Date",
                    "Cost",
                    "Category",
                ],
                "import_order": 1,
            },
        ],
        "recommended_order": ["assets"],
    }


@router.post("/preview/{entity_type}")
async def preview_import(
    entity_type: EntityType,
    file: UploadFile = File(...),
    db: Session = Depends(get_db_session),
    org_id: UUID = Depends(get_current_org_id),
    user_id: UUID = Depends(get_current_user_id),
    auth: dict = Depends(require_tenant_permission("fa:assets:import:preview")),
) -> ImportPreviewResponse:
    """Preview fixed asset imports with auto-mapping."""
    if not file.filename or not file.filename.endswith(".csv"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only CSV files are supported",
        )

    max_bytes = get_env_max_bytes("MAX_IMPORT_FILE_SIZE", 50 * 1024 * 1024)
    tmp_path = await write_upload_to_temp(
        file,
        suffix=".csv",
        max_bytes=max_bytes,
        error_detail=f"File too large. Maximum size: {max_bytes // 1024 // 1024}MB",
    )

    try:
        config = ImportConfig(
            organization_id=org_id,
            user_id=user_id,
            skip_duplicates=True,
            dry_run=True,
        )
        importer = _get_importer(entity_type, db, config)
        preview_result = importer.preview_file(tmp_path, max_rows=10)
        return ImportPreviewResponse.from_preview_result(preview_result)

    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Preview failed: {str(exc)}",
        )
    finally:
        Path(tmp_path).unlink(missing_ok=True)


@router.post("/{entity_type}")
async def import_data(
    entity_type: EntityType,
    file: UploadFile = File(...),
    skip_duplicates: bool = Form(default=True),
    dry_run: bool = Form(default=False),
    batch_size: int = Form(default=100),
    db: Session = Depends(get_db_session),
    org_id: UUID = Depends(get_current_org_id),
    user_id: UUID = Depends(get_current_user_id),
    auth: dict = Depends(require_tenant_permission("fa:assets:import:execute")),
) -> ImportResultResponse:
    """Import fixed asset data from a CSV file."""
    if not file.filename or not file.filename.endswith(".csv"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only CSV files are supported",
        )

    max_bytes = get_env_max_bytes("MAX_IMPORT_FILE_SIZE", 50 * 1024 * 1024)
    tmp_path = await write_upload_to_temp(
        file,
        suffix=".csv",
        max_bytes=max_bytes,
        error_detail=f"File too large. Maximum size: {max_bytes // 1024 // 1024}MB",
    )

    try:
        config = ImportConfig(
            organization_id=org_id,
            user_id=user_id,
            skip_duplicates=skip_duplicates,
            dry_run=dry_run,
            batch_size=batch_size,
        )
        importer = _get_importer(entity_type, db, config)
        result = ImportService.run_import(importer, tmp_path)
        return ImportResultResponse.from_import_result(result)

    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Import failed: {str(exc)}",
        )
    finally:
        Path(tmp_path).unlink(missing_ok=True)


def _get_importer(entity_type: EntityType, db: Session, config: ImportConfig):
    """Get the appropriate importer for fixed asset imports."""
    org_id = config.organization_id

    if entity_type == EntityType.ASSETS:
        asset_account = find_account_by_subledger_type(db, org_id, "ASSET")
        if not asset_account:
            asset_account = find_account_by_name_pattern(db, org_id, "fixed asset")
        if not asset_account:
            raise ValueError("No fixed asset account found. Import accounts first.")
        return AssetImporter(
            db, config, asset_account, asset_account, asset_account, asset_account
        )

    raise ValueError(f"Unsupported entity type: {entity_type}")
