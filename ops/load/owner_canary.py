"""Read-only positive owner-isolation probe for two marked capacity accounts."""

import argparse
import asyncio
import json
import re
import stat
from pathlib import Path

import httpx

from active_users import validate_base_url


CAMPAIGN_RE = re.compile(r"[a-z0-9][a-z0-9-]{2,31}\Z")
REPO_ROOT = Path(__file__).resolve().parents[2]


def private_fixture_input(path):
    resolved = path.resolve(strict=True)
    if resolved == REPO_ROOT or REPO_ROOT in resolved.parents:
        raise ValueError("Fixture token file must be outside the repository")
    if stat.S_IMODE(resolved.stat().st_mode) & 0o077 or stat.S_IMODE(resolved.parent.stat().st_mode) & 0o077:
        raise ValueError("Fixture token file and directory must be private")
    return resolved


def expected_marker(campaign, index):
    return f"Capacity owner canary {campaign} account {index}"


def assert_owner_content(index, campaign, workspace, conversations):
    own_symbol = ("XRP", "ADA")[index - 1]
    other_symbol = ("ADA", "XRP")[index - 1]
    symbols = {row.get("symbol") for row in workspace.get("watchlist", {}).get("rows", [])}
    if own_symbol not in symbols or other_symbol in symbols:
        raise RuntimeError(f"Owner {index} workspace watchlist isolation failed")
    own_id = f"capacity-owner-{campaign}-{index}"
    other_id = f"capacity-owner-{campaign}-{3 - index}"
    items = {item.get("id"): item.get("title") for item in conversations}
    if items.get(own_id) != expected_marker(campaign, index) or other_id in items:
        raise RuntimeError(f"Owner {index} FINN conversation isolation failed")


async def probe(base_url, fixtures, campaign):
    async with httpx.AsyncClient(base_url=base_url, timeout=20) as client:
        for index, fixture in enumerate(fixtures, 1):
            expected_email = f"capacity+{campaign}-{index:04d}@load.example"
            if fixture.get("email") != expected_email or not fixture.get("user_id") or not fixture.get("access_token"):
                raise ValueError("Fixture file must contain the exact ordered canary campaign accounts")
            headers = {"Authorization": f"Bearer {fixture['access_token']}"}
            identity = await client.get("/api/auth/me", headers=headers)
            if (identity.status_code != 200
                    or identity.json().get("id") != fixture["user_id"]
                    or identity.json().get("email") != expected_email):
                raise RuntimeError(f"Owner {index} identity preflight failed")
            workspace = await client.get("/api/workspace/asset?symbol=BTC", headers=headers)
            conversations = await client.get("/api/assistant/v2/conversations", headers=headers)
            if workspace.status_code != 200 or conversations.status_code != 200:
                raise RuntimeError(f"Owner {index} content GET failed")
            assert_owner_content(index, campaign, workspace.json(), conversations.json())
    return {"campaign": campaign, "owners_checked": 2, "workspace": "isolated", "finn_conversations": "isolated"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--fixtures", required=True, type=Path)
    parser.add_argument("--campaign", required=True)
    parser.add_argument("--allow-production", action="store_true")
    args = parser.parse_args()
    args.base_url = validate_base_url(args.base_url, allow_production=args.allow_production)
    if not CAMPAIGN_RE.fullmatch(args.campaign):
        parser.error("Campaign must be a 3-32 character lowercase slug")
    try:
        fixture_path = private_fixture_input(args.fixtures)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    fixtures = json.loads(fixture_path.read_text())
    if not isinstance(fixtures, list) or len(fixtures) != 2:
        parser.error("Owner canary needs exactly two distinct fixture accounts")
    if len({fixture.get("user_id") for fixture in fixtures if isinstance(fixture, dict)}) != 2:
        parser.error("Owner canary fixture IDs must be distinct")
    print(json.dumps(asyncio.run(probe(args.base_url, fixtures, args.campaign)), sort_keys=True))


if __name__ == "__main__":
    main()
