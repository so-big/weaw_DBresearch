# DBresearch — System Design

Department web app for storing **contracts** and **research grant** documents (mostly scanned PDFs),
encrypted at rest, with OCR auto-fill, search, and expiring share links.

Status: design agreed 2026-10-27 (grill session). Internal-funding sample reviewed (§6); external funding uses the same format. First real scan reviewed. Frontend layout still pending.

---

## 1. Decisions

| Area | Decision |
|---|---|
| Deliverable | DB design + working backend (API). Frontend later. |
| Stack | Python 3.13 + FastAPI, PostgreSQL 17, SQLAlchemy 2 + Alembic. |
| File store | **Local folder** (Docker volume `blobs`) behind a `BlobStore` interface. An S3 backend can be added later without touching callers. MinIO was dropped: the project was discontinued (GitHub archived 2026-04, Docker images removed). |
| Hosting | Docker Compose on the shared test server `cs31@100.104.87.92`. Ports bound to `127.0.0.1`; testers reach it through an **SSH tunnel**. |
| Git | Single branch: commit and push straight to `main`. |
| Core model | **Document = one PDF = one complete package** (e.g. a grant contract plus its numbered attachments `เอกสารแนบหมายเลข N`). Detected attachments are stored as **sections** with page ranges. There's no separate Project table in v1. |
| Classification | Every document has `kind` (contract / grant) **and** `funding_type` (external / internal). |
| Visibility | Every USER can view/download **all** documents. |
| Edit rights | Only the **uploader or ADMIN** can edit metadata, add versions, delete. |
| Roles | ADMIN, USER. **GUEST is not an account**: a guest is anyone holding a valid share link. |
| Accounts | **Login goes through the university's login API** (university ID + password; the API also returns the account type). Only **teacher and staff/employee** accounts may log in (`UNIVERSITY_ALLOWED_TYPES`; staff such as the research office enter papers); students are refused. ADMIN is the IT team; everyone else, research office included, is `user`. Guests never need an account (share links). The app is deployed on the university's server, which the API already trusts. Providers sit behind `AuthProvider` and are tried in order (`AUTH_PROVIDERS=local,university`); local username/password stays for dev/demo and bootstrap admins. **Roles stay in our DB**, managed by ADMIN: a teacher can log in only once ADMIN has added them (same email or university ID; default `UNIVERSITY_AUTO_CREATE=false`). An approval queue for first logins is planned (§9). No password reset, MFA or self-registration of local accounts. *(Decided 2026-11-09. The API spec is still pending: only `HttpUniversityClient.verify` in `dbresearch/university.py` changes when it arrives.)* |
| Login security | Server-side sessions (cookie holds a random token, DB its hash; `HttpOnly`, `SameSite=Lax`, `Secure` in production). A session ends after **12 h**, or **60 min idle** (`sessions.last_seen_at`, refreshed at most once a minute). At most **5 sessions per user**: a new login ends the oldest; logging in again on a browser ends that browser's old session. Users can log out on every device; ADMIN can see a user's devices and end them. Brute-force guard: 5 failures per username or 20 per IP in 15 min → `429`. University API outages answer `503` and don't count as failures. With `COOKIE_SECURE=true` every response sends HSTS (no `includeSubDomains`: other university sites share the domain). `/api` responses are `no-store`. ADMIN's audit page shows a 24 h login summary (failures, blocks, top usernames/IPs, which are locked now) and warns about unsafe server settings. |
| Encryption | App-level envelope encryption: one random key (DEK) per file version, wrapped by a master key (KEK). |
| Auto-fill | Per page: OCR with word positions (Tesseract `tha+eng`), split the PDF into sections, then apply **section templates stored in the DB** (several label variants per field: inline / right / below). User confirms. Nothing leaves the server. See §6. |
| Uploads | **Scanner PDFs only** (`application/pdf`; other types rejected). Phone photos are used only as test samples, taken in a scanner app's document mode. |
| Funding type | Taken from the contract's **title block** (the lines above `โครงการ :`): a contract *between* an outside agency and the university (`… ระหว่าง <agency> กับมหาวิทยาลัย…`) is **external**; one paid `จากงบประมาณ…` of a single unit (e.g. `รายได้คณะวิศวกรรมศาสตร์`) is **internal**. The parties clause below the title also says `ระหว่างคณะ… กับ <researcher>`, so it is ignored. *(Corrected 2026-11-02: the contract-number letter is the faculty, not the funding type.)* |
| Contract-number letter | `R2568`**`E`**`047`: the letter is the **faculty** that issued the number (`E` = engineering; others A–… are other faculties). It never sets the funding type. |
| Close a project | ปิดโครงการ: the uploader or an admin attaches the closing papers (approval memo, faculty-meeting resolution) **to the contract** and marks it closed with the approval date and memo/resolution no. Closed projects form an **archive**: hidden from the default list, one filter away, still searchable (their closing papers too). Reopening is allowed and logged. |
| Category options | Any USER may add an option to a category group from the review form (decided 2026-11-02, no admin approval). Admins tidy the list later. Still never created automatically from OCR. |
| Budget | `budget_total` is auto-filled from `งบประมาณรวม`. Installments `งวดที่ N` are **suggested** from the budget attachment (both internal and external contracts use them) and confirmed by the user with one click; item tables (`หมวด…`) are still typed by hand. |
| Checkboxes | Detect boxes visually (OpenCV) and treat ink inside a box as checked. Tuned for **typed ☑** (the only kind seen). Pen ticks aren't tuned for in v1: anything not detected confidently gives no suggestion, and the user adds tags by hand. **Checked** options → fuzzy-matched to ADMIN categories; unmatched → *suggested* free tag. **Unchecked boxes are ignored.** |
| Versions | Keep version history. Share links serve the latest version unless pinned. |
| Search | Metadata + OCR text, using PostgreSQL `pg_trgm` (substring match, no Thai word splitting needed). |
| Tags | ADMIN-managed category groups (used for filters) + free user tags. |
| Owner | The **person named in the document** (PI / contract party), kept in a `people` table, separate from the uploader. |
| Dates | Store Gregorian dates and years. Parse/display Buddhist Era (พ.ศ. = year + 543). Fiscal year is a normal column: taken from the document text ("ประจำปีงบประมาณ พ.ศ. 2568") when present, otherwise computed from `document_date` (Oct–Sep). |
| Delete | Soft delete → trash (share links die right away). ADMIN purge removes it from the **live** system only. Because backups are kept forever, a purged document can still be restored from a backup. |
| Backups | **Kept forever**: documents may be needed years later, and no data may be lost. Nightly, deduplicated, stored **off the server**. The KEK is backed up separately. See §2. |
| Sharing rights | Any USER can share a document they can read; the link's creator or an ADMIN manages it. |
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
   │ streams upload → encrypt → BlobStore             │
   │ streams download ← decrypt ← BlobStore           │
   └───────┬───────────────────────┬──────────────────┘
           │                       │
     PostgreSQL           BlobStore folder (ciphertext only)
   (metadata, OCR text,            ▲
    wrapped DEKs, jobs)            │
           ▲                       │
           └──── worker (OCR) ─────┘
                 decrypt to tmpfs → render pages 300 dpi
                 → tesseract tha+eng (word boxes) + checkbox detection
                 → sections → section templates → extracted fields
```

### Upload flow
1. `POST /documents` (multipart) → API generates a DEK, stream-encrypts to the BlobStore, stores the wrapped DEK on the version row.
2. Version gets `ocr_status = pending`; a job is queued.
3. The worker decrypts the file to **tmpfs only** and runs the auto-fill pipeline (§6). It stores per-page text + word boxes, detected sections, and `extracted_fields` (value + confidence + source page per field, checked-box suggestions, validation warnings).
4. The document moves to `needs_review`. The UI shows the pre-filled form with warnings highlighted, and the user confirms or edits it → `ready`. Confirmed checkbox suggestions become `document_categories` / `document_tags` rows with `source = 'auto'`.

### Encryption details
- **KEK**: 32-byte master key loaded from a file or env var, with a `key_id`. The `kek_id` column on each version allows rotation (re-wrap the DEKs; the files are untouched). It can move to Vault/KMS later.
- **DEK**: random 256-bit key per file version. Use **Tink Streaming AEAD (AES256_GCM_HKDF_1MB)** rather than custom chunking; associated data = `version_id`.
- Only ciphertext ever goes to the BlobStore. Plaintext exists only in memory or on the worker's tmpfs.
- **Accepted trade-off (department, 2026-10-28):** OCR text (`document_pages`, `documents.search_text`) and metadata are **plaintext in PostgreSQL**, which pg_trgm search and auto-fill require. The department considers this text low-sensitivity; the main protection is login (college SSO). The original files stay encrypted. Backups are encrypted anyway (restic).
- **Purge is not permanent erasure:** it deletes the object and wrapped DEK from the live system, but forever-kept backups still hold both. This fits the "never lose data" requirement.

### Backups (kept forever)

| What | How | Why |
|---|---|---|
| PostgreSQL | Nightly `pg_dump -Fc` (custom format) → restic | Small; holds all metadata, OCR text and wrapped DEKs |
| Blob folder | restic over the `blobs` volume (files are write-once, so increments are tiny) | The encrypted files |
| Retention | **Never `restic forget`**: every snapshot is kept. Dedup keeps growth ≈ new uploads only | No data loss, years later |
| Location | **Off the server** (the shared server has a single disk). **Assumed: the college NAS** (not yet confirmed by IT). The restic repository URL is configuration (`RESTIC_REPOSITORY`: SFTP, SMB mount, or S3), so the target can change without code changes | A backup on the same disk isn't a backup |
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

-- One user can have several ways to log in (local password, university account).
CREATE TABLE auth_identities (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id       uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  provider      text NOT NULL,            -- 'local' | 'university'
  subject       text NOT NULL,            -- username, or the university ID
  password_hash text,                     -- argon2id; NULL for 'university' (never stored)
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
  last_seen_at timestamptz NOT NULL DEFAULT now(),  -- idle timeout (session_idle_minutes)
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
CREATE TYPE doc_kind     AS ENUM ('contract', 'grant', 'proposal_dev', 'other');  -- proposal_dev: §11; other: programme papers
-- Funding filter (all sections). internal/external follows: FF and external → external (FF decided 2026-11-09).
CREATE TYPE funding_source AS ENUM ('ff', 'nu_income', 'faculty_income', 'external');
CREATE TYPE doc_status   AS ENUM ('processing', 'needs_review', 'ready', 'failed');

CREATE TABLE documents (
  id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  kind               doc_kind,            -- may be empty until review
  funding_type       funding_type,        -- ready needs it, except kind 'other'
  funding_source     funding_source,      -- CHECK: funding_type matches it
  funder_name        text,                -- the outside agency when funding_source = 'external'
  title              text NOT NULL,       -- main title as written (Thai, or English when that's all there is)
  title_en           text,
  reference_no       text,                -- contract no., normalised: uppercase, no spaces (e.g. R2568A001)
  -- Parsed parts: R + B.E. year + series letter (the issuing faculty, E = engineering) + running no. within that year+series.
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
  search_text        text NOT NULL DEFAULT '',      -- OCR text of current version + metadata, normalised, ALL whitespace removed (§5)
  created_at         timestamptz NOT NULL DEFAULT now(),
  updated_at         timestamptz NOT NULL DEFAULT now(),
  deleted_at         timestamptz,
  deleted_by         uuid REFERENCES users(id),
  -- ปิดโครงการ (archive). Closing papers are document_versions with purpose = 'closure'.
  closed_on          date,                -- approval date on the closing papers
  closed_at          timestamptz,         -- marked closed in the system (NULL = active project)
  closed_by          uuid REFERENCES users(id),
  closure_ref        text,                -- memo / resolution no., e.g. อว 0000.00/123
  closure_note       text,
  -- ยกเลิก: ended without result. CHECK: never both closed and cancelled.
  cancelled_on       date,
  cancelled_at       timestamptz,
  cancelled_by       uuid REFERENCES users(id),
  cancel_ref         text,
  cancel_reason      text,
  CHECK (effective_to IS NULL OR effective_from IS NULL OR effective_to >= effective_from)
);

-- Proposal-development grants (§11): fields only they have, 1:1 with a proposal_dev document.
-- Researcher + department live in document_people (role owner, unit); amount / period / fiscal year
-- in documents.budget_total / effective_from–to / fiscal_year.
CREATE TYPE proposal_outcome AS ENUM ('submitted', 'won', 'not_won');
CREATE TABLE proposal_projects (
  document_id         uuid PRIMARY KEY REFERENCES documents(id) ON DELETE CASCADE,
  request_ref         text,               -- request memo no., e.g. อว 0603.09.02/674
  research_area       text,               -- กรอบงานวิจัย
  kpi_target          text,               -- e.g. proposal for an outside grant + Impact Pathway
  kpi_due             date,
  kpi_result          text,               -- what the closing memo says was delivered
  spent_total         numeric(14,2) CHECK (spent_total >= 0),
  outcome             proposal_outcome,   -- optional: did the proposal win the outside grant?
  outcome_funder      text,
  outcome_document_id uuid REFERENCES documents(id) ON DELETE SET NULL  -- the contract it won
);

-- A project's timeline; each event points at its memo (a document_versions row).
CREATE TYPE project_event_type AS ENUM
  ('approved', 'title_change', 'budget_change', 'close', 'cancel', 'reopen', 'other');
CREATE TABLE project_events (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  document_id uuid NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  event_type  project_event_type NOT NULL,
  event_on    date,                       -- date on the memo
  memo_ref    text,
  version_id  uuid REFERENCES document_versions(id) ON DELETE SET NULL,
  details     jsonb NOT NULL DEFAULT '{}',  -- e.g. {"old_title": …, "new_title": …}
  created_by  uuid REFERENCES users(id),
  created_at  timestamptz NOT NULL DEFAULT now()
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
  actual_amount numeric(14,2) CHECK (actual_amount >= 0),  -- spent, from a closing report
  percent     numeric(5,2),               -- installments: ร้อยละ 70
  due_date    date,                       -- installments only
  condition   text,                       -- installment condition, e.g. 'เมื่อส่งรายงานความก้าวหน้า'
  sort        int NOT NULL DEFAULT 0
);
-- Service warns (doesn't block) when SUM(amount) ≠ documents.budget_total.

CREATE TYPE ocr_status AS ENUM ('pending', 'running', 'done', 'failed', 'skipped');

CREATE TYPE version_purpose AS ENUM ('main', 'closure', 'paper');  -- paper: cancellation / change memos

CREATE TABLE document_versions (
  id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  document_id       uuid NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  purpose           version_purpose NOT NULL DEFAULT 'main', -- 'closure' = a closing paper (own numbering)
  version_no        int  NOT NULL,
  storage_key       text NOT NULL UNIQUE,           -- BlobStore key (random, no filename)
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
  UNIQUE (document_id, purpose, version_no)
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
  user_agent    text,
  user_id       uuid REFERENCES users(id)  -- set when the visitor was logged in; NULL = guest
);

-- ───────────── Audit, settings, jobs ─────────────
CREATE TABLE audit_events (               -- append-only: a trigger rejects UPDATE/DELETE/TRUNCATE
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
- Closing a project: uploader or admin, like other edits. Closing papers never replace the current version and don't change the review status; a purge removes them with the document.
- Edit/delete/new version: `uploaded_by = me OR role = admin`. Purge: admin only.
- Restore from the trash: an admin, or the uploader when they deleted it themselves (an admin's delete stays with the admin). Each user sees their own bin (documents they uploaded or deleted); restoring never revives old share links.
- Bulk actions (select mode) are all-or-nothing in one transaction, at most 100 documents. A zip download writes one `document.download` audit row per file.
- Every download (user or guest), share create/revoke, user admin action, and purge writes to `audit_events`.

---

## 5. Thai-specific handling

- **DB locale (verified 2026-10-27 on postgres:17):** `CREATE DATABASE … TEMPLATE template0 ENCODING UTF8 LOCALE_PROVIDER icu ICU_LOCALE 'th-TH' LOCALE 'C.UTF-8'`. With this, pg_trgm keeps Thai words (combining marks included) intact and the GIN index serves `ILIKE '%ทุนวิจัย%'`. A plain `C` (non-UTF-8) ctype makes pg_trgm **ignore Thai**.
- **Search is space-insensitive.** OCR spacing in Thai never matches what a user types (`การพัฒนา ประสิทธิภาพ` found 0 pages as typed, 4 with spaces ignored). So `documents.search_text` stores the normalised text with **all whitespace removed**, and the query gets the same treatment: `search_text ILIKE '%' || compact(normalize(q)) || '%'`. Page text with spaces is kept in `document_pages.text` for display and snippets.
- Always use `ILIKE` for correctness; the trigram index only speeds it up. For ranking, use `word_similarity()` / `strict_word_similarity()`, not `similarity()` (a short query against a long document scores near 0).
- **Verified on real OCR text (2026-10-28):** 13/13 test queries found their pages (Thai titles, place names, `R2568A034` and lower-case `r2568e009`, amounts in Thai words, Thai dates, English words, `งวดที่ 2`), GIN index used. The PyThaiNLP fallback is **not needed**.
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

1. **Render** each page at 300 dpi, grayscale (`pypdfium2`; upsamples lower-dpi scans). Measured: **no extra cleaning needed**. A background-flattening + Otsu variant didn't improve confidence or label recall, so Tesseract gets the plain grayscale page. Ignore any embedded text layer (the mock's is garbled; scans have none). Later safeguards if real scans need them: crop to the page outline, light deskew.
2. **Checkbox detection** (OpenCV, tuned on both samples; see §6 spike results):
   - **find**: adaptive threshold (mean, block 35, C 15). A contour is a box if its side is **3–7 mm**, its aspect is 0.75–1.33, it approximates a **convex 4-gon**, its area is ≥ 70 % of its bounding rect, and **all four sides are ≥ 80 % continuous ink**. The last rule removes square-ish letters. Nested outer/inner border contours are merged.
   - **state**: ink ratio inside the inner 60 % of the box: **≥ 0.12 checked**, **≤ 0.03 empty**, otherwise unsure → no suggestion (the user tags manually). Tuned on typed ☑; pen ✓/✗ is untested.
   - **heading**: the nearest OCR line above the box that starts further left and isn't itself an option row. Strip numbering (`1.`) and bracketed instructions (`(ระบุ…เพียงข้อเดียว)`).
   - **label**: page-OCR words on the box's row, right of the box. If that doesn't match an option (page OCR sometimes drops a row), re-OCR the strip right of the box as one line (`--psm 7`), with and without strikethrough removal, and keep the higher-confidence read.
3. **OCR**: `tesseract -l tha+eng --oem 1 --psm 3` with **TSV output** (words + boxes + confidence).
   - Tesseract splits Thai into clusters (`สั ญ ญ า`). Rebuild lines by **box gap**: insert a space only where the gap is > 0.45 × the line's median word height between two Thai clusters, or > 0.2 × otherwise. The threshold sits in the measured valley of the gap distribution (`dbresearch.ocr_layout`).
   - Normalise (§5).
   - Drop lines with mean confidence < 50 (watermark/seal noise).
   - Store page text in `document_pages`.
   - Checkbox glyphs OCR as junk (`CD`, `M`, `[ ]`), so labels never rely on them.
4. **Sectioning**: classify **each page by its heading** (template `match_rules` on the top third of the page), and use the attachment marker only as a hint. Marker regex: `เอกสารแนบ\s*(หมายเลข)?\s*(ที่)?\s*([0-9๐-๙]+)`. The real scan shows it as a boxed label, as underlined text, and **even on the main contract page** (`เอกสารแนบ 1` on the contract itself), so a marker alone doesn't start a new section. Consecutive pages with the same classification form one section. Pages that match nothing join the previous section.
5. **Template match per section**: score each active template's `match_rules` against the section text. The best one above its minimum score is assigned. The template may imply `kind` / `funding_type`.
6. **Field extraction**. **Labels are matched at the start of a line** (numbering stripped) with fuzzy ratio **≥ 88** over a window of label length ± 2. Measured: real labels 88–100, false hits ≤ 84 (mid-sentence `โครงการวิจัย` must not match `ชื่อโครงการวิจัย`). OCR misreads single characters (`ชื่อ` → `ขือ`, `บาท` → `vin`), so exact matching fails. Values inside sentences use tolerant regexes, e.g. fiscal year `ประจำปี.{0,25}?(25\d\d)` because `พ.ศ.` comes out as `พ . ศ .` or `พ fl.`. Each field rule lists **label variants** and, for each, a layout:
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
   - contract no. differs between pages
   - contract no. already exists on a live document → suggest *new version* instead
   - **more than one contract no. in one PDF** → warn *"pages show different contract numbers"* (a real PDF is always one contract, so this means a wrong upload or an OCR misread; no auto-split)
   - more than one box checked in a single-choice group (`ระบุ…เพียงข้อเดียว`)
   - research-team shares don't add up to 100 %
   - installment amounts ≠ percent × total, or don't sum to the total (once typed)
   - required field missing
9. Write `document_sections` and `extracted_fields`, set `status = needs_review`.

### Contract number
Format: `R` + B.E. year + faculty letter + running number.

| Example | Year | Letter | Faculty |
|---|---|---|---|
| `R2568E001` | 2568 (FY 2025) | `E` | engineering (funding type comes from the title block, not the letter) |

Parse with `R(\d{4})([A-Z])(\d+)`, after normalising Thai digits and fixing OCR mix-ups inside the digit groups (`B`→`8`, `S`→`5`, `O`→`0`, `I`/`l`→`1`: `R256BE001` → `R2568E001`). The year cross-checks `fiscal_year`. The letter is the faculty and is kept as read.

**Running number:** counts up separately for each year + series (faculty). `R2568E001` is engineering's first contract of 2568. (This is the department's understanding; confirm it against more samples.) The system only **stores** numbers issued by the department; it never generates them. What it's used for:
- **Sorting**: order lists by `(ref_year_be, ref_series, ref_seq)` so `E002` comes before `E010`, not by the raw text.
- **Duplicate upload**: if the extracted number matches a live document, the review screen offers *"add as a new version of R2568A001"* instead of creating a duplicate. The partial unique index enforces it.
- **Missing numbers report** (ADMIN): for each year + series, list the gaps between 1 and the highest `ref_seq` (e.g. 2568 engineering: E004, E007 missing). Shows which contracts haven't been archived yet.
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

### Findings from the 2568 round-1 contracts (13 PDFs, 17–34 pages, 2026-11-02, confidential)

All internal (`จากงบประมาณรายได้คณะวิศวกรรมศาสตร์`), scanned at office quality. Measured by replaying saved OCR
through the rules (`spikes/` style, nothing stored). After tuning: contract no., title, fiscal year, period
and funding type right in **13/13**, signing date 12/13, installments 13/13, team block 11/13.

| Topic | What the scans show | Rule |
|---|---|---|
| Stamp noise | Lines like `a i i a a 37` between `เมื่อวันที่20` and `มกราคม 2568` | A body line without a word of 4+ letters is dropped (`thai.is_noise`) |
| Contract no. | `R256BE001`, single pages `E002` for `E012` | Repair B/S/O/I inside digit groups; a footer value is a *conflict* only on 2+ pages and not one character off the winner |
| Title | Printed in the contract (`โครงการ :`), the budget sheet and the proposal form; one budget sheet carried **another project's title** | Pick the title the other sources agree with (fuzzy support), not the highest single confidence; stop wrapping at `สัญญานี้ทำขึ้น` |
| Grantee | `… ฝ่ายหนึ่ง กับ <rank> ดร.<name> ซึ่งต่อไปในสัญญานี้เรียกว่า “ผู้รับทุน”` | Sentence rule; `ตร.`/`คร.`/`os.` → `ดร.`, spelled-out ranks → `ผศ.`/`รศ.` |
| Team block | `ชื่อ- สกุล` OCRs as `ชื่อ- ana`; surnames on dotted lines may read as Latin junk | Anchor on `หน่วยงาน` + `บทบาทในโครงการ`; a cut-off name merges with the grantee's full name |
| English names | CV part: `(ภาษาอังกฤษ) Mr. / Miss / Mrs: <name>` under the Thai name | `names_en` rule → `people.name_en` |
| Installments | `งวดที่ N จำนวน X บาท` / `(ร้อยละ P) <condition>`; deadline in `หมายเหตุ: ไม่เกินวันที่ …`; in some PDFs the amount sits in its own column | `installments` rule → **suggested** `budget_lines` (user confirms); missing amount = percent × total |
| Checkboxes | `ประยุกต์`, `มนุษยศาสตร์และสังคมศาสตร์` and 12 NRCT disciplines on the form but not in the seed | Seeded; an unmatched tick in a known group is offered as a new option of that group |

### Closing papers (ปิดโครงการ, 13 PDFs)

A closing memo (`บันทึกข้อความ`, `เรื่อง ขอปิดโครงการวิจัย…`) states the memo no. (`ที่ อว 0000.00/123`), date, project title,
amount, PI and sometimes the contract no.; a faculty-meeting resolution gives `ครั้งที่ 9/2568 เมื่อวันที่ …` and the
agenda item. The approval itself is handwritten. `dbresearch.autofill.closure` reads these as suggestions for the closing
form, and the document page warns when a closing paper's title doesn't match the contract (wrong file attached).

### Proposal-development grants (ทุนพัฒนาข้อเสนอ, Phase 7 step 1, 2026-11-09)

124 scanned PDFs (1,206 pages, 2566–2569) + the research office's spreadsheet (74 rows). OCR of the first
4 pages per file on the server (`spikes/proposal_dev_ocr.py`, ~30 min with 3 workers), analysis from that
cache (`spikes/proposal_dev_report.py`, counts only unless `--detail`). Results:

- **Paper type from the text** agrees with the office's file name in **116/124**. The `เรื่อง` line is
  garbled in about half the scans, so the memo body decides too (`ขออนุมัติยกเลิก…`, `…ขอส่งข้อเสนอ…
  เรียบร้อยแล้ว`, `หมวดค่าใช้จ่าย`, `เปลี่ยนแปลงหัวข้อ/ชื่อ`). Misses: 2 cancellations and 1 change read as
  requests, 1 title-change+closing memo, and the programme papers (Research Hangout, meeting resolutions).
- **Requests (73)**: researcher 70, department 70, title 70, fiscal year 68, KPI target 67, period 64,
  amount 64, funding source 73 (all `รายได้คณะ`). **Closings (30)**: title 29, researcher 28; amount 20,
  period 17. The KPI *result* of a closing isn't read yet (wording varies; next step).
- OCR quirks to handle: `เรื่อง` read as `เรือง`/`เร่ือง`; the memo-no. line (`อว 0603.09.02/674`) has no
  long word, so the noise filter drops it (read memo no. from unfiltered lines; still only ~15 % found,
  digits after `/` are often handwritten).
- **Matching to the spreadsheet**: 107/114 project papers match a row with title similarity ≥ 90;
  69/74 rows have at least one paper. Title wins over name: one researcher often has a grant every year.
- **Spreadsheet vs folder**: some rows say ปิดทุนแล้ว / ยกเลิก but no such paper matched (4 of 31) —
  either the paper is missing from the folder or it is filed under another year (cancellations of a 2566
  grant filed in 2567). 4 byte-identical duplicate files; closings sometimes sit in a later year's folder.
  → Import must group by content (title + researcher + year), skip duplicates by hash, and leave every
  grouping for a person to confirm.

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

### Spike results (2026-10-28, server, Tesseract 5.5.0)

| Check | Real scan (5 pages) | Mock (3 pages) |
|---|---|---|
| OCR confidence / time per page | 86–94 % / 1.8–4.5 s | 86–94 % / 0.4–1.0 s |
| Expected labels found (line-start fuzzy ≥ 88) | all, 0 false | all except `(ภาษาไทย)` on the mock |
| Values (contract no., amounts, Thai dates, fiscal year) | all found | all found |
| Checkboxes found / false boxes | 8 / 0 | 9 / 0 |
| Checked state correct | 8 / 8 (fill 0.27 vs 0.00) | 9 / 9 (fill 0.21–0.24 vs 0.00) |
| Box → group + category | 8 / 8 (scores 91–100) | 9 / 9 (score 100) |

Scripts: `spikes/ocr_probe.py`, `spikes/checkbox_probe.py` (run in the worker container; output text stays on tmpfs).

### Python libraries
`pypdfium2` (render), `pytesseract` (+ `tesseract-ocr-tha` in the image), `opencv-python-headless`, `rapidfuzz`, `numpy`. `pythainlp` is only needed for `thaiword_to_num` (amount-in-words check).

---

## 7. API sketch

Implemented (Phase 2). Every API path starts with **`/api`** (all other paths belong to the web
app, see §10). Interactive docs: `/api/docs`. `/health` also answers at the root for ops. Every
state-changing request needs the header `X-Requested-With: dbresearch` (CSRF guard).
Paths below are relative to `/api`.

```
Auth       POST /auth/login · POST /auth/logout · POST /auth/logout-all · GET /auth/me
Documents  POST /documents (multipart upload) · GET /documents (search: q, kind[], funding_type[],
           fiscal_year[], status[], category[], tag[], person, ref_year_be, ref_series, mine, sort,
           page, page_size, with_facets; several values in one filter = any of them; each facet
           group is counted without its own filter) · GET /documents/{id} · DELETE /documents/{id} (trash)
           GET /documents/zip?id=…&id=… (≤ 100, current versions as one zip, streamed; deleted ones left out)
           GET /documents/trash (my bin) · POST /documents/trash {ids} · POST /documents/trash/restore {ids}
           POST /documents/{id}/versions · GET /documents/{id}/file?version=&closure=&inline=
           POST /documents/{id}/closure-files (closing paper) · POST /documents/{id}/close {closed_on,
           closure_ref, closure_note} · POST /documents/{id}/reopen · GET /documents?project=open|closed
           GET /documents/{id}/autofill · PUT /documents/{id}/metadata · POST /documents/{id}/reprocess
Pickers    GET /categories · POST /categories {group_id, name_th} (any user) · GET /people?q=
Reports    GET /reports/overview · /reports/charts · /reports/missing-numbers (every user; system
           figures such as users, storage, all links and the whole trash only for admins)
Shares     POST /documents/{id}/shares · GET /shares · GET /shares/{id}/log
           DELETE /shares/{id} · POST /shares/{id}/password
Guest      GET /s/{token} · POST /s/{token}/unlock · GET /s/{token}/file?download=
           (the link people open is the web page /s/{token}; its grant cookie is scoped to /api/s/{token})
Admin      /admin/users (+ PATCH, /password, /sessions, POST /sessions/revoke) · /admin/security · /admin/shares?state=active|all|… · /admin/trash (restore, purge)
           /admin/audit · /admin/settings · /admin/category-groups · /admin/categories
           /admin/templates
```

---

## 8. Build order

1. ~~**Spike: Thai search.**~~ Done: ICU `th-TH` + pg_trgm, space-insensitive `search_text`. No PyThaiNLP fallback needed (§5).
2. ~~**Spike: OCR + checkboxes.**~~ Done: see §6 spike results.
3–10. ~~Stack, auth, encrypted storage, auto-fill worker + review, search, share links,
   admin, backups~~ Done 2026-10-28 (Phase 2, 87 tests on the server). Operations: `docs/OPERATIONS.md`.
11. ~~Frontend~~ Phase 3: Svelte web app served by the API (§10).

## 9. Open questions

- **For the IT team**: confirm the college NAS as backup target (assumed) and how to reach it (SFTP / SMB / S3); who holds the KEK copies.
- **For the IT team**: the university login API spec (URL, request/response fields, how the account type is named, API key or not). Decided already: teachers only, auto-created as `user` on first login (§1).
- **Teachers outside the department** *(decided 2026-11-09, not built yet)*: the API admits every teacher of the university, and every user can read every document, so a first login must **not** open access directly. It creates a *pending* request; ADMIN approves or rejects it (audited) and only then can the teacher log in. If the API returns the teacher's department/faculty, teachers of our own department are approved automatically and others still go to the queue. **Ask IT whether the API returns the department.** Until the queue is built, `UNIVERSITY_AUTO_CREATE=false` (ADMIN adds each teacher first) is the safe setting.

---

## 10. Web app (Phase 3)

Mocks of the agreed direction: `docs/ui/` (palette, layout + upload, search filters).

| Topic | Decision |
|---|---|
| Stack | **Svelte 5 + Vite**, plain JS, in `web/`. Built in the Docker image (node stage) and served by FastAPI from `/app/web/dist`: hashed `/assets/*`, every other non-`/api` path gets `index.html` (`no-cache`, strict CSP: same-origin only). No extra container. |
| Fonts | Kanit (headings) + IBM Plex Sans Thai (body), self-hosted via `@fontsource` (no CDN at runtime). |
| Colors | Faculty maroon `#8B1538` as primary (~10 % of the screen), warm off-white base, gold highlight (fills only, never text), yellow search-hit mark, orange-red for errors (never confused with maroon). Light + dark (follows the device; user can pick). |
| Layout | PC/tablet ≥ 768 px: header with tabs (เอกสาร · รอตรวจสอบ · ภาพรวม · ลิงก์แชร์ · ผู้ดูแลระบบ), search box (`/` focuses), upload button; the account menu links to ถังขยะของฉัน. Only Admin has a side menu. Phone: bottom bar with a raised **search** button in the center; upload sits in the top bar; ภาพรวม and ถังขยะของฉัน are on the บัญชี tab. |
| Select mode | "เลือก" on the results toolbar. Rows toggle instead of opening, a tick sits on the file tile, picks survive new searches (max 100). Action bar: count, select shown, download (one file = PDF, more = zip built by the server), move to trash (only the ones you may delete; confirm lists them; the toast offers undo). PC: floating bar at the bottom; phone: it takes the bottom nav's place. Esc leaves. |
| Upload | One window (dialog on PC, bottom sheet on phone) or drop files anywhere. Several PDFs, 2 in parallel, per-file result (uploaded / duplicate → link / rejected). Closing keeps uploading (header pill). Then *review now* or *review later* (documents wait in รอตรวจสอบ, searchable meanwhile). |
| Search | PC: filter column + removable chips + sort; filters live in the URL. Phone: quick chips + filter bottom sheet with a live "แสดง N รายการ" count. Zero-count options are disabled. |
| Close / archive | Document page card "การปิดโครงการ": attach closing papers, close with date + memo/resolution no. (pre-filled from what the system read), reopen. The list shows active projects; the "โครงการ" switch (ดำเนินการอยู่ · ปิดแล้ว · ทั้งหมด) opens the archive, and a search says how many matches sit in the archive. |
| People / budget rows | Laid out by the card's own width (container queries): one table row under a shared header when wide, a stacked mini-card when narrow, so the PDF can sit beside the form. Budget is split into งวดเงิน and รายการค่าใช้จ่าย with a running total checked against งบประมาณรวม. |
| Review | Pre-filled from auto-fill on the first review; afterwards the saved values, with the system's readings as clickable hints. Warnings never block. PDF beside the form on wide screens. Dates typed as `วว/ดด/ปปปป` in พ.ศ., stored Gregorian. |
| Guest page | `/s/{token}`: one card, full-width download button, password form when needed. No login. |
| Motion | Only transform/opacity, 150 ms (hover/press) and 220 ms (windows, sheets, tabs), one ease-out curve; skeleton rows, no layout shift, no backdrop blur; `prefers-reduced-motion` turns it off. |
| Dev | `cd web && npm run dev` proxies `/api` to `localhost:8120` (SSH tunnel). |

---

## 11. Proposal-development grants (ทุนพัฒนาข้อเสนอโครงการวิจัย, Phase 7)

Small faculty-income grants (≤ 20,000 บาท) that pay a teacher to write a proposal for an outside grant.
Papers and findings: §6 "Proposal-development grants"; plan: `plan.md` Phase 7.

| Topic | Decision |
|---|---|
| Storage | Same engine as contracts: a `documents` row with `kind = 'proposal_dev'` (encrypted versions, OCR, search, shares, trash, audit) + `proposal_projects` for its own fields. Its own web section, separate from สัญญาทุนวิจัย. |
| One project, many papers | The request memo is the main file. Closing papers are `closure` versions; cancellation and change memos are `paper` versions. Each is a `project_events` row (type, memo date, memo no., details such as old/new title). |
| Status | Derived: cancelled (`cancelled_at`) / closed = success (`closed_at`) / active; **overdue** = active and past `kpi_due`. A title change keeps the old title in its event (searchable). |
| Funding | `funding_source` (filter: งบประมาณ FF, รายได้ ม.นเรศวร, รายได้คณะ, แหล่งทุนภายนอก) on every document; `funding_type` follows it (FF = external). All papers so far: รายได้คณะ. |
| KPI and outcome | `kpi_target` + `kpi_due` from the request; `kpi_result` + spending from the closing. Optional outcome: submitted / won / not won, funder, link to the contract it won. |
| Who enters | Research office staff (plain `user` accounts). Any user may upload; edit/delete stays uploader or ADMIN. |
| Programme papers | Calls for proposals, the yearly programme approval, Research Hangout, meeting resolutions: `kind = 'other'` per fiscal year, a separate part, no funding type needed. |
