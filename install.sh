#!/usr/bin/env bash
# Install the album-share sidecar next to a running Immich docker compose stack.
#
#   ./install.sh /path/to/immich          # the dir holding Immich's docker-compose.yml
#   ./install.sh /path/to/immich --yes    # don't ask before starting the container
#
# Safe to rerun: it never overwrites album-share.env or an existing override file, and it only
# starts the container after a successful dry run.
set -euo pipefail

SRC=$(cd "$(dirname "$0")" && pwd)
DIR=${1:-}
YES=false
[[ "${2:-}" == "--yes" ]] && YES=true
die() { echo "error: $*" >&2; exit 1; }
say() { echo "==> $*"; }

[[ -n "$DIR" ]] || die "usage: $0 /path/to/immich [--yes]"
DIR=$(cd "$DIR" && pwd)
cd "$DIR"
docker compose version >/dev/null 2>&1 || die "docker compose v2 is required"
docker compose config --services 2>/dev/null | grep -qx immich-server \
  || die "$DIR doesn't look like an Immich compose project (no immich-server service)"

say "copying script + Dockerfile to $DIR/album-share/"
mkdir -p album-share
cp "$SRC/album_share.py" "$SRC/Dockerfile" album-share/

if [[ ! -f album-share.env ]]; then
  say "creating album-share.env"
  (umask 077; cp "$SRC/album-share.env.example" album-share.env)
  if [[ -t 0 ]]; then
    echo
    echo "Create an API key for each account whose albums should be shared"
    echo "(Immich -> Account Settings -> API Keys, permissions: user.read, album.read, albumUser.create)."
    read -rsp "API key(s), comma-separated (input hidden): " keys; echo
    read -rp "Emails whose albums are ALL shared (optional, comma-separated): " owners
    read -rp "Role for added users [editor/viewer] (editor): " role
    sed -i "s|^IMMICH_API_KEYS=.*|IMMICH_API_KEYS=${keys}|; s|^SHARE_ALL_OWNERS=.*|SHARE_ALL_OWNERS=${owners}|; s|^SHARE_ROLE=.*|SHARE_ROLE=${role:-editor}|" album-share.env
  fi
fi
chmod 600 album-share.env
grep -qE '^IMMICH_API_KEYS=.+' album-share.env \
  || die "set IMMICH_API_KEYS in $DIR/album-share.env, then rerun"

if [[ -f docker-compose.override.yml ]]; then
  if docker compose config --services | grep -qx album-share; then
    say "album-share service already present in docker-compose.override.yml"
  else
    echo
    echo "You already have a docker-compose.override.yml. Merge this service into it, then rerun:"
    echo
    sed -n '/^services:/,$p' "$SRC/docker-compose.override.yml" | tail -n +2
    exit 2
  fi
else
  say "writing docker-compose.override.yml"
  cp "$SRC/docker-compose.override.yml" docker-compose.override.yml
fi

say "building image"
docker compose build album-share

say "dry run (no changes are made)"
docker compose run --rm --no-deps -e DRY_RUN=true album-share --once \
  || die "dry run failed; check the API keys and IMMICH_URL in album-share.env"

if ! $YES; then
  read -rp "Start the sidecar now? It will make the changes listed above. [y/N] " ok
  [[ "$ok" =~ ^[Yy] ]] || { echo "Not started. Later: cd $DIR && docker compose up -d album-share"; exit 0; }
fi
docker compose up -d album-share
say "running. Logs: cd $DIR && docker compose logs -f album-share"
