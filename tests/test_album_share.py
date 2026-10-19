import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import album_share  # noqa: E402

ME = {"id": "u1", "email": "owner@example.com"}
USERS = [ME, {"id": "u2", "email": "b@example.com"}, {"id": "u3", "email": "c@example.com"}]


def album(aid, desc=None, members=()):
    return {"id": aid, "albumName": aid, "description": desc,
            "albumUsers": [{"user": {"id": m}, "role": "editor"} for m in members]}


def cfg(**env):
    base = {"IMMICH_API_KEYS": "k"}
    base.update(env)
    with mock.patch.dict(os.environ, base, clear=True):
        return album_share.Config()


class PlanTests(unittest.TestCase):
    def test_marker_selects_album(self):
        out = album_share.plan(ME, USERS, [album("a", "[Shared] trip"), album("b", "private")], cfg())
        self.assertEqual([(a["id"], m) for a, m in out], [("a", ["u2", "u3"])])

    def test_owner_all_selects_everything(self):
        out = album_share.plan(ME, USERS, [album("a"), album("b", "x")], cfg(SHARE_ALL_OWNERS="Owner@Example.com"))
        self.assertEqual(len(out), 2)

    def test_existing_members_and_owner_skipped(self):
        out = album_share.plan(ME, USERS, [album("a", "[Shared]", members=["u1", "u2"])], cfg())
        self.assertEqual(out[0][1], ["u3"])

    def test_owner_not_in_album_users_is_not_added(self):
        out = album_share.plan(ME, USERS, [album("a", "[Shared]")], cfg())
        self.assertNotIn("u1", out[0][1])

    def test_excluded_users(self):
        out = album_share.plan(ME, USERS, [album("a", "[Shared]")], cfg(EXCLUDE_USERS="c@example.com"))
        self.assertEqual(out[0][1], ["u2"])

    def test_leading_whitespace_and_custom_marker(self):
        out = album_share.plan(ME, USERS, [album("a", "  #family")], cfg(SHARE_MARKER="#family"))
        self.assertEqual(len(out), 1)

    def test_bad_role_rejected(self):
        with self.assertRaises(SystemExit):
            cfg(SHARE_ROLE="owner")

    def test_missing_keys_rejected(self):
        with mock.patch.dict(os.environ, {}, clear=True), self.assertRaises(SystemExit):
            album_share.Config()


if __name__ == "__main__":
    unittest.main()
