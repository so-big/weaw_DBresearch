# Operations runbook

Server: `cs31@100.104.87.92`, checkout in `~/dbresearch`, Docker Compose project `dbresearch`.
Design background: [DESIGN.md](DESIGN.md) §2 (encryption, backups).

## Deploy

```bash
ssh cs31@100.104.87.92 'cd ~/dbresearch && git pull && docker compose up -d --build'
curl -s 127.0.0.1:8120/health        # on the server: every check must be "ok"
```

`migrate` runs `alembic upgrade head` before `api` and `worker` start. Test access from a
laptop: `ssh -N -L 8120:127.0.0.1:8120 cs31@100.104.87.92`, then open `http://localhost:8120` (web app) or `http://localhost:8120/api/docs` (API docs).

## Public demo (Cloudflare Tunnel)

The server already runs `cloudflared` as a token-based tunnel (shared with other projects).
DBresearch needs no open port and no server change: the app stays on `127.0.0.1:8120` and the
tunnel forwards one hostname to it. Configure it in the Cloudflare dashboard:

1. **Zero Trust → Networks → Tunnels** → the tunnel running on this server → **Public hostnames**
   (newer UI: *Published application routes*) → **Add**.
2. Subdomain + domain of your choice (e.g. `dbresearch.example.com`), path empty,
   service **HTTP** → `localhost:8120`. Save: Cloudflare creates the DNS record itself.
3. **SSL/TLS → Edge certificates**: turn on *Always Use HTTPS*.
4. Server `.env` has `COOKIE_SECURE=true` and `TRUSTED_IP_HEADER=CF-Connecting-IP`
   (see `.env.example`), then `docker compose up -d`.

Notes:
- Uploads: Cloudflare's Free/Pro plans cap a request at 100 MB, the same as `MAX_UPLOAD_MB`.
- Local login is public now: 5 wrong passwords lock that username for 15 min (20 per IP).
  Give testers their own accounts (ผู้ดูแลระบบ → ผู้ใช้) and use strong passwords.
- Optional extra lock: a Cloudflare Access application on the hostname (email one-time code)
  with a *Bypass* policy for `/s/*`, `/api/s/*`, `/assets/*` and `/favicon.svg`, so share
  links still open for guests.
- The demo holds mock data only. Don't upload confidential scans until SSO is in place.

## First-time setup (already done on the demo server)

| Step | Command |
|---|---|
| DB password + signing key | `.env` with `POSTGRES_PASSWORD` and `SECRET_KEY` (`openssl rand -hex 32`), mode 600 |
| Master key (KEK) | `mkdir -p secrets && setfacl -m u:10001:rwx secrets` then `docker compose run --rm --no-deps -T -v ./secrets:/out api python -m dbresearch.cli kek-init --out /out/kek.json` |
| First admin | `docker compose exec -it api python -m dbresearch.cli create-admin --email … --name … --username …` (password prompted, or `DBR_PASSWORD`) |

## The master key (KEK): most important

Every stored file is encrypted under the KEK. **If the KEK is lost, every document and every
backup is unreadable forever.** Backups deliberately do *not* contain it.

1. Right after `kek-init`, make **two copies outside the server, kept apart from the backups**.
   For example: the department's password manager/vault, and a USB stick or printed copy in a
   locked cabinet.
   Read it with: `docker compose exec api cat /run/secrets/kek.json`.
2. Never put it in git, the database, chat, e-mail, or the restic repository.
3. Write down who holds the copies (open question for IT, see plan.md).
4. Rotation (future): add a new key to the keyset and make it primary. Old keys stay in the
   keyset forever, because backups still need them.

The restic password (`secrets/restic-password`) follows the same rules: lose it and the backups
are gone.

## Backups (kept forever)

`scripts/backup.sh` streams `pg_dump` straight into restic (no dump file on disk), then backs
up the encrypted `blobs` volume. It never runs `forget`/`prune`. On Sundays it also runs
`restic check --read-data-subset=5%`.

Setup:

```bash
cp backup.env.example backup.env && chmod 600 backup.env   # set RESTIC_REPOSITORY (college NAS)
openssl rand -base64 32 > secrets/restic-password && chmod 600 secrets/restic-password
scripts/backup.sh init        # once per repository
scripts/backup.sh             # a backup now
cp ops/dbresearch-backup.{service,timer} ~/.config/systemd/user/
systemctl --user daemon-reload && systemctl --user enable --now dbresearch-backup.timer
loginctl enable-linger "$USER"   # nightly 02:30 even when nobody is logged in
```

> The demo server currently backs up to a **local test repository** (`~/dbresearch-backup-test`)
> to prove the mechanics. A backup on the same disk is not a real backup: point
> `RESTIC_REPOSITORY` at the college NAS once IT confirms the access method.

## Restore drill (monthly)

```bash
scripts/restore-drill.sh            # SAMPLE=50 scripts/restore-drill.sh for a bigger sample
```

It restores the latest DB dump and blobs into a scratch folder and loads the dump into a
throwaway Postgres on a private network. It then runs `verify-storage`: every blob must be
present, and a random sample must decrypt with the KEK and match its SHA-256. Nothing live is
touched. "restore drill PASSED" means the backup is usable.

Live integrity check at any time: `docker compose exec api python -m dbresearch.cli verify-storage --sample 50`.

## Full restore (disaster)

1. New server with Docker, this repo, `.env`, and **the KEK copy** in `secrets/kek.json`.
2. `docker compose up -d db`, then
   `restic restore latest --tag db --target /tmp/r` and
   `docker compose exec -T db pg_restore -U dbresearch -d dbresearch --clean --if-exists < /tmp/r/dbresearch.dump`.
3. `restic restore latest --tag blobs --target /tmp/r`, then copy `/tmp/r/blobs/` into the
   `dbresearch_blobs` volume.
4. `docker compose up -d`, then `verify-storage` (no `--sample` = check everything).

## Purge is not erasure

ADMIN purge removes a trashed document's rows, wrapped key and blob from the **live** system.
Older backups still contain both, and they are kept forever (department decision). That is
intended: data must not be lost.

## Useful checks

| What | Command (on the server, in `~/dbresearch`) |
|---|---|
| Health | `curl -s 127.0.0.1:8120/health` |
| Worker log (ids/counts only) | `docker compose logs worker --tail 50` |
| Failed OCR jobs | `docker compose exec db psql -U dbresearch -c "select id, kind, attempts, last_error from jobs where state='failed'"` |
| Tests | `docker compose exec -T api pytest -q` |
| Samples / bulk import (dev/demo only) | The production compose file does not mount `./samples`. First run `docker compose -f docker-compose.yml -f docker-compose.samples.yml up -d worker`, then the `docker compose exec worker ... /samples/...` commands. Recreate the worker without the override afterwards to unmount. |
