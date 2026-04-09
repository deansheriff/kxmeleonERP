"""Add destination warehouse to inventory material requests.

Revision ID: 20260409_add_material_request_transfer_destination
Revises: 20260402_add_org_performance_mode
Create Date: 2026-04-09
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "20260409_add_material_request_transfer_destination"
down_revision = "20260402_add_org_performance_mode"
branch_labels = None
depends_on = None


def _column_has_unique_constraint(
    inspector: sa.Inspector, table_name: str, column_name: str, schema: str
) -> bool:
    for pk in [inspector.get_pk_constraint(table_name, schema=schema)]:
        constrained = pk.get("constrained_columns") or []
        if constrained == [column_name]:
            return True

    for unique in inspector.get_unique_constraints(table_name, schema=schema):
        constrained = unique.get("column_names") or []
        if constrained == [column_name]:
            return True

    for index in inspector.get_indexes(table_name, schema=schema):
        columns = index.get("column_names") or []
        if index.get("unique") and columns == [column_name]:
            return True

    return False


def _ensure_column_unique(
    bind: sa.Connection,
    inspector: sa.Inspector,
    table_name: str,
    column_name: str,
    schema: str,
    constraint_name: str,
) -> None:
    if not inspector.has_table(table_name, schema=schema):
        return

    if _column_has_unique_constraint(inspector, table_name, column_name, schema):
        return

    duplicate_value = bind.execute(
        sa.text(
            f"""
            SELECT {column_name}
            FROM {schema}.{table_name}
            WHERE {column_name} IS NOT NULL
            GROUP BY {column_name}
            HAVING COUNT(*) > 1
            LIMIT 1
            """
        )
    ).scalar()
    if duplicate_value is not None:
        raise RuntimeError(
            f"Cannot add unique constraint to {schema}.{table_name}.{column_name} because duplicate values exist."
        )

    op.create_unique_constraint(
        constraint_name,
        table_name,
        [column_name],
        schema=schema,
    )


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not inspector.has_table("material_request", schema="inv"):
        return

    _ensure_column_unique(
        bind,
        inspector,
        "warehouse",
        "warehouse_id",
        "inv",
        "uq_warehouse_warehouse_id",
    )

    columns = {
        column["name"]
        for column in inspector.get_columns("material_request", schema="inv")
    }
    if "transfer_to_warehouse_id" not in columns:
        op.add_column(
            "material_request",
            sa.Column(
                "transfer_to_warehouse_id",
                postgresql.UUID(as_uuid=True),
                nullable=True,
                comment="Destination warehouse for transfer requests",
            ),
            schema="inv",
        )

    fks = {
        fk["name"]
        for fk in inspector.get_foreign_keys("material_request", schema="inv")
    }
    if "fk_material_request_transfer_to_warehouse" not in fks:
        op.create_foreign_key(
            "fk_material_request_transfer_to_warehouse",
            "material_request",
            "warehouse",
            ["transfer_to_warehouse_id"],
            ["warehouse_id"],
            source_schema="inv",
            referent_schema="inv",
        )

    indexes = {
        idx["name"] for idx in inspector.get_indexes("material_request", schema="inv")
    }
    if "idx_material_request_transfer_to_wh" not in indexes:
        op.create_index(
            "idx_material_request_transfer_to_wh",
            "material_request",
            ["transfer_to_warehouse_id"],
            unique=False,
            schema="inv",
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not inspector.has_table("material_request", schema="inv"):
        return

    indexes = {
        idx["name"] for idx in inspector.get_indexes("material_request", schema="inv")
    }
    if "idx_material_request_transfer_to_wh" in indexes:
        op.drop_index(
            "idx_material_request_transfer_to_wh",
            table_name="material_request",
            schema="inv",
        )

    fks = {
        fk["name"]
        for fk in inspector.get_foreign_keys("material_request", schema="inv")
    }
    if "fk_material_request_transfer_to_warehouse" in fks:
        op.drop_constraint(
            "fk_material_request_transfer_to_warehouse",
            "material_request",
            schema="inv",
            type_="foreignkey",
        )

    columns = {
        column["name"]
        for column in inspector.get_columns("material_request", schema="inv")
    }
    if "transfer_to_warehouse_id" in columns:
        op.drop_column("material_request", "transfer_to_warehouse_id", schema="inv")
