# DBresearch — System Design

Department web app for storing **contracts** and **research grant** documents (mostly scanned PDFs),
encrypted at rest, with OCR auto-fill, search, and expiring share links.

Status: design agreed 2026-10-27 (grill session). Frontend layout and sample documents are still pending.

---

## 1. Decisions

| Area | Decision |
|---|---|
| Deliverable | DB design + working backend (API). Frontend later. |
| Stack | Python 3 + FastAPI, PostgreSQL, SQLAlchemy 2 + Alembic, S3-compatible object storage (MinIO). |
| Hosting | Portable: everything in Docker Compose. Demo server details TBD. |
| Core model | **Document** is the core record. A document may optionally belong to a **Project** (grant grouping). Contracts usually stand alone. |
| Classification | Every document has `kind` (contract / grant) **and** `funding_type` (external / internal). |
| Visibility | Every USER can view/download **all** documents. |
| Edit rights | Only the **uploader or ADMIN** can edit metadata, add versions, delete. |
| Roles | ADMIN, USER. **GUEST is not an account**: a guest is anyone holding a valid share link. |
| Accounts | ADMIN creates accounts. Credentials live in `auth_identities`, so SSO/LDAP can be added later. |
| Encryption | App-level envelope encryption: one random key (DEK) per file version, wrapped by a master key (KEK). |
| Auto-fill | OCR (Tesseract `tha+eng`), then **template rules stored in the DB** (keywords + regex). User confirms. Nothing leaves the server. |
| Versions | Keep version history. Share links serve the latest version unless pinned. |
| Search | Metadata + OCR text, using PostgreSQL `pg_trgm` (substring match, no Thai word splitting needed). |
| Tags | ADMIN-managed category groups (used for filters) + free user tags. |
| Owner | The **person named in the document** (PI / contract party), kept in a `people` table, separate from the uploader. |
| Dates | Store Gregorian dates. Parse/display Buddhist Era (พ.ศ. = year + 543). Thai fiscal year (Oct–Sep) is computed. |
| Delete | Soft delete → trash (share links die right away). ADMIN purges: deletes the object and its wrapped key (crypto-shred). |
| Share links | One document per link. Default 24h; USER max 7 days, ADMIN max 30 days (values in `settings`). Public or password (auto-generated). Optional download limit, view-only mode, full access log. |
| Scale | Small: < 10k docs, < 30 users. One server. OCR runs in a background worker. |
| Job queue | PostgreSQL-backed (`SELECT … FOR UPDATE SKIP LOCKED`), so no Redis is needed. |

---

## 2. Architecture

```
 Browser (USER/ADMIN)          Guest (link holder)
        │                              │
        ▼                              ▼
   ┌───────────────── FastAPI (api) ─────────────────┐
   │ auth · documents · search · shares · admin       │
   │ streams upload → encrypt → MinIO                 │
   │ streams download ← decrypt ← MinIO               │
   └───────┬───────────────────────┬──────────────────┘
           │                       │
     PostgreSQL               MinIO (ciphertext only)
   (metadata, OCR text,            ▲
    wrapped DEKs, jobs)            │
           ▲                       │
           └──── worker (OCR) ─────┘
                 decrypt to tmpfs → ocrmypdf -l tha+eng
                 → text → template match → extracted fields
```

### Upload flow
1. `POST /documents` (multipart) → API generates a DEK, stream-encrypts to MinIO, stores the wrapped DEK on the version row.
2. Version gets `ocr_status = pending`; a job is queued.
3. The worker decrypts the file to **tmpfs only**, runs OCR, stores `ocr_text`, matches a template, and writes `extracted_fields` (+ a confidence score per field).
4. The document moves to `needs_review`. The UI shows the pre-filled form, and the user confirms or edits it → `ready`.

### Encryption details
- **KEK**: 32-byte master key loaded from a file or env var, with a `key_id`. The `kek_id` column on each version allows rotation (re-wrap the DEKs; the files are untouched). It can move to Vault/KMS later.
- **DEK**: random 256-bit key per file version. Use **Tink Streaming AEAD (AES256_GCM_HKDF_1MB)** rather than custom chunking; associated data = `version_id`.
- Only ciphertext ever goes to MinIO. Plaintext exists only in memory or on the worker's tmpfs.
- **Known trade-off:** `ocr_text` and metadata are **plaintext in PostgreSQL** (required for pg_trgm search and auto-fill). Mitigations: put the DB volume on disk encryption, restrict DB access, encrypt backups. A stolen MinIO bucket alone reveals nothing; a stolen DB dump reveals OCR text but not the files.
- **Crypto-shred caveat:** a purge deletes the wrapped DEK from the live DB, but older DB backups still hold it until they expire. Document the backup retention period.

---

## 3. Database schema (PostgreSQL)

Conventions: `uuid` primary keys (`gen_random_uuid()`), `timestamptz` everywhere, `deleted_at` for soft delete,
Thai + English name columns where people read them. Extensions: `pgcrypto`, `pg_trgm`, `citext`.

```sql
-- ───────────── Accounts ─────────────
CREATE TYPE user_role   AS ENUM ('admin', 'user');
CREATE TYPE user_status AS ENUM ('active', 'disabled');

CREATE TABLE users (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  email         citext NOT NULL UNIQUE,
  display_name  text   NOT NULL,
  role          user_role   NOT NULL DEFAULT 'user',
  status        user_status NOT NULL DEFAULT 'active',
  last_login_at timestamptz,
  created_at    timestamptz NOT NULL DEFAULT now(),
  updated_at    timestamptz NOT NULL DEFAULT now()
);

-- One user can have several ways to log in (local password now, SSO later).
CREATE TABLE auth_identities (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id       uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  provider      text NOT NULL,            -- 'local', later 'sso-university'
  subject       text NOT NULL,            -- username or SSO subject id
  password_hash text,                     -- argon2id; NULL for SSO
  created_at    timestamptz NOT NULL DEFAULT now(),
  UNIQUE (provider, subject),
  CHECK (provider <> 'local' OR password_hash IS NOT NULL)
);

CREATE TABLE sessions (                   -- server-side sessions so they can be revoked
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id     uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  token_hash  bytea NOT NULL UNIQUE,      -- sha256 of cookie token
  expires_at  timestamptz NOT NULL,
  revoked_at  timestamptz,
  created_at  timestamptz NOT NULL DEFAULT now(),
  ip          inet,
  user_agent  text
);

-- ───────────── People named in documents ─────────────
CREATE TABLE people (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  prefix_th   text,                       -- ผศ.ดร., นาย, …
  name_th     text,
  name_en     text,
  affiliation text,
  email       citext,
  user_id     uuid REFERENCES users(id),  -- optional link to a system account
  created_at  timestamptz NOT NULL DEFAULT now(),
  CHECK (name_th IS NOT NULL OR name_en IS NOT NULL)
);

-- ───────────── Projects (optional grouping for grants) ─────────────
CREATE TYPE funding_type AS ENUM ('external', 'internal');
CREATE TYPE doc_kind     AS ENUM ('contract', 'grant');

CREATE TABLE projects (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  code          text UNIQUE,              -- project/grant number
  title_th      text,
  title_en      text,
  funding_type  funding_type NOT NULL,
  pi_person_id  uuid REFERENCES people(id),
  budget        numeric(14,2),
  start_date    date,
  end_date      date,
  created_by    uuid NOT NULL REFERENCES users(id),
  created_at    timestamptz NOT NULL DEFAULT now(),
  updated_at    timestamptz NOT NULL DEFAULT now(),
  deleted_at    timestamptz
);

-- ───────────── Documents ─────────────
CREATE TYPE doc_status AS ENUM ('processing', 'needs_review', 'ready', 'failed');

CREATE TABLE documents (
  id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  kind               doc_kind     NOT NULL,
  funding_type       funding_type NOT NULL,
  project_id         uuid REFERENCES projects(id),
  title              text NOT NULL,
  reference_no       text,                -- contract / grant number
  document_date      date,
  effective_from     date,
  effective_to       date,
  -- Thai fiscal year (Oct–Sep), Gregorian; UI shows +543.
  fiscal_year        int GENERATED ALWAYS AS
                       (extract(year FROM document_date + interval '3 months')::int) STORED,
  extra              jsonb NOT NULL DEFAULT '{}',   -- template-specific fields (budget, agency…)
  status             doc_status NOT NULL DEFAULT 'processing',
  current_version_id uuid,                -- FK added below (circular)
  uploaded_by        uuid NOT NULL REFERENCES users(id),
  search_text        text NOT NULL DEFAULT '',      -- denormalised: OCR text of current version
  created_at         timestamptz NOT NULL DEFAULT now(),
  updated_at         timestamptz NOT NULL DEFAULT now(),
  deleted_at         timestamptz,
  deleted_by         uuid REFERENCES users(id),
  CHECK (effective_to IS NULL OR effective_from IS NULL OR effective_to >= effective_from)
);

CREATE TYPE ocr_status AS ENUM ('pending', 'running', 'done', 'failed', 'skipped');

CREATE TABLE document_versions (
  id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  document_id       uuid NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  version_no        int  NOT NULL,
  storage_key       text NOT NULL UNIQUE,           -- MinIO object key (random, no filename)
  original_filename text NOT NULL,
  mime_type         text NOT NULL,
  size_bytes        bigint NOT NULL,
  sha256_plain      bytea NOT NULL,                 -- duplicate detection / integrity
  page_count        int,
  wrapped_dek       bytea NOT NULL,                 -- DEK encrypted by KEK
  kek_id            text  NOT NULL,                 -- which master key wrapped it
  ocr_status        ocr_status NOT NULL DEFAULT 'pending',
  ocr_text          text,
  template_id       uuid,                           -- FK below
  extracted_fields  jsonb,                          -- {"title": {"value":…, "confidence":0.92}, …}
  uploaded_by       uuid NOT NULL REFERENCES users(id),
  created_at        timestamptz NOT NULL DEFAULT now(),
  UNIQUE (document_id, version_no)
);

ALTER TABLE documents ADD FOREIGN KEY (current_version_id)
  REFERENCES document_versions(id) DEFERRABLE INITIALLY DEFERRED;

CREATE TYPE person_role AS ENUM ('owner', 'co_investigator', 'party', 'signer');

CREATE TABLE document_people (
  document_id uuid NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  person_id   uuid NOT NULL REFERENCES people(id),
  role        person_role NOT NULL,
  PRIMARY KEY (document_id, person_id, role)
);

-- ───────────── Categories (ADMIN) + free tags (USER) ─────────────
CREATE TABLE category_groups (            -- e.g. 'agency', 'status', 'research_area'
  id        uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  key       text NOT NULL UNIQUE,
  name_th   text NOT NULL,
  name_en   text,
  multi     boolean NOT NULL DEFAULT false, -- can a document have several from this group?
  sort      int NOT NULL DEFAULT 0
);

CREATE TABLE categories (
  id        uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  group_id  uuid NOT NULL REFERENCES category_groups(id),
  name_th   text NOT NULL,
  name_en   text,
  aliases   text[] NOT NULL DEFAULT '{}', -- e.g. {'วช.','NRCT'}: helps auto-fill matching
  active    boolean NOT NULL DEFAULT true,
  sort      int NOT NULL DEFAULT 0,
  UNIQUE (group_id, name_th)
);

CREATE TABLE document_categories (
  document_id uuid NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  category_id uuid NOT NULL REFERENCES categories(id),
  PRIMARY KEY (document_id, category_id)
);
-- "multi = false" (one category per group) is enforced in the service layer.

CREATE TABLE tags (
  id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name       text NOT NULL,
  normalized text NOT NULL UNIQUE,         -- lower(trim(nfc(name))), Thai digits → Arabic
  created_by uuid REFERENCES users(id)
);

CREATE TABLE document_tags (
  document_id uuid NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  tag_id      uuid NOT NULL REFERENCES tags(id),
  PRIMARY KEY (document_id, tag_id)
);

-- ───────────── Auto-fill templates ─────────────
CREATE TABLE extraction_templates (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name         text NOT NULL UNIQUE,
  kind         doc_kind,
  funding_type funding_type,
  match_rules  jsonb NOT NULL,   -- keywords/regex that identify this layout + min score
  field_rules  jsonb NOT NULL,   -- per field: regex, anchor keyword, post-processing (date_be, thai_digits…)
  priority     int NOT NULL DEFAULT 0,
  active       boolean NOT NULL DEFAULT true,
  created_by   uuid REFERENCES users(id),
  updated_at   timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE document_versions ADD FOREIGN KEY (template_id) REFERENCES extraction_templates(id);

-- ───────────── Share links ─────────────
CREATE TYPE share_access AS ENUM ('public', 'password');

CREATE TABLE share_links (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  document_id     uuid NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  version_id      uuid REFERENCES document_versions(id),  -- NULL = always latest
  token_hash      bytea NOT NULL UNIQUE,  -- sha256 of 32-byte random URL token (token shown once)
  access          share_access NOT NULL,
  password_hash   text,                   -- argon2id of auto-generated code (shown once)
  allow_download  boolean NOT NULL DEFAULT true,   -- false = view-only
  max_downloads   int CHECK (max_downloads IS NULL OR max_downloads > 0),
  download_count  int NOT NULL DEFAULT 0,
  failed_attempts int NOT NULL DEFAULT 0, -- lock link after N wrong passwords
  expires_at      timestamptz NOT NULL,
  created_by      uuid NOT NULL REFERENCES users(id),
  created_at      timestamptz NOT NULL DEFAULT now(),
  revoked_at      timestamptz,
  revoked_by      uuid REFERENCES users(id),
  note            text,                   -- "for NRCT reviewer"
  CHECK ((access = 'password') = (password_hash IS NOT NULL)),
  CHECK (expires_at > created_at)
);
-- Expiry cap (USER 7d / ADMIN 30d) is checked in the service layer against `settings`.

CREATE TYPE share_event AS ENUM ('open', 'view', 'download', 'bad_password', 'denied');

CREATE TABLE share_access_log (
  id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  share_link_id uuid NOT NULL REFERENCES share_links(id) ON DELETE CASCADE,
  event         share_event NOT NULL,
  reason        text,                     -- for 'denied': expired / revoked / limit / locked
  at            timestamptz NOT NULL DEFAULT now(),
  ip            inet,
  user_agent    text
);

-- ───────────── Audit, settings, jobs ─────────────
CREATE TABLE audit_events (               -- append-only; app role has INSERT/SELECT only
  id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  actor_id    uuid REFERENCES users(id),
  action      text NOT NULL,              -- 'document.download', 'share.create', 'user.disable'…
  entity_type text NOT NULL,
  entity_id   uuid,
  details     jsonb NOT NULL DEFAULT '{}',
  ip          inet,
  at          timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE settings (
  key   text PRIMARY KEY,                 -- 'share.default_ttl', 'share.max_ttl_user', 'share.max_ttl_admin'
  value jsonb NOT NULL
);

CREATE TYPE job_state AS ENUM ('queued', 'running', 'done', 'failed');

CREATE TABLE jobs (
  id         bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  kind       text NOT NULL,               -- 'ocr', 'purge', 'reextract'
  payload    jsonb NOT NULL,
  state      job_state NOT NULL DEFAULT 'queued',
  attempts   int NOT NULL DEFAULT 0,
  run_after  timestamptz NOT NULL DEFAULT now(),
  last_error text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

-- ───────────── Indexes ─────────────
CREATE INDEX documents_live_idx      ON documents (kind, funding_type, fiscal_year) WHERE deleted_at IS NULL;
CREATE INDEX documents_project_idx   ON documents (project_id);
CREATE INDEX documents_title_trgm    ON documents USING gin (title gin_trgm_ops);
CREATE INDEX documents_ref_trgm      ON documents USING gin (reference_no gin_trgm_ops);
CREATE INDEX documents_text_trgm     ON documents USING gin (search_text gin_trgm_ops);
CREATE INDEX people_name_th_trgm     ON people USING gin (name_th gin_trgm_ops);
CREATE INDEX people_name_en_trgm     ON people USING gin (name_en gin_trgm_ops);
CREATE INDEX share_links_active_idx  ON share_links (expires_at) WHERE revoked_at IS NULL;
CREATE INDEX share_log_link_idx      ON share_access_log (share_link_id, at DESC);
CREATE INDEX audit_entity_idx        ON audit_events (entity_type, entity_id, at DESC);
CREATE INDEX jobs_queue_idx          ON jobs (run_after) WHERE state = 'queued';
```

### Entity relationships (summary)

```
users 1─* auth_identities        users 1─* sessions
users 1─* documents (uploaded_by) people 0..1─1 users
projects 1─* documents            documents 1─* document_versions
documents *─* people     (document_people, with role: owner/co_investigator/party/signer)
documents *─* categories (document_categories) ── categories *─1 category_groups
documents *─* tags       (document_tags)
documents 1─* share_links 1─* share_access_log
extraction_templates 1─* document_versions
```

---

## 4. Rules the service layer enforces

- **Share link validity** = `revoked_at IS NULL AND now() < expires_at AND document.deleted_at IS NULL AND (max_downloads IS NULL OR download_count < max_downloads) AND failed_attempts < 10`.
- Increment `download_count` with `UPDATE … SET download_count = download_count + 1 WHERE … AND download_count < max_downloads RETURNING` (atomic, no race).
- Soft-deleting a document marks its live share links revoked in the same transaction.
- Share tokens and passwords are **shown once** and never stored in plaintext. If a password is lost, the user regenerates it.
- View-only links stream the PDF inline or as rendered page images, without a download button. This is best effort (screenshots can't be blocked).
- `multi = false` category groups allow at most one category per document.
- Edit/delete/new version: `uploaded_by = me OR role = admin`. Purge: admin only.
- Every download (user or guest), share create/revoke, user admin action, and purge writes to `audit_events`.

---

## 5. Thai-specific handling

- **DB locale (verified 2026-10-27 on postgres:17):** `CREATE DATABASE … TEMPLATE template0 ENCODING UTF8 LOCALE_PROVIDER icu ICU_LOCALE 'th-TH' LOCALE 'C.UTF-8'`. With this, pg_trgm keeps Thai words (combining marks included) intact and the GIN index serves `ILIKE '%ทุนวิจัย%'`. A plain `C` (non-UTF-8) ctype makes pg_trgm **ignore Thai**.
- Always use `ILIKE '%q%'` for correctness; the trigram index only speeds it up. For ranking long OCR text, use `word_similarity()` / `strict_word_similarity()`, not `similarity()` (a short query against a long document scores near 0). Fallback if results are poor on real OCR text: pre-tokenise with PyThaiNLP into a `tsvector` column using the `simple` config.
- Normalise text before storing and searching: Unicode NFC, Thai digits ๐–๙ → 0–9, collapse whitespace.
- Date parser for the extractor: `12 มีนาคม 2567`, `12 มี.ค. 67`, `12/03/2567` → Gregorian `2024-03-12`.
- Display: years as พ.ศ. (+543); fiscal year label `ปีงบประมาณ 2568`.

---

## 6. API sketch

```
POST   /auth/login                 POST /auth/logout             GET /me
GET    /documents?q=&kind=&funding=&fy=&category=&tag=&owner=&page=
POST   /documents                  (upload → returns id, status=processing)
GET    /documents/{id}             PATCH /documents/{id}         DELETE /documents/{id}  (soft)
POST   /documents/{id}/confirm     (accept reviewed auto-fill → ready)
POST   /documents/{id}/versions    GET /documents/{id}/versions/{n}/download
POST   /documents/{id}/shares      GET /shares (mine)            DELETE /shares/{id} (revoke)
GET    /s/{token}                  POST /s/{token}/unlock        GET /s/{token}/file   (guest)
ADMIN: /admin/users · /admin/shares (all active + logs) · /admin/trash (restore/purge)
       /admin/categories · /admin/templates · /admin/settings · /admin/audit
```

---

## 7. Build order

1. **Spike: Thai search.** ICU `th-TH` + pg_trgm basics verified on synthetic text (2026-10-27). Still to do: re-test on real Thai OCR output and decide whether the PyThaiNLP fallback is needed.
2. **Spike: OCR quality.** `ocrmypdf -l tha+eng` on the sample scans. Measure accuracy before writing templates.
3. Docker Compose (postgres, minio, api, worker) + Alembic baseline migration from §3.
4. Auth (local identities, sessions, roles) + admin user CLI bootstrap.
5. Upload/download with envelope encryption + versions.
6. OCR worker + jobs queue + template engine + review/confirm flow.
7. Search & filters.
8. Share links + access log + admin active-links screen.
9. Trash/purge, audit views, settings.

## 8. Open questions

- Sample documents for External/Internal funding (needed for templates and the frontend).
- Demo server details (OS, RAM, Docker available?, domain/HTTPS).
- Do grants really span several files? (Decides whether the Project UI is first-class or hidden.)
- Backup policy and retention period (affects crypto-shred guarantees).
- Is the plaintext OCR text in the DB acceptable to the department (see §2 trade-off)?
