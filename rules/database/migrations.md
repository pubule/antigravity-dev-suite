---
description: Enterprise Database Migration Safety & Zero-Downtime Schema Evolution Directives
globs: ["**/*.sql", "**/migrations/**", "**/*.prisma", "**/alembic/**"]
---

# 🗄️ Enterprise Database Migration Safety Directives

## 1. Expand / Contract Pattern
- Separate schema modifications into distinct forward-compatible phases:
  1. **Phase 1 (Expand)**: Add new columns or tables additively (nullable or with default values).
  2. **Phase 2 (Dual-Write)**: Deploy application code writing both old and new columns, reading from old.
  3. **Phase 3 (Backfill)**: Run asynchronous background migration to populate existing rows.
  4. **Phase 4 (Dual-Read)**: Switch application reads to the new column.
  5. **Phase 5 (Contract)**: Drop old columns in a subsequent release after verifying stability.

## 2. PostgreSQL & Relational Lock Avoidance
- **Concurrent Index Creation**: Always use `CREATE INDEX CONCURRENTLY` in PostgreSQL to avoid blocking table writes.
- **Safe Column Additions**: Never add `NOT NULL` columns to existing populated tables without a default value (`NOT NULL DEFAULT ...` or add nullable, backfill, then set NOT NULL).
- **Safe Column Deletion**: Never drop an active column in a single deployment. Always deprecate first.
- **Safe Type Alterations**: Never execute `ALTER TABLE ... ALTER COLUMN ... TYPE` directly on large tables without expand/contract migration.

## 3. Backward-Compatible Rollbacks
- Guarantee that every migration script has an idempotent rollback procedure.
- Ensure that the previous version of application code continues operating without error if a rollback occurs.
