#!/usr/bin/env bash
set -Eeuo pipefail

REMOTE="${REMOTE:-origin}"
BRANCH="${BRANCH:-master}"
SERVICE="${SERVICE:-blog}"
HEALTH_TIMEOUT="${HEALTH_TIMEOUT:-90}"

cd "$(dirname "$0")"

log() {
  printf '[deploy] %s\n' "$*"
}

require_command() {
  if ! command -v "$1" >/dev/null 2>&1; then
    printf '[deploy] missing command: %s\n' "$1" >&2
    exit 1
  fi
}

compose() {
  docker compose "$@"
}

require_command git
require_command docker

if ! docker compose version >/dev/null 2>&1; then
  printf '[deploy] docker compose is not available\n' >&2
  exit 1
fi

if [ -n "$(git status --porcelain)" ]; then
  printf '[deploy] working tree is not clean; commit, stash, or discard local changes first\n' >&2
  git status --short >&2
  exit 1
fi

log "fetching ${REMOTE}/${BRANCH}"
git fetch "$REMOTE" "$BRANCH"

current_branch="$(git branch --show-current)"
if [ "$current_branch" != "$BRANCH" ]; then
  log "switching from ${current_branch:-detached HEAD} to ${BRANCH}"
  git checkout "$BRANCH"
fi

log "fast-forwarding ${BRANCH}"
git pull --ff-only "$REMOTE" "$BRANCH"

log "building and starting ${SERVICE}"
compose up -d --build "$SERVICE"

container_id="$(compose ps -q "$SERVICE")"
if [ -z "$container_id" ]; then
  printf '[deploy] service container was not created: %s\n' "$SERVICE" >&2
  compose ps >&2
  exit 1
fi

log "waiting for health check"
deadline=$((SECONDS + HEALTH_TIMEOUT))
while true; do
  status="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$container_id")"
  if [ "$status" = "healthy" ] || [ "$status" = "running" ]; then
    break
  fi
  if [ "$status" = "unhealthy" ]; then
    printf '[deploy] container became unhealthy\n' >&2
    compose logs --tail=120 "$SERVICE" >&2
    exit 1
  fi
  if [ "$SECONDS" -ge "$deadline" ]; then
    printf '[deploy] health check timed out after %ss, last status: %s\n' "$HEALTH_TIMEOUT" "$status" >&2
    compose logs --tail=120 "$SERVICE" >&2
    exit 1
  fi
  sleep 2
done

log "deployed $(git rev-parse --short HEAD)"
compose ps "$SERVICE"
