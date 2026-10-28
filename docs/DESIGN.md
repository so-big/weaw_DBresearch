# DBresearch — System Design

Department web app for storing **contracts** and **research grant** documents (mostly scanned PDFs),
encrypted at rest, with OCR auto-fill, search, and expiring share links.

Status: design agreed 2026-10-27 (grill session). Internal-funding sample reviewed (§6); external funding uses the same format. First real scan reviewed. Frontend layout still pending.

---

## 1. Decisions

| Area | Decision |
|---|---|
| Deliverable | DB design + working backend (API). Frontend later. |
| Stack | Python 3 + FastAPI, PostgreSQL, SQLAlchemy 2 + Alembic, S3-compatible object storage (MinIO). |
| Hosting | Docker Compose on the shared test server `cs31@100.104.87.92`. Ports bound to `127.0.0.1`; testers reach it through an **SSH tunnel**. |
| Git | Single branch: commit and push straight to `main`. |
| Core model | **Document = one PDF = one complete package** (e.g. a grant contract plus its numbered attachments `เอกสารแนบหมายเลข N`). Detected attachments are stored as **sections** with page ranges. There's no separate Project table in v1. |
| Classification | Every document has `kind` (contract / grant) **and** `funding_type` (external / internal). |
| Visibility | Every USER can view/download **all** documents. |
| Edit rights | Only the **uploader or ADMIN** can edit metadata, add versions, delete. |
| Roles | ADMIN, USER. **GUEST is not an account**: a guest is anyone holding a valid share link. |
| Accounts | **Login will be integrated with the college system by the IT team.** We ship a minimal, swappable auth layer: local username/password for dev/demo only, behind an `AuthProvider` interface. Identity comes from the provider; **roles stay in our DB**, managed by ADMIN. No password reset, MFA or self-registration in v1. |
| Encryption | App-level envelope encryption: one random key (DEK) per file version, wrapped by a master key (KEK). |
| Auto-fill | Per page: OCR with word positions (Tesseract `tha+eng`), split the PDF into sections, then apply **section templates stored in the DB** (several label variants per field: inline / right / below). User confirms. Nothing leaves the server. See §6. |
| Uploads | **Scanner PDFs only** (`application/pdf`; other types rejected). Phone photos are used only as test samples, taken in a scanner app's document mode. |
| Funding type | Taken from the contract number letter: `R2568`**`E`**`999` = internal, `R2568`**`A`**`001` = external. Cross-checked with the header text. |
| Budget | `budget_total` is auto-filled from `งบประมาณรวม`. Line items (internal) and installments `งวด` (external) are **typed by the user** into `budget_lines`; no table parsing. |
| Checkboxes | Detect boxes visually (OpenCV) and treat ink inside a box as checked. Tuned for **typed ☑** (the only kind seen). Pen ticks aren't tuned for in v1: anything not detected confidently gives no suggestion, and the user adds tags by hand. **Checked** options → fuzzy-matched to ADMIN categories; unmatched → *suggested* free tag. **Unchecked boxes are ignored.** |
| Versions | Keep version history. Share links serve the latest version unless pinned. |
| Search | Metadata + OCR text, using PostgreSQL `pg_trgm` (substring match, no Thai word splitting needed). |
| Tags | ADMIN-managed category groups (used for filters) + free user tags. |
| Owner | The **person named in the document** (PI / contract party), kept in a `people` table, separate from the uploader. |
| Dates | Store Gregorian dates and years. Parse/display Buddhist Era (พ.ศ. = year + 543). Fiscal year is a normal column: taken from the document text ("ประจำปีงบประมาณ พ.ศ. 2568") when present, otherwise computed from `document_date` (Oct–Sep). |
| Delete | Soft delete → trash (share links die right away). ADMIN purge removes it from the **live** system only. Because backups are kept forever, a purged document can still be restored from a backup. |
| Backups | **Kept forever**: documents may be needed years later, and no data may be lost. Nightly, deduplicated, stored **off the server**. The KEK is backed up separately. See §2. |
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
                 decrypt to tmpfs → render pages 300 dpi
                 → tesseract tha+eng (word boxes) + checkbox detection
                 → sections → section templates → extracted fields
```

### Upload flow
1. `POST /documents` (multipart) → API generates a DEK, stream-encrypts to MinIO, stores the wrapped DEK on the version row.
2. Version gets `ocr_status = pending`; a job is queued.
3. The worker decrypts the file to **tmpfs only** and runs the auto-fill pipeline (§6). It stores per-page text + word boxes, detected sections, and `extracted_fields` (value + confidence + source page per field, checked-box suggestions, validation warnings).
4. The document moves to `needs_review`. The UI shows the pre-filled form with warnings highlighted, and the user confirms or edits it → `ready`. Confirmed checkbox suggestions become `document_categories` / `document_tags` rows with `source = 'auto'`.

### Encryption details
- **KEK**: 32-byte master key loaded from a file or env var, with a `key_id`. The `kek_id` column on each version allows rotation (re-wrap the DEKs; the files are untouched). It can move to Vault/KMS later.
- **DEK**: random 256-bit key per file version. Use **Tink Streaming AEAD (AES256_GCM_HKDF_1MB)** rather than custom chunking; associated data = `version_id`.
- Only ciphertext ever goes to MinIO. Plaintext exists only in memory or on the worker's tmpfs.
- **Accepted trade-off (department, 2026-10-28):** OCR text (`document_pages`, `documents.search_text`) and metadata are **plaintext in PostgreSQL**, which pg_trgm search and auto-fill require. The department considers this text low-sensitivity; the main protection is login (college SSO). The original files stay encrypted. Backups are encrypted anyway (restic).
- **Purge is not permanent erasure:** it deletes the object and wrapped DEK from the live system, but forever-kept backups still hold both. This fits the "never lose data" requirement.

### Backups (kept forever)

| What | How | Why |
|---|---|---|
| PostgreSQL | Nightly `pg_dump -Fc` (custom format) → restic | Small; holds all metadata, OCR text and wrapped DEKs |
| MinIO objects | restic over the bucket data (objects are write-once, so increments are tiny) | The encrypted files |
| Retention | **Never `restic forget`**: every snapshot is kept. Dedup keeps growth ≈ new uploads only | No data loss, years later |
| Location | **Off the server** (the shared server has a single disk). Target is TBD with IT: college NAS, another Tailscale machine, or S3-compatible cloud | A backup on the same disk isn't a backup |
| Restore drill | Monthly: restore the latest snapshot into a scratch stack, open a few documents | An untested backup is a hope, not a backup |

**KEK custody (most important):** every file is encrypted under the KEK. **If the KEK is lost, every document and every backup becomes unreadable forever.**
- Keep at least two copies outside the server **and separate from the data backups**, e.g. a password manager or vault owned by the department plus an offline copy (USB in a safe, or a printed QR/hex sheet).
- Never put the KEK in git, in the DB, or in the same restic repository as the data.
- Rotating the KEK creates a new `kek_id`. Old KEKs must be kept as long as any backup references them, which means forever.
- The restic repository password is a second secret with the same rule: lose it and the backups are gone.

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

-- ───────────── Documents (one PDF = one package) ─────────────
CREATE TYPE funding_type AS ENUM ('external', 'internal');
CREATE TYPE doc_kind     AS ENUM ('contract', 'grant');
CREATE TYPE doc_status   AS ENUM ('processing', 'needs_review', 'ready', 'failed');

CREATE TABLE documents (
  id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  kind               doc_kind     NOT NULL,
  funding_type       funding_type NOT NULL,
  title              text NOT NULL,       -- main title as written (Thai, or English when that's all there is)
  title_en           text,
  reference_no       text,                -- contract no., normalised: uppercase, no spaces (e.g. R2568A001)
  -- Parsed parts: R + B.E. year + series letter (E internal / A external) + running no. within that year+series.
  -- NULL when reference_no doesn't follow the pattern (still allowed, e.g. old or odd documents).
  ref_year_be        int  GENERATED ALWAYS AS (substring(reference_no FROM '^R(\d{4})[A-Z]\d+$')::int) STORED,
  ref_series         text GENERATED ALWAYS AS (substring(reference_no FROM '^R\d{4}([A-Z])\d+$')) STORED,
  ref_seq            int  GENERATED ALWAYS AS (substring(reference_no FROM '^R\d{4}[A-Z](\d+)$')::int) STORED,
  document_date      date,
  effective_from     date,
  effective_to       date,
  -- Thai fiscal year (Oct–Sep), Gregorian (2568 B.E. → 2025). From document text if stated,
  -- else computed from document_date by the service. UI shows +543.
  fiscal_year        int,
  budget_total       numeric(14,2),
  extra              jsonb NOT NULL DEFAULT '{}',   -- template-specific fields (agency…)
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

-- Budget breakdown, typed manually by the user (too varied to auto-parse).
-- Internal funding: items grouped by หมวด. External funding: installments (งวด) with due dates.
CREATE TYPE budget_line_type AS ENUM ('item', 'installment');

CREATE TABLE budget_lines (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  document_id uuid NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  line_type   budget_line_type NOT NULL,
  group_label text,                       -- 'หมวด 1' for items; NULL for installments
  label       text NOT NULL,              -- 'ค่าตอบแทน…' or 'งวดที่ 1'
  amount      numeric(14,2) NOT NULL CHECK (amount >= 0),
  percent     numeric(5,2),               -- installments: ร้อยละ 70
  due_date    date,                       -- installments only
  condition   text,                       -- installment condition, e.g. 'เมื่อส่งรายงานความก้าวหน้า'
  sort        int NOT NULL DEFAULT 0
);
-- Service warns (doesn't block) when SUM(amount) ≠ documents.budget_total.

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
  ocr_status        ocr_status NOT NULL DEFAULT 'pending',   -- page text lives in document_pages
  extracted_fields  jsonb,   -- {"fields": {"title": {"value":…, "confidence":0.92, "page":3}}, "checks": […], "warnings": […]}
  uploaded_by       uuid NOT NULL REFERENCES users(id),
  created_at        timestamptz NOT NULL DEFAULT now(),
  UNIQUE (document_id, version_no)
);

ALTER TABLE documents ADD FOREIGN KEY (current_version_id)
  REFERENCES document_versions(id) DEFERRABLE INITIALLY DEFERRED;

-- Attachments detected inside one PDF ("เอกสารแนบหมายเลข 5" → attachment_no 5).
-- Pages before the first marker form the main section (attachment_no NULL).
CREATE TABLE document_sections (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  version_id    uuid NOT NULL REFERENCES document_versions(id) ON DELETE CASCADE,
  attachment_no int,                      -- NULL = main body. Not unique: the same number can appear twice in one PDF
  heading       text,                     -- e.g. 'แบบเสนอโครงการวิจัย …'
  page_from     int NOT NULL,
  page_to       int NOT NULL,
  template_id   uuid,                     -- FK below; NULL = no template matched
  match_score   real,
  CHECK (page_to >= page_from)
);

CREATE TABLE document_pages (
  version_id     uuid NOT NULL REFERENCES document_versions(id) ON DELETE CASCADE,
  page_no        int  NOT NULL,           -- position in this PDF (1..n)
  printed_page_no int,                    -- 'หน้า N' from the footer; scans often contain only selected pages
  text           text NOT NULL,           -- normalised OCR text
  words          jsonb,                   -- [{t, x, y, w, h, conf, line}] for re-extraction without re-OCR
  checkboxes     jsonb,                   -- [{x, y, size, fill, checked, label, group_heading}]
  ocr_confidence real,
  PRIMARY KEY (version_id, page_no)
);

CREATE TYPE person_role AS ENUM ('owner', 'co_investigator', 'party', 'signer');

CREATE TABLE document_people (
  document_id uuid NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  person_id   uuid NOT NULL REFERENCES people(id),
  role        person_role NOT NULL,       -- หัวหน้าโครงการ → owner, ผู้ร่วมวิจัย → co_investigator
  share_pct   numeric(5,2) CHECK (share_pct BETWEEN 0 AND 100),  -- สัดส่วนการทำวิจัย (%)
  unit        text,                       -- หน่วยงาน as written on this document
  PRIMARY KEY (document_id, person_id, role)
);

-- ───────────── Categories (ADMIN) + free tags (USER) ─────────────
CREATE TABLE category_groups (            -- e.g. 'grant_type', 'research_type', 'research_group', 'discipline'
  id        uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  key       text NOT NULL UNIQUE,
  name_th   text NOT NULL,
  name_en   text,
  aliases   text[] NOT NULL DEFAULT '{}', -- heading variants seen on forms: {'ประเภทวิจัย','ประเภทการวิจัย'}
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

CREATE TYPE label_source AS ENUM ('manual', 'auto');   -- 'auto' = from a checked box, confirmed by user

CREATE TABLE document_categories (
  document_id uuid NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  category_id uuid NOT NULL REFERENCES categories(id),
  source      label_source NOT NULL DEFAULT 'manual',
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
  source      label_source NOT NULL DEFAULT 'manual',
  PRIMARY KEY (document_id, tag_id)
);

-- ───────────── Auto-fill templates (one per section type) ─────────────
-- e.g. 'internal_grant_contract' (main body), 'att_budget' (เอกสารแนบ 1), 'att_proposal_form' (เอกสารแนบ 5).
CREATE TABLE extraction_templates (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name          text NOT NULL UNIQUE,
  attachment_no int,             -- expected attachment number; NULL = main body or any
  kind          doc_kind,        -- set when matching this section implies the kind…
  funding_type  funding_type,    -- …or the funding type (e.g. 'งบประมาณรายได้คณะ' → internal)
  match_rules   jsonb NOT NULL,  -- keywords/regex that identify this section + min score
  field_rules   jsonb NOT NULL,  -- per field: list of label variants, layout (inline/right/below), regex, post-processing
  checkbox_groups boolean NOT NULL DEFAULT false, -- run checkbox → category mapping on this section
  priority      int NOT NULL DEFAULT 0,
  active        boolean NOT NULL DEFAULT true,
  created_by    uuid REFERENCES users(id),
  updated_at    timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE document_sections ADD FOREIGN KEY (template_id) REFERENCES extraction_templates(id);

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
-- One live document per contract no.; a re-upload of the same contract becomes a new version instead.
CREATE UNIQUE INDEX documents_ref_uniq ON documents (reference_no) WHERE deleted_at IS NULL AND reference_no IS NOT NULL;
CREATE INDEX documents_ref_seq_idx   ON documents (ref_year_be, ref_series, ref_seq) WHERE deleted_at IS NULL;
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
documents 1─* document_versions 1─* document_pages
                                  document_versions 1─* document_sections *─0..1 extraction_templates
documents *─* people     (document_people, with role: owner/co_investigator/party/signer)
documents *─* categories (document_categories, source manual/auto) ── categories *─1 category_groups
documents *─* tags       (document_tags, source manual/auto)
documents 1─* share_links 1─* share_access_log
documents 1─* budget_lines   (manual: items or installments)
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
- Normalise text before storing and searching: Unicode NFC, strip zero-width chars (U+200B/200C/200D/FEFF), recompose `ํ`+`า` → `ำ`, remove stray spaces before Thai combining marks (`ช ื่อ` → `ชื่อ`), Thai digits ๐–๙ → 0–9, collapse whitespace.
- Date parser for the extractor: `12 มีนาคม 2567`, `12 มี.ค. 67`, `12/03/2567` → Gregorian `2024-03-12`.
- Display: years as พ.ศ. (+543); fiscal year label `ปีงบประมาณ 2568`.

---

## 6. Auto-fill pipeline (from the mock and the first real scan)

### What the sample shows (`docs/sample document-1.pdf`, 3 pages, gitignored)

| Page | Section | Useful content |
|---|---|---|
| 1 | Main body: `สัญญารับทุนอุดหนุนการวิจัย จากงบประมาณรายได้คณะ… ประจำปีงบประมาณ พ.ศ. 2568` | kind = contract/grant, funding = **internal** (`งบประมาณรายได้คณะ`), fiscal year, `โครงการ : <title>` (inline) |
| 2 | `เอกสารแนบหมายเลข 1` (budget) | `สัญญาเลขที่`, `โครงการ <title>` (bold, no colon, wraps to 2 lines), `งบประมาณรวม ในวงเงิน 10,000 บาท(หนึ่งแสนบาทถ้วน)`, budget item table (**not parsed**; user types it) |
| 3 | `เอกสารแนบหมายเลข 5` (proposal form) | `ชื่อโครงการวิจัย (ภาษาไทย) … (ภาษาอังกฤษ) …` (value in a right-hand column), **checkbox groups**: ประเภททุน, 1. ประเภทวิจัย, 2. กลุ่มการวิจัย, 3. สาขาวิชาการ |
| every | Footer | `สัญญาเลขที่ R2568E999` · `หน้า N` · `“<owner name>”` (quoted, may wrap) |

Observations that shape the design:
- **One PDF = many sections.** Attachment numbers have gaps (1 and 5 only), and the marker wording varies (`เอกสารแนบหมายเลข 5` / `เอกสารแนบหมายเลขที่ 5`).
- **The same field has different labels and layouts** in different sections. Some sections lack a field entirely.
- **Checked labels are struck through** in the sample, which damages OCR of the label text.
- **The sample's figures and words disagree** (`10,000` vs `หนึ่งแสน` = 100,000). Real documents may too, so cross-check and warn.
- **The PDF's embedded text layer garbles Thai** (`ช ื่อ`, `สญั ญา`, zero-width spaces). Default to OCR of rendered pages; whether to use a text layer at all is decided by a spike.

### Steps (worker)

1. **Render** each page into tmpfs at an effective 300 dpi. If the embedded image is lower (the phone test captures are 150–190 dpi), upscale it (Thai vowel and tone marks need the resolution). Then:
   - crop to the page outline (a safeguard; test photos show neighbouring sheets and clips at the edges, scanner PDFs rarely do)
   - light deskew (1–2°)
   - remove the background and shadows, then binarise (adaptive threshold), so faint seal watermarks and coloured stamps drop out
   - no perspective correction in production (scanner PDFs)
2. **Checkbox detection** (OpenCV): find small near-square contours (≈ 2–6 mm) with a hollow border. Fill ratio = dark pixels inside the box after trimming its border. Above the threshold → checked. Inside the uncertainty band → `checked: null`, **no suggestion** (no warning needed; the user tags manually). Tuned on typed ☑; pen ✓/✗ may or may not be caught, and the fallback is always manual tagging.
3. **Line removal + OCR**: remove long horizontal strokes (strikethrough, table rules) with a morphological opening, then `tesseract -l tha+eng` with **TSV output** (words + boxes + confidence). Normalise the text (§5). Store it in `document_pages`.
4. **Sectioning**: classify **each page by its heading** (template `match_rules` on the top third of the page), and use the attachment marker only as a hint. Marker regex: `เอกสารแนบ\s*(หมายเลข)?\s*(ที่)?\s*([0-9๐-๙]+)`. The real scan shows it as a boxed label, as underlined text, and **even on the main contract page** (`เอกสารแนบ 1` on the contract itself), so a marker alone doesn't start a new section. Consecutive pages with the same classification form one section. Pages that match nothing join the previous section.
5. **Template match per section**: score each active template's `match_rules` against the section text. The best one above its minimum score is assigned. The template may imply `kind` / `funding_type`.
6. **Field extraction**: each field rule lists **label variants** and, for each, a layout:
   - `inline`: value after the label on the same line (`โครงการ : X`)
   - `right`: value in the column to the right, possibly continuing on following lines (`(ภาษาไทย)  X`)
   - `below`: value on the next line(s)
   - `footer`: majority vote over all pages' footers (contract no., owner)
   - `sentence`: regex over running text, for contract clauses (`เมื่อวันที่ <date>`, `นับตั้งแต่วันที่ <date> ถึงวันที่ <date>`, `ในวงเงิน <amount> บาท (<words>)`, `เรื่อง “<title>”`)
   - `block`: repeated label groups, e.g. the research-team block (`ชื่อ – สกุล` / `หน่วยงาน` / `บทบาทในโครงการ` / `สัดส่วนการทำวิจัย (%)`), producing one record per repeat

   Values are cleaned of dotted leaders (`.....`), and academic prefixes (`ผศ.ดร.`, `นางสาว`, …) are split into `people.prefix_th`.

   When several sections produce a value, the highest confidence wins. The losing candidates are kept for the review UI.
7. **Checkbox → categories** (sections whose template has `checkbox_groups = true`):
   - For each **checked** box: label = OCR words to the right of the box on the same line. Group heading = the nearest line above that sits further left (with numbering like `1.` stripped).
   - Heading → `category_groups` by fuzzy match against `name_th` + `aliases`. Label → `categories` within that group by fuzzy match against `name_th` + `aliases` (RapidFuzz on normalised text, threshold ~85).
   - Matched → category suggestion. Unmatched (or heading unknown) → suggested free tag. **Unchecked boxes are ignored.**
8. **Validation warnings** (shown in the review UI, never block):
   - amount in digits ≠ amount in Thai words (`thaiword_to_num` from PyThaiNLP)
   - fiscal year in the header ≠ year in the contract no. (`R2568…`)
   - funding type from the contract no. letter ≠ funding type implied by the header text
   - contract no. differs between pages
   - contract no. already exists on a live document → suggest *new version* instead
   - **more than one contract no. in one PDF** → warn *"pages show different contract numbers"* (a real PDF is always one contract, so this means a wrong upload or an OCR misread; no auto-split)
   - more than one box checked in a single-choice group (`ระบุ…เพียงข้อเดียว`)
   - research-team shares don't add up to 100 %
   - installment amounts ≠ percent × total, or don't sum to the total (once typed)
   - required field missing
9. Write `document_sections` and `extracted_fields`, set `status = needs_review`.

### Contract number
Format: `R` + B.E. year + funding letter + running number.

| Example | Year | Letter | Funding type |
|---|---|---|---|
| `R2568E999` | 2568 (FY 2025) | `E` | internal |
| `R2568A001` | 2568 (FY 2025) | `A` | external |

Parse with `R(\d{4})([A-Z])(\d+)`, after normalising Thai digits and fixing common OCR mix-ups (`O`→`0` and `I`/`l`→`1` inside the digit groups). The letter sets `funding_type` (the strongest signal), and the year cross-checks `fiscal_year`. An unknown letter → no funding type + warning; the user picks it.

**Running number:** counts up separately for each year + series. `R2568E001` is the first internal contract of 2568, and `R2568A001` is the first external one. (This is the department's understanding; confirm it against more samples.) The system only **stores** numbers issued by the department; it never generates them. What it's used for:
- **Sorting**: order lists by `(ref_year_be, ref_series, ref_seq)` so `E002` comes before `E010`, not by the raw text.
- **Duplicate upload**: if the extracted number matches a live document, the review screen offers *"add as a new version of R2568A001"* instead of creating a duplicate. The partial unique index enforces it.
- **Missing numbers report** (ADMIN): for each year + series, list the gaps between 1 and the highest `ref_seq` (e.g. internal 2568: E004, E007 missing). Shows which contracts haven't been archived yet.
- Search accepts both the short and padded forms (`A1` → `A001`).

### Package structure (one PDF = one contract)

| Part | Content | Auto-fill |
|---|---|---|
| Contract body | Header (programme, funding source/agency, fiscal year), parties, clauses: signing date, period, amount, title | **Yes**: template `contract_body` |
| `เอกสารแนบหมายเลข 1` | Money: total budget + item table (internal) or installments `งวด` (external) | **Yes**: `budget_total` only (breakdown is typed manually) |
| `เอกสารแนบหมายเลข 2–4` | Supporting documents | **No**: OCR'd for search only, stored as sections with their attachment number and no template |
| `เอกสารแนบหมายเลข 5` (last) | Project proposal form: Thai/English title, checkbox groups, research team | **Yes**: template `att_proposal_form` (checkboxes → categories, team → people) |

So v1 needs three section templates. Pages that match none of them become sections keyed by their marker number (or join the previous section). A `เอกสารแนบ 1` label printed on the contract page itself is ignored, because the heading classifies that page as the contract body.

### Findings from the first real scan (`samples/`, 5 pages, confidential, gitignored)

**Test capture only:** phone scanner app (ML Kit) → image-only PDF, colour JPEG, **149–191 dpi**, no text layer. Production uploads are office-scanner PDFs of the **same documents**, so the layout findings apply; the photo artifacts (marked *photo*) mostly don't. Pages 1–3 are an internal contract (`R2568E0xx`); pages 4–5 are an external contract (`R2568A0xx`). They were combined only as examples; **a real PDF always holds exactly one contract**. Footers show `หน้า 1/5/10`, so only selected pages were scanned.

| Topic | What the scan shows | Design consequence |
|---|---|---|
| Page noise | *photo:* edges of other sheets, a paper clip, folded corners, low dpi. *Real document:* a `คู่ฉบับ` stamp, a confidentiality notice top-left, faint seal watermark mid-page | Stamps and watermark are real → adaptive threshold + ignore the stamp words. Page-outline cropping is a cheap safeguard, needed mainly for test photos |
| Attachment markers | `เอกสารแนบ 1` (boxed, on the **contract page itself**), `เอกสารแนบหมายเลข 1` (underlined), `เอกสารแนบหมายเลข 5` (boxed) | Classify pages by heading; marker is only a hint (step 4) |
| Header, internal | `สัญญารับทุนอุดหนุนการวิจัย [วิจัยสถาบัน] จากงบประมาณรายได้คณะ… ประจำปีงบประมาณ พ.ศ. 2568` | `[…]` = grant programme → category. `รายได้คณะ` → internal |
| Header, external | `สัญญารับทุนอุดหนุนการวิจัย ภายใต้บันทึกความเข้าใจ… ประจำปี พ.ศ. 2568 ระหว่าง <agency> กับมหาวิทยาลัยนเรศวร` | Fiscal-year label variant `ประจำปี พ.ศ.`; agency name → `agency` category (with aliases such as `สป.อว.`) |
| Contract body | Signing date `เมื่อวันที่ …`, period `นับตั้งแต่วันที่ … ถึงวันที่ …`, amount `ในวงเงิน … บาท (…)`, title in `ข้อ 1 … เรื่อง “…”` | Auto-fill `document_date`, `effective_from/to`, a second `budget_total` source and a second title source |
| Recipient | Named in the internal body; **blank** in the external body | The footer name is the reliable owner source; body is a fallback |
| Title | External title is **English only** (with a collaborator name in brackets) | `title` holds whichever language is present |
| Checkbox page | Typed ☑ (no strikethrough). Headings carry instructions: `1. ประเภทการวิจัย (ระบุความสอดคล้องเพียงข้อเดียว)` | Strip numbering **and** the bracketed instruction before matching; `เพียงข้อเดียว` ⇒ single choice |
| Research team | `ส่วน ข` repeats `ชื่อ – สกุล / หน่วยงาน / บทบาทในโครงการ / สัดส่วนการทำวิจัย (%)` with dotted leaders | `block` rule → `document_people` (role + `share_pct` + `unit`) |
| External budget | `งวดที่ N (ร้อยละ P) จำนวนเงิน X บาท (…)` + condition text | Still typed manually (decision), but regular enough to auto-fill later; added `percent` column |
| Internal budget | Table grouped by `หมวด…` with numbered items | Manual (decision) |

### Seed data (ADMIN can edit)

Category options differ between grant programmes, so each group holds the union. The `multi` column comes from the form instructions.

| Group (`key`) | Heading variants | Multi | Options |
|---|---|---|---|
| `grant_programme` | text in `[…]` in the contract header | no | วิจัยสถาบัน |
| `agency` | contract header (`ระหว่าง …`, `จากงบประมาณ…`) | no | สำนักงานปลัดกระทรวงการอุดมศึกษา วิทยาศาสตร์ วิจัยและนวัตกรรม (alias `สป.อว.`) · งบประมาณรายได้คณะวิศวกรรมศาสตร์ |
| `research_type` | ประเภทการวิจัย, ประเภทวิจัย | no | เพื่อแก้ปัญหา · เพื่อการวางแผนพัฒนา · เพื่อการประกันคุณภาพ · พื้นฐาน · ทดลองและพัฒนา |
| `research_group` | กลุ่มการวิจัย | no | นิสิต / นักศึกษา · บุคลากร · หลักสูตร / โปรแกรมการศึกษา · การเงิน / งบประมาณ · อาคารสถานที่ และสิ่งอำนวยความสะดวก · วิทยาศาสตร์เทคโนโลยี · วิทยาศาสตร์สุขภาพ |
| `grant_type` | ประเภททุน | no | นักวิจัยรุ่นใหม่ · ทุนวิจัยสำหรับนักวิจัยที่มีประสบการณ์ด้านการวิจัย *(mock only)* |
| `discipline` | สาขาวิชาการ | ? | วิศวกรรมศาสตร์และอุตสาหกรรมวิจัย · นิติศาสตร์ *(mock only)* |

### Python libraries
`opencv-python-headless`, `pytesseract` (+ `tesseract-ocr-tha` in the image), `pdf2image`/`pdftoppm` (poppler), `rapidfuzz`, `pythainlp`.

---

## 7. API sketch

```
POST   /auth/login                 POST /auth/logout             GET /me
GET    /documents?q=&kind=&funding=&fy=&category=&tag=&owner=&page=
POST   /documents                  (upload → returns id, status=processing)
GET    /documents/{id}             PATCH /documents/{id}         DELETE /documents/{id}  (soft)
POST   /documents/{id}/confirm     (accept reviewed auto-fill → ready)
POST   /documents/{id}/versions    GET /documents/{id}/versions/{n}/download
POST   /documents/{id}/shares      GET /shares (mine)            DELETE /shares/{id} (revoke)
GET    /s/{token}                  POST /s/{token}/unlock        GET /s/{token}/file   (guest)
ADMIN: /admin/reports/missing-numbers?year=2568&series=E
       /admin/users · /admin/shares (all active + logs) · /admin/trash (restore/purge)
       /admin/categories · /admin/templates · /admin/settings · /admin/audit
```

---

## 8. Build order

1. **Spike: Thai search.** ICU `th-TH` + pg_trgm basics verified on synthetic text (2026-10-27). Still to do: re-test on real Thai OCR output and decide whether the PyThaiNLP fallback is needed.
2. **Spike: OCR + checkboxes.** On the server: Tesseract `tha+eng` accuracy on the sample (rendered vs. text layer), checkbox detection + fill threshold, and strikethrough removal. Typed ☑ only (no pen-tick samples).
3. Docker Compose (postgres, minio, api, worker) + Alembic baseline migration from §3.
4. Auth (local identities, sessions, roles) + admin user CLI bootstrap.
5. Upload/download with envelope encryption + versions.
6. Worker + jobs queue + auto-fill pipeline (§6) + review/confirm flow.
7. Search & filters.
8. Share links + access log + admin active-links screen.
9. Trash/purge, audit views, settings.
10. Backups: nightly `pg_dump` + restic (no forget), restore drill script, KEK custody runbook.

## 9. Open questions

- **For the IT team**: backup target (NAS / other machine / cloud) and who holds the KEK copies.
- **For the IT team**: SSO protocol of the college system (OIDC, SAML, LDAP, or a trusted reverse-proxy header) → which `AuthProvider` to implement. Do SSO users get auto-created as `user` on first login, or must ADMIN pre-create them?
