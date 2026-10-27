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
4. Run heavy tests on the server (Postgres, MinIO, OCR): `docker compose exec api uv run pytest`.
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
- [x] Check marks can be typed ☑ or pen ticks → detect by ink inside the box, not by OCR.
- [x] Contract no. `R2568E999` = `R`+B.E. year, `E`+running number. Not used for funding type.

## Decisions still open

- [?] **External-funding format**: no sample yet.
- [?] **Scanned sample with pen ticks**: needed to tune checkbox thresholds (current sample is born-digital).
- [?] **Budget line items** (เอกสารแนบ 1): store them in `extra.budget_items`, or only the total?
- [?] **OCR text plaintext in DB**: does the department accept this trade-off? (DESIGN §2)
- [?] **Backup policy + retention**: affects the crypto-shred guarantee.
- [?] **Frontend stack**: decide when the frontend phase starts (must work well on low-end phones).

## Phase 1 — Foundation (not started, no coding yet)

- [x] Review internal-funding sample → DESIGN §6 (sections, label variants, checkbox groups, seed categories)
- [ ] Copy samples to the server: `scp "docs/sample document-1.pdf" cs31@100.104.87.92:~/dbresearch/samples/`
- [ ] Spike: Tesseract `tha+eng` on rendered pages vs. the PDF text layer (on the server)
- [ ] Spike: checkbox detection + fill threshold + strikethrough removal (on the server)
- [ ] Re-test Thai search on real OCR text, then decide on the PyThaiNLP fallback
- [ ] Project scaffold: `pyproject.toml` (uv), ruff config, FastAPI skeleton, Dockerfile (with `tesseract-ocr-tha`, poppler)
- [ ] `docker-compose.yml`: postgres (ICU th-TH), minio, api (`127.0.0.1:8120`), worker
- [ ] Alembic baseline migration from DESIGN §3 + seed categories from DESIGN §6
- [ ] pytest against a throwaway Postgres on the server

## Phase 2+ — Features (order from DESIGN §8)

- [ ] Auth: local identities, sessions, roles, admin bootstrap CLI
- [ ] Upload/download with envelope encryption + versions
- [ ] Worker + jobs queue + auto-fill pipeline (sections, fields, checkboxes, warnings) + review/confirm flow
- [ ] Search & filters
- [ ] Share links + access log + admin active-links screen
- [ ] Trash/purge, audit views, settings
- [ ] Frontend

## Log

- 2026-10-27 — Internal-funding sample reviewed: PDF is a bundle of sections; titles use several labels/layouts; checked boxes drive auto-tags. Decided: SSH tunnel, push to `main`.
- 2026-10-27 — Git workflow verified end to end: local push → GitHub → server `git pull` (read-only deploy key; server push is refused).
- 2026-10-27 — Design agreed. Repo + server verified. Thai pg_trgm spike passed (synthetic text).
