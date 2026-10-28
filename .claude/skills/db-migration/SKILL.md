---
name: db-migration
description: Create, review, and test an Alembic migration for this project's PostgreSQL schema. Use whenever a SQLAlchemy model, enum, index, or constraint changes.
---

# DB migration workflow

1. Change the SQLAlchemy models first. Keep them consistent with the schema in `docs/DESIGN.md` §3. If the design itself changes, update DESIGN.md in the same change.
2. Generate: `uv run alembic revision --autogenerate -m "<verb_object>"` (e.g. `add_share_link_note`).
3. Review the generated file by hand. Autogenerate misses or mangles these:
   - **Enum changes**: adding a value needs `op.execute("ALTER TYPE <name> ADD VALUE '<v>'")`. Removing or renaming values needs a manual type swap.
   - **Generated columns** (`documents.ref_year_be` / `ref_series` / `ref_seq`) must use `Computed(..., persisted=True)` in models *and* migration. Without it, PostgreSQL 18+ makes them VIRTUAL, which can't be indexed.
   - Partial indexes (`WHERE deleted_at IS NULL`) and `gin_trgm_ops` indexes: declare them in the model (`postgresql_where`, `postgresql_using`/`postgresql_ops`) so autogenerate and `alembic check` see them.
   - **Shared enum types** (used by two tables): create them once at the top of `upgrade()`, reference them with `postgresql.ENUM(name=..., create_type=False)`, and drop them at the end of `downgrade()`. See the baseline migration.
   - **Extensions** (`pgcrypto`, `pg_trgm`, `citext`): only in the baseline migration.
   - **Circular FK** `documents.current_version_id`: must stay `DEFERRABLE INITIALLY DEFERRED`.
   - Server defaults (`gen_random_uuid()`, `now()`) must be `server_default=sa.text(...)`.
4. Make `downgrade()` real, not `pass`, unless dropping data is unavoidable. If it is, say so in the docstring.
5. Test on the server: `docker compose exec -T api pytest -q tests/test_migrations.py`. It builds a throwaway ICU th-TH database, runs upgrade → downgrade base → upgrade, then `alembic check` (models vs schema). Autogenerate also runs there, against a scratch DB:
   `docker compose exec -T api sh -c 'DATABASE_URL=${DATABASE_URL%/*}/<scratch_db> alembic revision --autogenerate -m <name>'`, then `cat` the file back to this machine.
6. Never edit a migration that has already been applied anywhere shared (demo server). Add a new one instead.
7. Never put data that depends on secrets (KEK, passwords) in a migration. Seed admin users with the bootstrap CLI.
