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

## Decisions still open

- [?] **Sample documents**: External/Internal funding scans (needed for templates, OCR test, frontend).
- [?] **Port + access for testing**: SSH tunnel (`ssh -L 8120:127.0.0.1:8120 cs31@…`, recommended, nothing exposed), bind to the Tailscale IP, or route through the existing reverse proxy on :443 with a domain.
- [?] **Branching**: push straight to `main` (solo), or feature branches + PRs.
- [?] **OCR text plaintext in DB**: does the department accept this trade-off? (DESIGN §2)
- [?] **Backup policy + retention**: affects the crypto-shred guarantee.
- [?] **Projects UI**: first-class, or hidden until we know grants span several files.
- [?] **Frontend stack**: decide when the frontend phase starts (must work well on low-end phones).

## Phase 1 — Foundation (not started, no coding yet)

- [ ] Spike: OCR quality with `ocrmypdf -l tha+eng` on real samples (on the server)
- [ ] Re-test Thai search on real OCR text, then decide on the PyThaiNLP fallback
- [ ] Project scaffold: `pyproject.toml` (uv), ruff config, FastAPI skeleton, Dockerfile
- [ ] `docker-compose.yml`: postgres (ICU th-TH), minio, api, worker. Ports bound to 127.0.0.1 only
- [ ] Alembic baseline migration from DESIGN §3
- [ ] pytest against a throwaway Postgres on the server

## Phase 2+ — Features (order from DESIGN §7)

- [ ] Auth: local identities, sessions, roles, admin bootstrap CLI
- [ ] Upload/download with envelope encryption + versions
- [ ] OCR worker + jobs queue + template engine + review/confirm flow
- [ ] Search & filters
- [ ] Share links + access log + admin active-links screen
- [ ] Trash/purge, audit views, settings
- [ ] Frontend

## Log

- 2026-10-27 — Git workflow verified end to end: local push → GitHub → server `git pull` (read-only deploy key; server push is refused).
- 2026-10-27 — Design agreed. Repo + server verified. Thai pg_trgm spike passed (synthetic text).
