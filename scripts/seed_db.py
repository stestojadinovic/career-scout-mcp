"""Seed the scout database with synthetic postings from data/seed_postings.sql.

Idempotent: drops existing synth-* rows before inserting. Safe to re-run.

Usage:
    cd career-scout-mcp
    uv run python scripts/seed_db.py
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from career_scout_mcp.storage import db


REPO_ROOT = Path(__file__).resolve().parent.parent
SEED_FILE = REPO_ROOT / "data" / "seed_postings.sql"


async def main() -> None:
    await db.init_schemas()
    statements = SEED_FILE.read_text(encoding="utf-8")

    async with db.scout_connection() as conn:
        # Clear prior synth-* rows so the seed is idempotent
        await conn.execute("DELETE FROM postings WHERE id LIKE 'synth-%'")
        # Execute the whole SQL file as a single script
        await conn.executescript(statements)
        await conn.commit()

    print(f"Seeded synthetic postings from {SEED_FILE.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    asyncio.run(main())
