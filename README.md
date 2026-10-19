# immich-album-share-everyone

Immich has no way to share an album with *all* users. This small sidecar adds that feature. It runs
next to your Immich compose stack, and every few minutes it adds every user to the albums you
choose. It uses only the Immich REST API, so it changes nothing inside Immich itself.

- **Shared albums:** every album owned by the accounts in `SHARE_ALL_OWNERS`, plus any album whose
  description starts with `[Shared]`.
- **Adds only:** missing users get the `editor` or `viewer` role. Nobody is ever removed, and existing roles are kept.
- **Automatic:** new users and new albums are picked up on the next run. Running it twice changes nothing.
- **Small:** one Python file, standard library only, on `python:3.13-alpine`, running as a non-root user.

Tested with Immich **v3.3.3**.

## How it works

On each run, and for each API key:

1. `GET /users/me`, `GET /users`, `GET /albums?isOwned=true`
2. It selects the albums to share: all albums if the key's owner is in `SHARE_ALL_OWNERS`,
   otherwise only albums whose description starts with the marker.
3. `PUT /albums/{id}/users` adds every user who isn't on the album yet.

Immich only lets an album's **owner** add users to it, and an API key acts as the user who
created it. So you need **one API key per account whose albums should be shared**. Albums owned by
accounts without a key are invisible to the sidecar, even if they're marked.

## Setup

### 1. Create API keys

For each account whose albums you want shared, log in as that user and open
**Account Settings → API Keys → New API Key**. Give the key only these permissions:

| Permission | Used for |
|---|---|
| `user.read` | listing users, `/users/me` |
| `album.read` | listing owned albums |
| `albumUser.create` | adding users to albums |

### 2. Install

Clone this repo anywhere on the Docker host, then point the installer at the directory that holds
Immich's `docker-compose.yml`:

```bash
git clone https://github.com/calamonkey/immich-album-share-everyone.git
cd immich-album-share-everyone
./install.sh /path/to/immich
```

The installer:

1. Checks that the directory is an Immich compose project (it has an `immich-server` service).
2. Copies `album_share.py` and the `Dockerfile` to `/path/to/immich/album-share/`.
3. Creates `album-share.env` (mode 600) and asks for your keys, owners and role.
4. Writes `docker-compose.override.yml`. Compose merges this file in automatically, so Immich's own
   `docker-compose.yml` stays untouched and can still be replaced on upgrades.
5. Builds the image and does a **dry run** that only logs what it would change.
6. Asks before starting the container. Add `--yes` to skip the question.

You can rerun it safely. It never overwrites an existing `album-share.env` or override file. If you
already have a `docker-compose.override.yml`, it prints the service block for you to merge in.

### Manual install

If you'd rather not use the installer, run this from the Immich directory:

```bash
mkdir album-share
cp /path/to/immich-album-share-everyone/{album_share.py,Dockerfile} album-share/
cp /path/to/immich-album-share-everyone/album-share.env.example album-share.env && chmod 600 album-share.env
$EDITOR album-share.env
cp /path/to/immich-album-share-everyone/docker-compose.override.yml .   # or merge it into yours
docker compose build album-share
docker compose run --rm --no-deps -e DRY_RUN=true album-share --once   # preview
docker compose up -d album-share
```

### Prebuilt image

On every push to `main` and every `v*` tag, CI publishes a multi-arch image (amd64 and arm64) to
`ghcr.io/calamonkey/immich-album-share-everyone`. To use it, swap `build: ./album-share` for the `image:` line
in the override file. Then you only need `album-share.env`, not the copied script.

## Configuration (`album-share.env`)

| Variable | Default | Meaning |
|---|---|---|
| `IMMICH_API_KEYS` | (required) | Comma-separated, one key per album owner |
| `SHARE_ALL_OWNERS` | empty | Emails whose albums are **all** shared, no marker needed |
| `SHARE_MARKER` | `[Shared]` | Description prefix that marks an album for sharing |
| `SHARE_ROLE` | `editor` | Role for added users: `editor` or `viewer` |
| `EXCLUDE_USERS` | empty | Emails that are never added |
| `INTERVAL_SECONDS` | `600` | Seconds between runs |
| `IMMICH_URL` | `http://immich-server:2283` | The Immich server as seen from the container |
| `DRY_RUN` | `false` | `true` logs the changes without making them |

To share one album, edit its description in Immich so it starts with `[Shared]`. It's picked up on
the next run.

## Operating

```bash
docker compose logs -f album-share                                       # what it's doing
docker compose run --rm --no-deps -e DRY_RUN=true album-share --once     # preview
docker compose run --rm --no-deps album-share --once                     # sync right now
```

- **Health:** the container reports healthy when a sync has succeeded within the last 3 intervals.
  A bad key or an unreachable server makes it unhealthy, and the logs show the API error.
- **Upgrades:** to update the script, `git pull` and rerun `./install.sh /path/to/immich`. It only
  replaces the script and Dockerfile. If you use the prebuilt image, run `docker compose pull album-share`.
- **Removing it:** delete the `album-share` service from the override file, then run
  `docker compose up -d --remove-orphans`. Also delete the API keys in Immich. Users it already
  added stay on their albums.

## Notes and limits

- The sidecar never removes users. If you take someone off an album that's still marked, the next
  run adds them back. Use `EXCLUDE_USERS`, or remove the marker.
- Immich may notify users when they're added to an album, the same as a manual share.
- The API keys can read your user list and albums, and add users to albums. Treat `album-share.env`
  like a password: it's git-ignored here and should stay mode 600 on the host.

## Development

```bash
python -m unittest discover -s tests -v
```

The album-selection logic is a pure function (`plan()`), so the tests need no Immich server.

## License

MIT
