"""Insert an API token by hash. Usage: python add_token.py <org-slug> <name> <sha256>."""
import sys

from reversa_api.db import session_for
from reversa_api.models import ApiToken, Organization


def main() -> None:
    slug, name, hash_ = sys.argv[1], sys.argv[2], sys.argv[3]
    session = session_for("main")()
    org = session.query(Organization).filter_by(slug=slug).first()
    assert org, f"org {slug} missing"
    session.add(ApiToken(org_id=org.id, name=name, token_hash=hash_))
    session.commit()
    print("token-ok")


if __name__ == "__main__":
    main()
