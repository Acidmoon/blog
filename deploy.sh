#!/usr/bin/env bash
set -Eeuo pipefail

REMOTE="${REMOTE:-origin}"
BRANCH="${BRANCH:-master}"
SERVICE="${SERVICE:-blog}"
HEALTH_TIMEOUT="${HEALTH_TIMEOUT:-90}"
previous_revision=''
previous_short_revision=''
previous_container_id=''
previous_image_id=''
previous_image_ref=''

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

wait_for_healthy() {
  local container_id="$1"
  local label="$2"
  local deadline status

  deadline=$((SECONDS + HEALTH_TIMEOUT))
  while true; do
    if ! status="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}missing-healthcheck{{end}}' "$container_id" 2>/dev/null)"; then
      printf '[deploy] cannot inspect %s container: %s\n' "$label" "$container_id" >&2
      return 1
    fi
    case "$status" in
      healthy)
        return 0
        ;;
      unhealthy|exited|dead|missing-healthcheck)
        printf '[deploy] %s container is not healthy, status: %s\n' "$label" "$status" >&2
        return 1
        ;;
    esac
    if [ "$SECONDS" -ge "$deadline" ]; then
      printf '[deploy] %s health check timed out after %ss, last status: %s\n' \
        "$label" "$HEALTH_TIMEOUT" "$status" >&2
      return 1
    fi
    sleep 2
  done
}

rollback_target_service() {
  local reason="$1"
  local rollback_container_id restored_image=0

  printf '[deploy] deployment failed: %s\n' "$reason" >&2
  if [ -z "$previous_revision" ]; then
    printf '[deploy] rollback unavailable: previous revision was not recorded\n' >&2
    return 1
  fi

  log "rolling back ${SERVICE} to ${previous_short_revision}"
  if ! git reset --hard "$previous_revision"; then
    printf '[deploy] rollback failed while restoring revision %s\n' "$previous_revision" >&2
    return 1
  fi

  if [ -n "$previous_image_id" ] && [ -n "$previous_image_ref" ] \
    && docker image inspect "$previous_image_id" >/dev/null 2>&1; then
    if docker tag "$previous_image_id" "$previous_image_ref"; then
      restored_image=1
      log "restored previous target image ${previous_image_id}"
    else
      printf '[deploy] could not retag previous image; rebuilding the recorded revision\n' >&2
    fi
  else
    printf '[deploy] previous target image is unavailable; rebuilding the recorded revision\n' >&2
  fi

  if [ "$restored_image" -eq 1 ]; then
    if ! compose up -d --no-deps --force-recreate "$SERVICE"; then
      printf '[deploy] rollback failed while restoring the target service image\n' >&2
      return 1
    fi
  elif ! compose up -d --build --no-deps --force-recreate "$SERVICE"; then
    printf '[deploy] rollback failed while rebuilding the target service\n' >&2
    return 1
  fi

  rollback_container_id="$(compose ps -q "$SERVICE" || true)"
  if [ -z "$rollback_container_id" ]; then
    printf '[deploy] rollback did not create a target service container: %s\n' "$SERVICE" >&2
    return 1
  fi
  if ! wait_for_healthy "$rollback_container_id" 'rollback'; then
    compose logs --tail=120 "$SERVICE" >&2 || true
    return 1
  fi
  log "rollback completed for ${SERVICE} at ${previous_short_revision}"
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

previous_revision="$(git rev-parse --verify HEAD)"
previous_short_revision="$(git rev-parse --short "$previous_revision")"
previous_container_id="$(compose ps -q "$SERVICE" || true)"
if [ -n "$previous_container_id" ]; then
  previous_image_id="$(docker inspect --format '{{.Image}}' "$previous_container_id" 2>/dev/null || true)"
  previous_image_ref="$(docker inspect --format '{{.Config.Image}}' "$previous_container_id" 2>/dev/null || true)"
fi
log "recorded previous revision: ${previous_short_revision}"
log "recorded previous image: ${previous_image_id:-none}"

log "fast-forwarding ${BRANCH}"
git pull --ff-only "$REMOTE" "$BRANCH"

log "building and starting ${SERVICE}"
if ! compose up -d --build "$SERVICE"; then
  rollback_target_service "target service failed to start"
  exit 1
fi

container_id="$(compose ps -q "$SERVICE" || true)"
if [ -z "$container_id" ]; then
  printf '[deploy] service container was not created: %s\n' "$SERVICE" >&2
  compose ps >&2 || true
  rollback_target_service "target service container was not created"
  exit 1
fi

log "waiting for health check"
if ! wait_for_healthy "$container_id" 'new'; then
  compose logs --tail=120 "$SERVICE" >&2 || true
  rollback_target_service "new target service did not become healthy"
  exit 1
fi

log "deployed $(git rev-parse --short HEAD)"
compose ps "$SERVICE"
