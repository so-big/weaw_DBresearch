# plan.md — Task Tracker

Design reference: [docs/DESIGN.md](docs/DESIGN.md). Status keys: `[ ]` todo · `[~]` in progress · `[x]` done · `[?]` needs decision.

## Workflow

```
 this machine (edit, light checks)  ──git push──▶  GitHub someact/DBresearch (private)  ──git pull──▶  server cs31@100.104.87.92
                                                     version history + code store               docker compose up · tests · demo
```

1. Write code on this machine. Run only light checks here (ruff, quick unit tests). This machine is too weak for the full stack.
2. Commit + push to `main` on https://github.com/someact/DBresearch.git.
3. Deploy on the server: `ssh cs31@100.104.87.92 'cd ~/dbresearch && git pull && docker compose up -d --build'`.
4. Run heavy tests on the server (Postgres, OCR): `docker compose exec api uv run pytest`.
5. Secrets (`.env`, KEK file) live **only on the server** in `~/dbresearch/.env` / `~/dbresearch/secrets/`, never in git.

## Environment facts (checked 2026-10-27)

| | |
|---|---|
| Repo | `someact/DBresearch`, private, default branch `main`. `gh` logged in as `someact` with push rights. |
| Server | Arch Linux, 20 cores, 15 GiB RAM, `/home` 136 GB free (Docker root is `/home/docker`). |
| Server tools | Docker 29.8 + Compose 5.6, user `cs31` in the `docker` group. No uv/tesseract on the host (they go inside images). |
| Network | Reached over Tailscale (`archlinux`, via relay "sin", so large transfers are slow). The server can reach GitHub. |
| Shared server | Also runs carewai, flood-x, promptjang, bus-system. Ports taken: 22, 443, 8443, 3080, 3090, 3100, 8110, 11434. |
| Git on server | Pattern: one read-only deploy key per project + `~/.ssh/config` host alias (`git@github-<project>:…`). |
| Thai search spike | `postgres:17` with `ICU_LOCALE 'th-TH' LOCALE 'C.UTF-8'`: pg_trgm handles Thai, and the GIN index is used for `ILIKE '%ทุนวิจัย%'`. |

## Phase 0 — Setup & verification

- [x] Design grill session → `docs/DESIGN.md`, `CLAUDE.md`, skills, ruff hook
- [x] Verify GitHub repo access (read + push permission)
- [x] Verify server SSH, Docker, resources, GitHub reachability
- [x] Spike: Thai trigram search in Postgres 17 (synthetic text)
- [x] `git init` locally, first commit, push to `main`
- [x] Server: deploy key `~/.ssh/dbresearch_deploy` + host alias `github-dbresearch`, added as **read-only** deploy key
- [x] Server: clone to `~/dbresearch`, then test the push → pull round trip

## Decisions made

- [x] Test access: **SSH tunnel**. The API binds `127.0.0.1:8120` on the server; open it locally with `ssh -N -L 8120:127.0.0.1:8120 cs31@100.104.87.92`, then browse `http://localhost:8120`.
- [x] Git: **push straight to `main`**.
- [x] One PDF = one full package with attachments (`เอกสารแนบหมายเลข N`). No separate Project table in v1 (DESIGN §1, §3).
- [x] Auto-tags from **checked** boxes, matched to ADMIN categories; unmatched → suggested tag; unchecked ignored (DESIGN §6).
- [x] Checkbox detection is tuned for typed ☑ only. Pen ticks are out of scope for v1: if a box isn't detected confidently, there's no suggestion and the user tags manually.
- [x] Contract no. = `R` + B.E. year + faculty letter + running no. (`R2568E047`, E = engineering). *(Was "E = internal / A = external"; corrected 2026-11-02, see Feedback round 1.)*
- [x] Running number counts per year + series (`R2568E001` = first internal of 2568). Used for sorting, duplicate-upload detection (unique per live doc), and an ADMIN missing-numbers report. The system stores numbers, never issues them.
- [x] External funding uses the same document format as internal → same section templates; funding type comes from the contract no.
- [x] Budget: auto-fill only `budget_total`. Line items / installments (`งวด`) are typed manually into `budget_lines`.
- [x] One PDF = **exactly one contract** (one contract no.). Different numbers within a PDF → warning only, no split.
- [x] Package = contract body + `เอกสารแนบ 1–5`. Auto-fill only from the body, att. 1 (money: total) and att. 5 (proposal: titles, checkboxes, team). Att. 2–4 are OCR'd for search only.
- [x] OCR text stored **unencrypted** in the DB: accepted (low-sensitivity; files themselves stay encrypted).
- [x] Login: the **university login API** (university ID + password, returns the account type). **Staff only** (research office USER, IT team ADMIN); teachers and other guests use share links, students never get in. Deployed on the university's server (already trusted by the API). Roles live in our DB. *(2026-11-09, replaces "IT team integrates SSO")*
- [x] Backups **kept forever** (never prune), off the server, nightly `pg_dump` + blob folder via restic, to the college NAS (assumed). **KEK backed up separately**; losing it = losing every file.
- [x] File store: **local folder + `BlobStore` interface** (MinIO discontinued 2026-04).
- [x] Sharing: **any USER** can share any document they can read; only the link's creator or an ADMIN manages it. The document's uploader sees every active link on it and may revoke any of them (2026-11-12).
- [x] kind / funding_type may be empty until review; a document can only become `ready` with both set.
- [x] If OCR fails 3 times, the document still goes to review (warning `ocr_failed`) so metadata can be typed by hand.
- [x] Production uploads: **scanner PDFs only**. Auto-fill is assistive; anything wrong or missing is typed by the user on the review screen.

## Decisions still open

- [?] **Backup target** (IT team): **assumed college NAS**; access method still unknown (`RESTIC_REPOSITORY` is configurable).
- [⏸] **Login system PAUSED (2026-11-10)**: waiting for the real university login API spec (URL, fields, account-type names, API key) or the department's user-ID server; the IT team continues it. Until then the app uses local login only. Ready for it: `HttpUniversityClient` (fill in once the spec arrives), student usernames refused up front, approval queue, test-only `UNIVERSITY_CLIENT=php_ldap_test` (IT's RealLogin.php worked against the real AD on 2026-11-10).
- [?] **Login source**: `samples/RealLogin.php` (LDAP to `ldap.nu.local`) is for testing and comparing only (it is unsafe: empty password logs anyone in). The department deployment will use a database of user IDs. Username formats are in DESIGN §9. Students can be refused by username format; staff and teachers look the same, so we still need AD groups or the database to tell them apart.
- [?] **Does the university API return the staff member's department/faculty?** Ask IT with the spec. If yes: auto-approve our department's staff, queue the rest.

## Phase 1 — Foundation ✅ done 2026-10-28

- [x] Review internal-funding sample → DESIGN §6 (sections, label variants, checkbox groups, seed categories)
- [x] Collect test samples: mock (`docs/`) + first real scan (`samples/`, internal + external, typed ☑). Real PDFs stay gitignored.
- [x] Copy samples to the server (read-only ACL for container uid 10001): `scp samples/*.pdf "docs/sample document-1.pdf" cs31@100.104.87.92:~/dbresearch/samples/`
- [x] Spike: Tesseract `tha+eng`: 86–94 % confidence; gap-based Thai joining; line-start fuzzy labels (DESIGN §6)
- [x] Spike: checkboxes: 17/17 boxes, 0 false, all states + categories correct on both samples
- [x] Thai search on real OCR text: 13/13 queries; space-insensitive `search_text`; no PyThaiNLP fallback
- [x] Project scaffold: `pyproject.toml` (uv), ruff config, FastAPI skeleton, Dockerfile (with `tesseract-ocr-tha`, poppler)
- [x] `docker-compose.yml`: postgres (ICU th-TH), api (`127.0.0.1:8120`), worker, `blobs` volume
- [x] Alembic baseline migration from DESIGN §3 + seed categories/settings (DESIGN §6); one-shot `migrate` service
- [x] pytest against a throwaway ICU th-TH Postgres on the server: up/down/up, `alembic check`, key constraints

## Phase 2 — Backend ✅ done 2026-10-28 (87 tests pass on the server)

- [x] Auth: `AuthProvider` (local argon2id, swappable for college SSO), server-side sessions, CSRF header, roles, `create-admin` CLI
- [x] Upload/download with Tink envelope encryption (per-version streaming DEK, KEK file) + versions + duplicate detection
- [x] Worker + PostgreSQL job queue + auto-fill pipeline (sections, field rules, checkboxes → categories, team, warnings) + review/metadata flow + reprocess
- [x] Search: space-insensitive text, filters, facets, snippets, sort by contract running number
- [x] Share links: TTL caps, public/password, view-only, download cap, lockout, access log; guest pages
- [x] Admin: users, all links, trash/restore/purge, audit browser, settings, categories, templates (validated), missing-numbers + overview reports
- [x] Backups: `scripts/backup.sh` (no forget), `scripts/restore-drill.sh` (passed on the demo server), `verify-storage`, `docs/OPERATIONS.md`
- [ ] **Backups to the college NAS + nightly timer**: waiting for IT (demo uses a local test repo; timer not installed)
- [ ] **KEK custody**: copy `secrets/kek.json` and `secrets/restic-password` to two places off the server (docs/OPERATIONS.md)

## Phase 3 — Frontend

- [x] Brainstorm: stack, screens (upload → review → search → share), mobile/low-end constraints, Thai typography, พ.ศ. dates
  - [x] Colors (approved): faculty maroon `#8B1538` as primary (~10% of the screen), warm off-white base, **gold** highlight (fill only, not text), yellow search-hit mark, status colors (error is orange-red, never maroon). Dark mode in v1, follows the device setting. Faculty logo: text name until the faculty approves the logo.
  - [x] Layout: PC/tablet (≥768px) = top header nav (เอกสาร · รอตรวจสอบ · ลิงก์แชร์ · ผู้ดูแลระบบ) + search + upload in the header. Only the Admin area adds a left sub-menu (many sub-pages). Search results get a left filter column (facets). Phone = bottom bar with a large raised **search** button in the center; upload sits in the header, not the bar.
  - [x] Upload: one button (or drop files anywhere) → modal with drop zone + file picker, multiple files, sent 2 at a time, per-file result (uploaded / duplicate `409` → link to the existing doc / not PDF). Closing keeps uploading (header pill). Then "review now" or "review later": docs wait in รอตรวจสอบ (`needs_review`), searchable and editable any time.
  - [x] Search filters: PC = left filter column, applies on click, removable chips + result count + sort above results, filters kept in the URL. Phone = quick chips (fiscal year, funding, needs review) under the search box + full filter bottom sheet with a live "แสดง N รายการ" button. Groups: fiscal year (พ.ศ.), funding type, status open; doc kind, admin category groups, researcher name, "mine" folded. Zero-count options greyed out.
  - [x] Backend for filters: (1) `fiscal_year`, `kind`, `funding_type` accept lists (multi-select); (2) each facet's counts leave out its own group's filter, so other options stay selectable.
  - [x] Stack: **Svelte 5 + Vite** (plain JS) in `web/`, fonts **Kanit + IBM Plex Sans Thai** self-hosted. Design summary: DESIGN §10.
  - [x] Style: simple, minimal, smooth. Animate only transform/opacity, 150ms/220ms with one ease-out curve, reserved space (no layout shift), skeleton rows, no backdrop blur, respect reduced-motion.
- [x] API moved under `/api` (docs at `/api/docs`); FastAPI serves the built web app for every other path (CSP, SPA fallback). Share links stay `/s/{token}` (web page).
- [x] Screens: login, documents search + filters (PC column / phone sheet), multi-file upload window, document page (download, view, share, new version, trash), review form (auto-fill hints, warnings, PDF beside the form), review queue, my share links, guest page, phone account tab, admin (overview + missing numbers, users, all links, trash, categories, audit, settings)
- [x] Deployed to the demo server; 92 tests pass. Headless click-through (`spikes/ui_smoke.py`) on PC + phone, light + dark: no JS errors. Found and fixed a Phase 2 bug: `/admin/audit` and share logs crashed on IP values.
- [~] Try it on a real phone (guest link, search, upload from the phone's files) and collect feedback
  - [x] Share links work on phone and PC (checked by the user 2026-11-11)
- [ ] Later: PDF preview inside the page on phones (pdf.js) if opening a new tab is not enough

## Phase 4 — Polish and public demo

- [x] Public demo at **https://dbresearch.promptjang.com** (Cloudflare Tunnel → `127.0.0.1:8120`). The college network blocks `promptjang.com`; testers there use a VPN. Visitor IP from `CF-Connecting-IP`, HTTPS-only cookies, login limit (5 per username / 15 min).
- [x] Thai error messages for known API errors; drag & drop accepts every way desktops hand over files
- [x] Upload window: cancel any file (waiting, uploading, or undo a finished upload → trash)
- [x] Overview with charts: status meter, documents + budget per fiscal year, uploads per month, views/downloads per day, top categories, contract-number coverage grid (each with a table view). `GET /api/admin/reports/charts`
- [x] Visual refresh: maroon masthead with search + quick figures, funding-tinted file tiles, split login, guest band
- [x] Select mode on the documents list: pick several → download as one zip (server decrypts + compresses on the fly) or move to the trash (all or none, with undo)
- [x] Overview opened to every user (tab ภาพรวม; `GET /api/reports/*`); admin-only figures stay hidden from users
- [x] ถังขยะของฉัน: each user sees what they uploaded or deleted and can restore their own deletes; admins still purge
- [ ] Collect tester feedback on the live site and fix what feels off

## Phase 5 — Feedback round 1 (2026-11-02)

- [x] Contract-number letter = **faculty** (E = engineering), not funding type. Funding type now comes from the title block: `ระหว่าง … กับ …` = external, `จากงบประมาณ…` of one unit = internal (DESIGN §1)
- [x] Auto-fill tuned on 13 real contracts (ทุนวิจัย ปี 68 รอบ 1): noise lines, contract-no. repair, title by agreement, grantee from the parties clause, team block anchored on หน่วยงาน/บทบาท, English names, installments suggested (DESIGN §6). Data migration `c5e1f0a7d392` (+ form options)
- [x] Review form: any user adds a category option inline (+ ticked-but-unknown options offered in their group)
- [x] Review form: ผู้เกี่ยวข้อง and รายการงบประมาณ rows fit the card (container queries); budget split into งวดเงิน / รายการค่าใช้จ่าย with totals
- [x] Close a project (ปิดโครงการ): closing papers attached to the contract (encrypted, OCR'd, readings pre-fill the form), archive filter, reopen (migration `a3d9c2e71b54`)
- [x] Deployed; 135 tests pass on the server; screens checked on PC, tablet and phone (no JS errors)

## Phase 6 — Login security (2026-11-09)

- [x] Idle timeout (60 min) on top of the 12 h limit; re-login ends the browser's old session
- [x] At most 5 sessions per user; log out on every device (user), device list + end sessions (admin)
- [x] HSTS when `COOKIE_SECURE=true`, `no-store` on `/api`, Permissions-Policy; startup + admin warning for unsafe settings
- [x] Login audit: reason for each failure, user agent, blocked attempts, API outages; admin 24 h security summary
- [x] `audit_events` append-only by trigger (migration `e4b7a1c9d025`)
- [x] University login provider (teachers only, auto-create or pre-add by email/ID), with a placeholder HTTP client
- [ ] ⏸ Paused: fill in the real university API (or the department's user-ID server) once it arrives; test it on the university's server
- [x] **Approval queue** (decided 2026-11-09): a teacher's first login creates a *pending* request, not an account. They see "waiting for admin approval"; ADMIN approves/rejects on the Users page (audited). Replaces auto-create as the default, so teachers from other departments can't get in directly. If the API gives the department, auto-approve our own department (`UNIVERSITY_AUTO_APPROVE_DEPARTMENTS`). Built 2026-11-11: status `pending` (migration `b8e3f6a2c4d1`), `GET /api/admin/users/requests`, approve/reject (audited), count on the admin ผู้ใช้ menu, login page notice. `UNIVERSITY_AUTO_CREATE` removed.

## Phase 7 — ทุนพัฒนาข้อเสนอโครงการวิจัย (proposal-development grants) — PLAN, not started

Source: USB folder `ขออนุมัติทุนพัฒนาข้อเสนอโครงการวิจัย 2566-ปัจจุบัน` (confidential, never in git) +
`ข้อมูลทุนพัฒนาข้อเสนอโครงการวิจัย งปม.2566-2569.xlsx` (74 rows: researcher, title, fiscal year, remark
ปิดทุนแล้ว / ยกเลิก / ชื่อเดิม / เปลี่ยนแปลงชื่อเรื่อง). The 2569 rows in the sheet are incomplete (3 rows, 33 files).

### What the papers are (checked 2026-11-09 on samples; all scans, no text layer)
- 119 PDFs in `งปม.2566–2569`, 1–98 pages. By file name: ~74 requests, ~30 closings, 7 cancellations,
  3 changes (title / budget category), 5 programme papers. Plus 5 loose files at the top
  (Research Hangout 2567, a faculty-meeting resolution) that are a different programme.
- Every paper is a faculty memo (`บันทึกข้อความ`): `ที่ อว 0603.09…/NNN`, date, `เรื่อง …`, researcher
  + department (`สังกัดภาควิชา…`), project title, amount (≤ 20,000 บาท), period, signatures.
  The file-name prefix (e.g. `10221`) is the faculty's received no. stamped top-left.
- **Request** `ขออนุมัติทุนพัฒนาข้อเสนอโครงการวิจัย ประจำปีงบประมาณ พ.ศ. …`: title, amount, period
  (e.g. 15 ธ.ค. 2568 – 30 ก.ย. 2569), **KPI**: deliver a research proposal for an outside grant +
  Impact Pathway by a due date. Funding line: `งบประมาณเงินรายได้คณะวิศวกรรมศาสตร์ … กองทุนวิจัย`.
  Attachments: research-area page (`กรอบงานวิจัย`, e.g. เทคโนโลยีพลังงาน), budget lines.
- **Closing** `ขออนุมัติปิดโครงการ ทุนพัฒนาข้อเสนอโครงการวิจัย`: the KPI result (e.g. "ข้อเสนอสำหรับ
  การขอทุนวิจัยภายนอก พร้อมสัญญาทุนวิจัย"), planned vs actual spending and remainder, and the
  developed proposal itself (most of the pages) + a copy of the original approval.
- **Cancellation** `ขออนุมัติยกเลิกทุนพัฒนาข้อเสนอโครงการวิจัย`: reason in free text.
- **Changes** `ขออนุมัติเปลี่ยนแปลงหัวข้อ…` (new title, sometimes closes in the same memo) and
  `ขออนุมัติเปลี่ยนแปลงหมวดค่าใช้จ่าย…` (budget categories moved).
- **Programme papers** (per fiscal year, not per project): call for proposals (`เวียนแจ้งเปิดรับ…`)
  and the faculty's yearly approval of the whole programme (e.g. 1,000,000 บาท for 2567).
- Data quirks: duplicates (`268 … 2567.pdf` / `…2567..pdf`, `10483` ×2, `5035` + `(แก้ไข)`),
  closings filed in a later year's folder, typos in names (ปิดทึน). Grouping must use content, not folders.

### Proposed design (to confirm)
- **Same engine, separate section.** Reuse documents, encrypted versions, OCR, search, share links,
  trash and audit. Add `kind = proposal_dev` beside `contract` / `grant`. The web app gets its own
  top-level section "ทุนพัฒนาข้อเสนอ" (own list, filters, detail page, overview) separate from
  "สัญญาทุนวิจัย".
- **One record per project, a timeline of papers.** The request is the main file. Closing, cancelling
  and change memos attach to the same project as events (`project_events`: type, memo no., date,
  details, the paper). Status: กำลังดำเนินการ → ปิดทุนแล้ว (success) / ยกเลิก; overdue when past the
  KPI due date and not closed. A title change keeps the old title (searchable).
- **New fields**: researcher + department, amount, period, research area (กรอบงานวิจัย),
  KPI target + due date, KPI result, actual spent / remainder, the outside funder the proposal went
  to, and an optional link to the real research contract it led to (already in this system).
- **Funding source** as one field shared by every section: `FF` (Fundamental Fund), `รายได้ ม.นเรศวร`,
  `รายได้คณะ`, `แหล่งทุนภายนอก` (+ funder name). Internal/external is derived from it.
  All papers in this folder are `รายได้คณะ`.
- **Programme papers** stored per fiscal year as "เอกสารประกอบโครงการ" (not projects).

### Steps
- [x] 0. Confirm the open questions (2026-11-09)
- [x] 1. Copied to the server (`samples/proposal_dev/`), OCR'd (first 4 pages, 1,206 pages total), classified
      and compared with the spreadsheet: type 116/124, request fields ~90 %, 107/114 papers match a sheet
      row (DESIGN §6 "Proposal-development grants"). 2026-11-09
- [x] 2. Schema + migration `f2c8d4a1b7e3`: `kind proposal_dev` / `other`, `funding_source` (+ check vs funding_type), `cancelled_*`, `proposal_projects`, `project_events`, `budget_lines.actual_amount`, version purpose `paper` (DESIGN §3, §11). 2026-11-10
- [x] 3. Memo reader `autofill/proposal.py` (code, not DB templates: prose memos, see DESIGN §6), wired into
      the worker for `proposal_dev` / `other` documents. Tuned on 2569, checked on 2566–2568: type 117/124,
      title 94/100 and researcher 94/100 vs the spreadsheet. Synthetic test memos in `tests/test_proposal_reader.py`. 2026-11-10
- [x] 4. Bulk importer `dbresearch.importer plan|apply` (DESIGN §11). Plan on the real folder: 72 projects
      (28 closed, 7 cancelled), 9 programme papers, 4 duplicates, 4 flagged; spreadsheet rows 16, 24, 27, 34, 61
      say closed but no closing paper is in the folder (ask the research office). 2026-11-10
- [ ] 4b. Run `apply` on real data **after step 5** (decided 2026-11-10); where real data may live is still open (the public demo holds no real scans so far)
- [x] 5. Web section ทุนพัฒนาข้อเสนอ: list + filters, grant page with timeline and close / cancel / change
      actions, review form, upload choice, overview chart; API sections, filters, timeline, cancel, report
      (DESIGN §11). Demo has 4 fake "[ตัวอย่าง]" grants (`spikes/demo_proposals.py`); UI smoke on PC/phone,
      light/dark: no JS errors. 2026-11-10
- [ ] 6. Import the real data on the demo, review together, then feedback round

### Decided (2026-11-09)
- **Funding source filter** with exactly: `งบประมาณ FF`, `รายได้ ม.นเรศวร`, `รายได้คณะ`, `แหล่งทุนภายนอก`
  (all sections). ~~FF counts as external~~ → **FF counts as internal** (changed 2026-11-11) when internal/external is derived.
- Research Hangout files and the faculty-meeting resolution: a **separate part** for now
  ("เอกสารอื่น ๆ" per fiscal year); ask the research office later what they are (maybe a summary of all funding).
- **The research office enters** proposal-development papers (teachers just sign). Research office staff
  are employees with a university ID → plain **`user`** accounts. **ADMIN = IT only.**
  No section-level upload restriction: any user may upload (as for contracts); edit/delete stays
  uploader-or-ADMIN; every user reads everything.
- ~~University login must also admit staff/employee accounts, not only teachers~~ → **corrected 2026-11-11:
  only staff/employees log in; teachers get no account** (they get share links to view and print their papers).
  `UNIVERSITY_ALLOWED_TYPES` defaults to `staff`; exact type names from the API spec. Admin approval still applies.
- **Outcome tracking** (proposed, optional at closing): proposal submitted → won / not won, funder name,
  link to the research contract in this system when won. Report: how many seed grants became outside grants.

### Open questions
- [?] What are the Research Hangout files and the faculty-meeting resolution? (ask the research office)

## Security review (2026-11-11)

Checked: login + sessions, share links, encryption, edit rights, uploads, XSS/CSP, SQL, Docker, logs,
dependencies (npm audit + pip-audit: 0 known vulnerabilities).
- [x] **OCR page images were written to disk**: Tesseract puts each rendered page in the temp folder, and the
      worker's `/tmp` was disk, not tmpfs (breaks the "no plaintext on disk" rule). Fixed: worker `TMPDIR=/tmp/work`.
      Pages OCR'd before the fix were deleted after use, but may linger in free disk blocks.
- [x] **Share tokens in the access log** (`docker compose logs api` showed full `/s/<token>` URLs). Fixed: redacted.
- [x] Containers get only `kek.json` (not the restic or demo passwords); all Linux capabilities dropped, no-new-privileges
- [x] Guest unlock cookie: `Secure` in production; a new link password ends open unlocks at once
- [x] **View-only links still handed over the whole PDF** (the viewer can save/print). Decided 2026-11-11: ease of
      use wins (teachers print their own papers). Every open, view or download, now counts toward the link's limit;
      the "view only" checkbox is gone from the share window (old view-only links still hide the button).
      Later, if needed: stamp a light watermark ("สำเนาสำหรับ … วันที่ …") on shared PDFs for traceability.
- [?] Hide `/api/docs` and the `/health` details from the public internet in production (low risk)
- [ ] Biggest remaining risks are availability, not attackers: KEK custody and backups (Phase 2 items above)

## Phase 8 — New front-end design (on hold, added 2026-11-11)

- [?] **Decide again when the remaining tasks are almost done**: whether to redesign the web app, and how far
  (new look only, or new layout and screens too). Not started; no design work until then.
- [ ] When it starts: brainstorm the direction, make mocks (`docs/ui/`), agree on them, then update DESIGN §10
  (current UI rules) and CLAUDE.md before building

## Phase 9 — Review round 2026-11-10: security, bugs, QoL, features (9A–9C + F1 done 2026-11-12; 224 tests pass on the server)

Found by reading the code (auth, shares, documents, admin, search, worker, web app, compose,
backup script). "Confirmed" = traced in the code; "check" = needs a test on a real device/server.

### 9A. Security fixes (do first, all small)
- [x] **S1 Password links show the title before the password** (confirmed): `GET /api/s/{token}`
      returns title, file name, size and pages to anyone holding the link; `Guest.svelte` shows the
      title on the password screen. Return only `requires_password` + `expires_at` until unlocked.
- [x] **S2 Uploads are read before the login check** (confirmed: FastAPI parses the form before
      dependencies). Anyone can send 100 MB bodies to `POST /api/documents` and fill the API's 1 GB
      in-memory `/tmp` before getting 401. Reject unauthenticated multipart POSTs in a middleware
      (cookie → valid session) before the body is read; keep the Content-Length check.
- [~] **S3 Unauthenticated requests write rows forever** (code half done 2026-11-12: one `login_blocked` row per lock; **still to do by hand: the Cloudflare rate-limit rule**): every blocked login writes an
      `auth.login_blocked` audit row (append-only, never cleaned) and every guest page load writes a
      share log row. Add a Cloudflare rate-limit rule on `/api/auth/login` and `/api/s/*`, and
      write one `login_blocked` row per lock window instead of one per request.
- [x] **S4 Anyone can lock a staff account** (done 2026-11-12: failures count per username + IP; ADMIN unlocks a username or IP on the audit page, `POST /api/admin/security/unlock`) by typing 5 wrong passwords for that username
      (15 min, repeatable). Decide: count username failures per IP too, or add a short delay
      instead of a hard lock, or put Cloudflare Access in front (OPERATIONS.md option).
- [x] **S5 Opened PDFs run on our own site**: add `Content-Security-Policy: sandbox` to file
      responses (`stream_version`), so a crafted PDF opened inline can't act as our site.
- [x] **S6 Container hardening**: `migrate` lacks `cap_drop`/`no-new-privileges`; the worker mounts
      `./samples` (confidential scans) in the production compose file → move to a dev override.
- [x] **S7 Dependency checks**: no CI. Add a GitHub Action: ruff, unit tests, `npm run build`,
      `pip-audit`, `npm audit --omit=dev`.
- (existing) KEK custody, NAS backups (Phase 2), hide `/api/docs` + `/health` details (Security review).

### 9B. Bugs
- [x] **B1 Renaming a category leaves old search text** (confirmed): `search_text` includes category
      names but `PATCH /admin/categories/{id}` (name/aliases) doesn't rebuild it → the new name
      finds nothing until each document is re-saved. Rebuild affected documents (a job).
- [x] **B2 OCR failure → document not searchable** (confirmed): `give_up` never builds
      `search_text`, so a failed-OCR upload can't be found even by its file name until reviewed.
- [x] **B3 Duplicates via the trash** (confirmed): the duplicate check ignores trashed documents, so
      re-uploading a trashed file makes a second document; restoring the first then gives two.
      Point to the trashed copy ("restore it instead?").
- [x] **B4 Duplicate race** (confirmed): no unique index on `sha256_plain`; the upload window sends
      2 files at once, so the same file dropped twice can be stored twice. Lock or unique index.
- [x] **B5 Title highlight ignores spaces/case** (confirmed): `Documents.svelte` highlights titles with
      plain `includes(q)`, unlike the space-insensitive search, so most title hits aren't marked.
- [x] **B6 Slow result list** (confirmed by reading): `search.snippet` loads every page's text of
      each result in Python (up to 100 results × hundreds of pages for proposal bundles). Find the
      match in SQL, or only for the first page of results.
- [x] **B7 Docs drift** (2026-11-12): DESIGN §1 still lists share-link "view-only mode" (dropped 2026-11-11);
      plan.md has two open items for the university API spec (lines "Decisions still open").
- [ ] **B8 (check, user tests on a phone)** "Every open counts": test on Android/iOS that opening or downloading once
      uses only one count (some mobile viewers fetch twice).

### 9C. QoL fixes to what exists
- [x] **Q1 Don't lose review work**: a 60-min idle timeout ends the session while someone types a
      long review form (typing makes no requests); the save then fails and redirects to login.
      Keep a local draft of the form, warn ~5 min before the session ends, and refresh it on typing.
- [x] **Q2 Unsaved-changes warning** when leaving the review form / proposal review (none today).
- [x] **Q3 Share dialog**: "copy link + password as a message" (ready-to-paste Thai text for
      LINE/email, password on its own line), a QR code for handing a link over on a phone, and
      the version pin the API already supports.
- [x] **Q4 Owner sees every link on their document**: the uploader can't see or revoke links a
      colleague made on their document; list all active links on the document page.
- [x] **Q5 Thai error messages**: several API messages still reach users in English
      (link-length cap, "No such version", cancelled/not-closed project, "Name or key already
      exists", "Used by N document(s)", "already decided"). Map them or send error codes.
- [x] **Q6 Restore from trash**: say that old share links stay dead and offer "create a new link".

### 9D. Feature ideas (pick later)
- [x] **F1 Export to Excel/CSV** of the current search/filters and the proposal report (the office
      works from spreadsheets today). High value, small.
- [ ] **F2 Reminders**: weekly digest for overdue KPIs, projects near their end date, and documents
      waiting for review (email, if the university gives SMTP; else an in-app "due soon" page).
- [ ] **F3 Researcher page**: all projects of one person (from `people`), totals per year and
      funding source; link from every name.
- [ ] **F4 Backup status on the admin page**: last successful backup time; warn after 26 h.
      Needs the backup timer (Phase 2) to write a status row/file.
- [ ] **F5 Saved searches / pinned filters** per user.
- [ ] **F6 Share several papers in one link** (a teacher's whole set). Changes the "one document
      per link" rule (DESIGN §1): decide first.
- [ ] **F7 Find inside a document**: search box on the document page that jumps to the page.

### Suggested order
1. 9A S1–S3, S5, S6 (small, mostly one file each) → deploy → full tests on the server.
2. 9B B1–B5, B7, then B6 → deploy.
3. 9C Q1–Q2 (protect work), then Q3–Q6.
4. Decide S4 and F6; pick features from 9D (F1 first).

## Demo environment

- Demo admin: username `admin`, password in `~/dbresearch/secrets/demo-admin-password` on the server (mode 600).
- Demo data: the **mock** sample uploaded once (status `needs_review`). The confidential real scan is *not* in the demo DB.

- **RealLogin test (2026-11-10)**: done and removed (containers on 8121/8122 deleted). To repeat it, run IT's script in a `php:8.3-apache` container with the `ldap` extension on `dbresearch_default`, and a second app instance with `UNIVERSITY_CLIENT=php_ldap_test`, bound to `127.0.0.1` only (never on the public demo).

## Log

- 2026-11-12 — Memo numbers (`ที่ อว 0603.09.xx/NNN`) on proposal-development papers: checked 36 random scans, the line is on all of them; the running number is typed on ~15 %, handwritten on ~55 %, blank on ~30 % (department copies). OCR reads the full number on only 23/124 papers, so it stays a typed field with an OCR suggestion. Now searchable (request, timeline, closing and cancelling numbers go into `search_text`, rebuilt on close / cancel / reopen / event edit), shown on the list row, and exported.

- 2026-11-12 — Phase 9 (9A–9C + F1) built by `claude-work` workers in worktrees, reviewed, merged and deployed; 224 tests pass on the server, UI smoke clean, CI added. Notes: the worker no longer mounts `./samples` by default (use `docker-compose.samples.yml`); file responses carry `Content-Security-Policy: sandbox` (inline viewing checked in headless Chromium; check Safari/phones with B8); a re-upload of a trashed file is refused with a restore offer; duplicate race closed with a per-hash advisory lock (no unique index); review forms keep a local draft, ping the session while typing and warn before leaving; share dialog has copy-as-message, QR and version pin; Excel/CSV export of search results and the proposal report (audited). Open: S3 Cloudflare rule, B8 phone check, 9D F2–F7. Not done: a "session ends soon" warning (the API does not expose the expiry); category aliases are not in the search text.

- 2026-11-11 — Share links: every file open (view or download) counts toward the limit; "view only" option removed from the share window.

- 2026-11-11 — Security review: fixed OCR page images on disk (worker TMPDIR), share tokens in access logs, secrets mounted into containers, container privileges, guest-cookie flags.

- 2026-11-11 — Corrected who uses the system: research-office staff (`user`) and IT (`admin`) only. Teachers get no account; staff share links to them so they can view and print. University login now admits staff types only (`UNIVERSITY_ALLOWED_TYPES=staff` placeholder).

- 2026-11-11 — FF (Fundamental Fund) now counts as **internal** funding (was external); migration `d5a7c3e9f1b2` switches existing FF documents. New front-end design added as Phase 8, on hold until the remaining tasks are almost done.

- 2026-11-10 — Login system paused until the real university API or the department's user-ID server is ready (IT team continues). RealLogin test containers removed.
- 2026-11-10 — Test-only university login through IT's RealLogin.php (`UNIVERSITY_CLIENT=php_ldap_test`) on a private app copy (port 8122); student-format usernames refused before any password is sent.
- 2026-11-10 — Noted university username formats (student ID / student email with entry year / staff and teacher email) and that `RealLogin.php` is for testing only; the department deployment will log in against a database of user IDs.
- 2026-11-11 — Phase 6: approval queue for first university logins (pending → approve / reject on the Users page). Share links confirmed working on phone and PC.

- 2026-11-10 — Phase 7 step 5: ทุนพัฒนาข้อเสนอ section in the web app (list, grant page + timeline, review, overview); 180 tests pass.
- 2026-11-10 — Phase 7 step 4: bulk importer (plan / apply); real folder → 72 projects, 9 programme papers, 4 duplicates.
- 2026-11-10 — Phase 7 step 3: proposal-memo reader; type 117/124, title and researcher 94/100 against the office spreadsheet.
- 2026-11-09 — Phase 7 step 1: 124 proposal-development PDFs OCR'd on the server; paper type from text 116/124, 107/114 papers matched to the office spreadsheet.
- 2026-11-09 — Decided: new university logins need ADMIN approval (pending queue); auto-approve by department if the API returns it.
- 2026-11-09 — Login security: idle timeout, session cap, log out everywhere, richer login audit + admin summary, append-only audit log, HSTS/no-store, university login provider (teachers only, API spec pending).

- 2026-11-02 — Feedback round 1: faculty letter ≠ funding type, auto-fill tuned on 13 real contracts + 13 closing papers, inline category options, people/budget layout, close & archive projects.

- 2026-10-29 — Share-link access log names the visitor when they are logged in (new `share_access_log.user_id`); guests stay IP-only.
- 2026-10-28 — Select mode (zip download, bulk trash with undo), overview for every user, per-user bin with restore.
- 2026-10-28 — Phase 4: public demo live; per-file upload cancel, chart overview, visual refresh.

- 2026-10-28 — Phase 3: web app live on the demo server (`http://localhost:8120` through the SSH tunnel).
- 2026-10-28 — Phase 3: UI direction agreed (colors, layout, upload, filters; mocks in `docs/ui/`). Svelte web app built; API moved under `/api`.

- 2026-10-28 — Phase 2 backend done: auth, encrypted storage, auto-fill worker, review, search, share links, admin, backups + passing restore drill. Next: frontend brainstorm.
- 2026-10-28 — Phase 1 done: models + baseline/seed migrations on the live demo DB; 24 tests (9 need Postgres) pass on the server.
- 2026-10-28 — Phase 1: stack runs on the server (health OK, ICU th-TH). Spikes done: OCR, checkboxes, Thai search all work on the real scan. MinIO replaced by a local BlobStore folder (MinIO discontinued).
- 2026-10-28 — Decided: plaintext OCR text OK; login handled by IT (SSO) → swappable auth; backups kept forever + separate KEK custody.
- 2026-10-28 — First real scan reviewed (DESIGN §6 findings): low dpi + page noise, marker on the contract page itself, header variants, team block, English-only title, 2 contracts in one PDF. Seed categories updated from the real form.
- 2026-10-27 — Contract running number is per year + series → parsed columns, unique live contract no., missing-numbers report.
- 2026-10-27 — External funding uses the internal format; contract letter E=internal/A=external. Budget breakdown is manual. Production uploads are scanner PDFs only.
- 2026-10-27 — Internal-funding sample reviewed: PDF is a bundle of sections; titles use several labels/layouts; checked boxes drive auto-tags. Decided: SSH tunnel, push to `main`.
- 2026-10-27 — Git workflow verified end to end: local push → GitHub → server `git pull` (read-only deploy key; server push is refused).
- 2026-10-27 — Design agreed. Repo + server verified. Thai pg_trgm spike passed (synthetic text).
