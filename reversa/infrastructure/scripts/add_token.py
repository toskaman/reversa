"""Manage API tokens (server-side CLI; never prints secrets).

Usage:
  python add_token.py <org-slug> <name> <sha256>
      Insert a token row by hash (legacy form).
  python add_token.py revoke-historic <org-slug> [--name NAME]...
      Revoke historic demo credential(s) by name (default: seed name) and
      blocklist their hashes so a DB restore cannot resurrect them.
      Prints revoked names + remaining count only. Refuses to delete the
      last remaining credential (mint a replacement first).
"""
import sys

from fastapi import HTTPException

from reversa_api.auth import revoke_historic_demo_tokens
from reversa_api.db import session_for
from reversa_api.models import ApiToken, Organization


def _insert(slug: str, name: str, hash_: str) -> None:
    session = session_for("main")()
    org = session.query(Organization).filter_by(slug=slug).first()
    assert org, f"org {slug} missing"
    session.add(ApiToken(org_id=org.id, name=name, token_hash=hash_))
    session.commit()
    print("token-ok")


def _revoke_historic(slug: str, names: list[str]) -> int:
    try:
        out = revoke_historic_demo_tokens(
            slug, names=names or None)  # type: ignore[arg-type]
    except HTTPException as exc:
        print(f"revoke-failed: {exc.status_code} {exc.detail}")
        return 1
    print(f"revoked={','.join(out['revoked']) or '(none)'} "
          f"remaining={out['remaining']}")
    return 0


def main() -> int:
    args = sys.argv[1:]
    if len(args) >= 2 and args[0] == "revoke-historic":
        slug = args[1]
        names: list[str] = []
        rest = args[2:]
        while rest:
            if rest[0] != "--name" or len(rest) < 2:
                print(__doc__)
                return 2
            names.append(rest[1])
            rest = rest[2:]
        return _revoke_historic(slug, names)
    if len(args) == 3:
        _insert(args[0], args[1], args[2])
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main())
