#!/usr/bin/env bash
# Nightly backup: database dump + encrypted blobs → restic. Run on the server host.
#
#   scripts/backup.sh            (reads ./backup.env)
#
# - The DB dump is streamed straight into restic (no dump file on disk).
# - Blobs are already ciphertext; restic encrypts everything again with its own password.
# - Snapshots are NEVER forgotten or pruned: data must not be lost (CLAUDE.md).
# - The KEK is NOT backed up here, on purpose: it lives in separate custody (docs/OPERATIONS.md).
set -euo pipefail
cd "$(dirname "$0")/.."

ENV_FILE=${ENV_FILE:-backup.env}
[ -f "$ENV_FILE" ] || { echo "missing $ENV_FILE (see backup.env.example)" >&2; exit 2; }
# shellcheck disable=SC1090
source "$ENV_FILE"
: "${RESTIC_REPOSITORY:?set in $ENV_FILE}" "${RESTIC_PASSWORD_FILE:?set in $ENV_FILE}"
RESTIC_IMAGE=${RESTIC_IMAGE:-restic/restic:0.19.1}
PROJECT=${COMPOSE_PROJECT_NAME:-dbresearch}

restic() {
  local mounts=(-v "$(realpath "$RESTIC_PASSWORD_FILE")":/run/restic-password:ro)
  # A local (path) repository must be mounted into the container at the same path.
  if [[ "$RESTIC_REPOSITORY" == /* ]]; then
    mounts+=(-v "$RESTIC_REPOSITORY":"$RESTIC_REPOSITORY")
  fi
  docker run --rm -i --hostname dbresearch-backup --user "$(id -u):$(id -g)" \
    -e RESTIC_CACHE_DIR=/tmp/restic-cache "${mounts[@]}" "${EXTRA_DOCKER_ARGS[@]}" \
    -e RESTIC_REPOSITORY -e RESTIC_PASSWORD_FILE=/run/restic-password \
    ${RESTIC_ENV:+--env-file "$RESTIC_ENV"} "$RESTIC_IMAGE" "$@"
}
EXTRA_DOCKER_ARGS=()

if [ "${1:-}" = "init" ]; then
  restic init
  exit
fi

stamp=$(date -u +%Y-%m-%dT%H%M%SZ)
echo "[$stamp] dumping database → restic"
docker compose -p "$PROJECT" exec -T db pg_dump -U dbresearch -d dbresearch -Fc \
  | restic backup --stdin --stdin-filename dbresearch.dump --tag db --tag "$stamp"

echo "[$stamp] encrypted blobs → restic"
EXTRA_DOCKER_ARGS=(-v "${PROJECT}_blobs":/blobs:ro)
restic backup /blobs --tag blobs --tag "$stamp"
EXTRA_DOCKER_ARGS=()

if [ "$(date -u +%u)" = "7" ]; then  # Sundays: verify a slice of the stored data
  echo "[$stamp] weekly integrity check"
  restic check --read-data-subset=5%
fi
echo "[$stamp] done"
