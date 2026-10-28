#!/usr/bin/env bash
# Restore drill: prove the latest backup can be restored and decrypted. Touches nothing live.
#
#   scripts/restore-drill.sh     (reads ./backup.env; needs the KEK at ./secrets/kek.json)
#
# 1. restore the latest DB dump + blobs from restic into a scratch folder
# 2. load the dump into a throwaway Postgres (ICU th-TH) on a private network
# 3. run `dbresearch.cli verify-storage` against it: every blob present, a sample decrypts with
#    the KEK and matches its SHA-256
# Exit code 0 = the backup is usable. Everything scratch is deleted afterwards.
set -euo pipefail
cd "$(dirname "$0")/.."
source "${ENV_FILE:-backup.env}"
RESTIC_IMAGE=${RESTIC_IMAGE:-restic/restic:0.19.1}
SAMPLE=${SAMPLE:-20}
drill=dbresearch-drill-$$
scratch=$(mktemp -d "${TMPDIR:-/tmp}/dbresearch-drill.XXXXXX")
chmod 700 "$scratch"

cleanup() {
  docker rm -f "$drill-db" >/dev/null 2>&1 || true
  docker network rm "$drill" >/dev/null 2>&1 || true
  rm -rf "$scratch"
}
trap cleanup EXIT

restic() {
  local mounts=(-v "$(realpath "$RESTIC_PASSWORD_FILE")":/run/restic-password:ro
                -v "$scratch":/scratch)
  if [[ "$RESTIC_REPOSITORY" == /* ]]; then mounts+=(-v "$RESTIC_REPOSITORY":"$RESTIC_REPOSITORY"); fi
  docker run --rm --hostname dbresearch-backup --user "$(id -u):$(id -g)" \
    -e RESTIC_CACHE_DIR=/tmp/restic-cache "${mounts[@]}" -e RESTIC_REPOSITORY -e RESTIC_PASSWORD_FILE=/run/restic-password \
    ${RESTIC_ENV:+--env-file "$RESTIC_ENV"} "$RESTIC_IMAGE" "$@"
}

echo "== restoring latest snapshots"
restic restore latest --tag db --target /scratch/db
restic restore latest --tag blobs --target /scratch

echo "== loading the dump into a throwaway Postgres"
docker network create --internal "$drill" >/dev/null
docker run -d --name "$drill-db" --network "$drill" -e POSTGRES_PASSWORD=drill \
  -e POSTGRES_USER=dbresearch -e POSTGRES_DB=dbresearch \
  -e POSTGRES_INITDB_ARGS="--encoding=UTF8 --locale-provider=icu --icu-locale=th-TH --locale=C.UTF-8" \
  postgres:17.11 >/dev/null
until docker exec "$drill-db" pg_isready -U dbresearch -d dbresearch >/dev/null 2>&1; do sleep 1; done
sleep 2
docker exec -i "$drill-db" pg_restore -U dbresearch -d dbresearch --no-owner --exit-on-error \
  < "$scratch/db/dbresearch.dump"
docker exec "$drill-db" psql -U dbresearch -d dbresearch -tAc \
  "SELECT 'documents=' || count(*) FROM documents UNION ALL SELECT 'versions=' || count(*) FROM document_versions"

echo "== verifying blobs + decryption (sample $SAMPLE)"
docker run --rm --network "$drill" -v "$scratch/blobs":/data/blobs:ro \
  -v "$(pwd)/secrets":/run/secrets:ro \
  -e DATABASE_URL="postgresql+psycopg://dbresearch:drill@$drill-db:5432/dbresearch" \
  dbresearch-app:dev python -m dbresearch.cli verify-storage --sample "$SAMPLE"
echo "== restore drill PASSED"
