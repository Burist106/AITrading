"""Local historical decision verification, without native or network imports."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path
from uuid import UUID

from aurum_worker.shadow.replay import verify_replay
from aurum_worker.shadow.replay_archive import SqliteReplayArchive


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Verify one local DEMO ONLY / SHADOW historical decision"
    )
    parser.add_argument("--archive", required=True)
    parser.add_argument("--owner-id", required=True)
    parser.add_argument("--account-id", required=True)
    parser.add_argument("--cycle-id", required=True)
    args = parser.parse_args(argv)
    try:
        owner, account, cycle = (
            UUID(args.owner_id),
            UUID(args.account_id),
            UUID(args.cycle_id),
        )
        archive = SqliteReplayArchive(
            Path(args.archive),
            owner_id=owner,
            trading_account_id=account,
            read_only=True,
        )
        envelope = archive.read(cycle)
        if envelope is None:
            print("REPLAY: UNAVAILABLE / REPLAY_RECORD_NOT_FOUND")
            return 2
        result = verify_replay(envelope, owner_id=owner, trading_account_id=account)
    except Exception:
        print("REPLAY: UNAVAILABLE / REPLAY_ARCHIVE_UNAVAILABLE")
        return 2
    print(f"REPLAY: {result.status} / {result.code}")
    print(
        "LOCAL HISTORICAL CHECK ONLY. No remote confirmation, source authentication, "
        "current readiness or trading permission."
    )
    return {"MATCH": 0, "MISMATCH": 1, "UNAVAILABLE": 2}[result.status]


if __name__ == "__main__":
    raise SystemExit(main())
