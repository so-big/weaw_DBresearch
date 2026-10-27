# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Department web app for encrypted storage of contracts and research-grant documents (mostly scanned Thai/English PDFs).
The agreed design, schema, and open questions live in @docs/DESIGN.md. Read it before changing the data model, and update it when a decision changes.

## Workflow
- Track tasks and open decisions in `plan.md`. Update its checkboxes and log as work lands.
- This machine has no Docker and is too weak for the stack: run only ruff and quick unit tests here. Push to `origin main`, then deploy and test on the server: `ssh cs31@100.104.87.92 'cd ~/dbresearch && git pull && docker compose up -d --build'`.
- The server is shared with other projects. Bind DBresearch ports to `127.0.0.1` only, and never touch other projects' containers.

## Stack
- Python 3 + FastAPI, PostgreSQL, SQLAlchemy 2 + Alembic, MinIO (S3 API), Docker Compose.
- Use `uv` for everything (`uv add`, `uv run pytest`, `uv run alembic ...`). Do not use pip directly.
- Background work (OCR, purge) goes through the PostgreSQL `jobs` table (`FOR UPDATE SKIP LOCKED`). Don't add Redis/Celery.

## Rules that must not break
- **No plaintext file bytes outside memory or the worker's tmpfs.** MinIO holds ciphertext only. Every file version has its own DEK, wrapped by the KEK (Tink Streaming AEAD). Never log file contents or OCR text.
- **GUEST is not a role or a user row.** A guest is anyone holding a valid share link. Roles are only `admin` and `user`.
- Share-link tokens and passwords are stored **only as hashes** and shown once. Download-count limits are enforced with an atomic conditional `UPDATE ... RETURNING`.
- Soft-deleting a document revokes its share links in the same transaction. Only ADMIN purges (deletes the object + wrapped DEK).
- Edit/delete/new version is allowed only for `uploaded_by` or ADMIN. Every USER can read every document.
- Every download, share create/revoke, admin action, and purge writes an `audit_events` row.

## Thai data gotchas
- Create the DB with `LOCALE_PROVIDER icu ICU_LOCALE 'th-TH' LOCALE 'C.UTF-8'` (verified). With a plain `C` ctype, pg_trgm silently ignores Thai text.
- Search uses `ILIKE '%q%'` backed by `gin_trgm_ops` indexes. Don't switch to `to_tsvector` with a language config (it can't split Thai words).
- Normalise text before storing and searching: NFC, Thai digits ๐–๙ → 0–9, collapse whitespace.
- Store dates and years in the Gregorian calendar. Convert to พ.ศ. (+543) only at the API/UI edge. `fiscal_year` comes from the document text when stated, otherwise from `document_date` (Oct–Sep).
- One PDF is a bundle of sections (`เอกสารแนบหมายเลข N`). Auto-fill works per section with several label variants per field (DESIGN §6). Don't assume a field appears once or uses one fixed label.
- Auto-tagging uses **checked** boxes only (unchecked ones are ignored). Map them to categories by fuzzy match. Never create categories automatically; unmatched labels become *suggested* tags.

## Sample documents
- Real PDFs are confidential and gitignored (`*.pdf`, `samples/`). Never commit them or paste their contents into tests. Use redacted text fixtures.
- Copy samples to the server with `scp` into `~/dbresearch/samples/` for OCR tests. Don't go through git.
