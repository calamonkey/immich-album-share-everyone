#!/usr/bin/env python3
"""Share Immich albums with every user.

Selected albums:
  * every album owned by an account listed in SHARE_ALL_OWNERS, and
  * any album whose description starts with SHARE_MARKER (default "[Shared]").

Missing users are added with SHARE_ROLE. Nobody is ever removed, so runs are idempotent.

Immich only lets an album's owner add users, so IMMICH_API_KEYS holds one API key per
owner account (comma-separated). Albums owned by accounts without a key are not visible.
Each key needs: user.read, album.read, albumUser.create.
"""
import json
import os
import pathlib
import signal
import sys
import time
import urllib.error
import urllib.request

HEALTH_FILE = pathlib.Path(os.environ.get("HEALTH_FILE", "/tmp/last-success"))


def env_list(name):
    return [v.strip() for v in os.environ.get(name, "").split(",") if v.strip()]


def log(msg):
    print(time.strftime("%Y-%m-%dT%H:%M:%S"), msg, flush=True)


class Config:
    def __init__(self):
        self.url = os.environ.get("IMMICH_URL", "http://immich-server:2283").rstrip("/") + "/api"
        self.keys = env_list("IMMICH_API_KEYS")
        self.owners = {e.lower() for e in env_list("SHARE_ALL_OWNERS")}
        self.excluded = {e.lower() for e in env_list("EXCLUDE_USERS")}
        self.marker = os.environ.get("SHARE_MARKER", "[Shared]")
        self.role = os.environ.get("SHARE_ROLE", "editor")
        self.interval = int(os.environ.get("INTERVAL_SECONDS", "600"))
        self.dry_run = os.environ.get("DRY_RUN", "false").lower() in ("1", "true", "yes")
        if not self.keys:
            sys.exit("IMMICH_API_KEYS is empty: set at least one API key")
        if self.role not in ("editor", "viewer"):
            sys.exit(f"SHARE_ROLE must be editor or viewer, got {self.role!r}")


def plan(me, users, albums, cfg):
    """Return [(album, [missing user ids])] for one owner account. Pure; no I/O."""
    everyone = {u["id"]: u for u in users if u["email"].lower() not in cfg.excluded}
    owner_all = me["email"].lower() in cfg.owners
    result = []
    for album in albums:
        desc = (album.get("description") or "").lstrip()
        if not owner_all and not desc.startswith(cfg.marker):
            continue
        members = {au["user"]["id"] for au in album.get("albumUsers", [])} | {me["id"]}
        missing = [uid for uid in everyone if uid not in members]
        result.append((album, missing))
    return result


class Immich:
    def __init__(self, url, key):
        self.url, self.key = url, key

    def __call__(self, method, path, body=None):
        req = urllib.request.Request(
            self.url + path,
            method=method,
            data=json.dumps(body).encode() if body is not None else None,
            headers={"x-api-key": self.key, "Content-Type": "application/json", "Accept": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                data = r.read()
                return json.loads(data) if data else None
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"{method} {path} -> HTTP {e.code}: {e.read().decode(errors='replace')[:300]}") from None


def sync(cfg):
    changes = 0
    for i, key in enumerate(cfg.keys, 1):
        api = Immich(cfg.url, key)
        try:
            me = api("GET", "/users/me")
        except RuntimeError as e:
            raise RuntimeError(f"API key #{i}: {e}") from None
        users = api("GET", "/users")
        owned = api("GET", "/albums?isOwned=true")
        emails = {u["id"]: u["email"] for u in users}
        selected = plan(me, users, owned, cfg)
        for album, missing in selected:
            if not missing:
                continue
            names = ", ".join(emails[u] for u in missing)
            log(f"{'[dry-run] ' if cfg.dry_run else ''}'{album['albumName']}' ({me['email']}): add {names} as {cfg.role}")
            if not cfg.dry_run:
                api("PUT", f"/albums/{album['id']}/users",
                    {"albumUsers": [{"userId": u, "role": cfg.role} for u in missing]})
            changes += len(missing)
        log(f"{me['email']}: {len(owned)} owned album(s), {len(selected)} selected, {len(users)} user(s)")
    return changes


def main():
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))  # PID 1 in a container ignores SIGTERM otherwise
    cfg = Config()
    once = "--once" in sys.argv
    while True:
        try:
            n = sync(cfg)
            HEALTH_FILE.touch()
            log(f"sync done, {n} membership(s) {'would be ' if cfg.dry_run else ''}added")
        except Exception as e:  # keep the loop alive; the next run retries
            log(f"sync failed: {e}")
            if once:
                sys.exit(1)
        if once:
            return
        time.sleep(cfg.interval)


if __name__ == "__main__":
    main()
