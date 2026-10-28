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
- [x] Contract no. = `R` + B.E. year + funding letter + running no.: `E` = internal (`R2568E999`), `A` = external (`R2568A001`). The letter sets `funding_type`.
- [x] Running number counts per year + series (`R2568E001` = first internal of 2568). Used for sorting, duplicate-upload detection (unique per live doc), and an ADMIN missing-numbers report. The system stores numbers, never issues them.
- [x] External funding uses the same document format as internal → same section templates; funding type comes from the contract no.
- [x] Budget: auto-fill only `budget_total`. Line items / installments (`งวด`) are typed manually into `budget_lines`.
- [x] One PDF = **exactly one contract** (one contract no.). Different numbers within a PDF → warning only, no split.
- [x] Package = contract body + `เอกสารแนบ 1–5`. Auto-fill only from the body, att. 1 (money: total) and att. 5 (proposal: titles, checkboxes, team). Att. 2–4 are OCR'd for search only.
- [x] OCR text stored **unencrypted** in the DB: accepted (low-sensitivity; files themselves stay encrypted).
- [x] Login: the **IT team integrates college SSO**. We build a minimal swappable `AuthProvider` (local login for dev/demo only); roles live in our DB.
- [x] Backups **kept forever** (never prune), off the server, nightly `pg_dump` + blob folder via restic, to the college NAS (assumed). **KEK backed up separately**; losing it = losing every file.
- [x] File store: **local folder + `BlobStore` interface** (MinIO discontinued 2026-04).
- [x] Sharing: **any USER** can share any document they can read; only the link's creator or an ADMIN manages it.
- [x] kind / funding_type may be empty until review; a document can only become `ready` with both set.
- [x] If OCR fails 3 times, the document still goes to review (warning `ocr_failed`) so metadata can be typed by hand.
- [x] Production uploads: **scanner PDFs only**. Auto-fill is assistive; anything wrong or missing is typed by the user on the review screen.

## Decisions still open

- [?] **Backup target** (IT team): **assumed college NAS**; access method still unknown (`RESTIC_REPOSITORY` is configurable).
- [?] **SSO protocol** (IT team): OIDC / SAML / LDAP / proxy header → which `AuthProvider` to build.

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
- [ ] Try it on a real phone (guest link, search, upload from the phone's files) and collect feedback
- [ ] Later: PDF preview inside the page on phones (pdf.js) if opening a new tab is not enough

## Phase 4 — Polish and public demo

- [x] Public demo at **https://dbresearch.promptjang.com** (Cloudflare Tunnel → `127.0.0.1:8120`). The college network blocks `promptjang.com`; testers there use a VPN. Visitor IP from `CF-Connecting-IP`, HTTPS-only cookies, login limit (5 per username / 15 min).
- [x] Thai error messages for known API errors; drag & drop accepts every way desktops hand over files
- [x] Upload window: cancel any file (waiting, uploading, or undo a finished upload → trash)
- [x] Overview with charts: status meter, documents + budget per fiscal year, uploads per month, views/downloads per day, top categories, contract-number coverage grid (each with a table view). `GET /api/admin/reports/charts`
- [x] Visual refresh: maroon masthead with search + quick figures, funding-tinted file tiles, split login, guest band
- [ ] Collect tester feedback on the live site and fix what feels off

## Demo environment

- Demo admin: username `admin`, password in `~/dbresearch/secrets/demo-admin-password` on the server (mode 600).
- Demo data: the **mock** sample uploaded once (status `needs_review`). The confidential real scan is *not* in the demo DB.

## Log

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
