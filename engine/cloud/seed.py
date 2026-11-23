"""Optional first-boot admin seed for hosted deployments.

No-op unless CLIPFORGE_SEED_ADMIN=1. The local desktop/dev server keeps its own
database and is never modified by this module.
"""

from __future__ import annotations

import os

from . import accounts


def admin() -> None:
    if os.getenv("CLIPFORGE_SEED_ADMIN", "").strip() != "1":
        return
    email = os.getenv("CLIPFORGE_ADMIN_EMAIL", "").strip().lower()
    password = os.getenv("CLIPFORGE_ADMIN_PASSWORD", "")
    if not email or not password:
        return

    accounts.init()
    with accounts.connection() as conn:
        row = conn.execute("SELECT id FROM users WHERE email=?", (email,)).fetchone()
        if row:
            conn.execute(
                "UPDATE teams SET plan='Studio' WHERE id IN "
                "(SELECT team_id FROM members WHERE user_id=? AND role='owner')",
                (row["id"],),
            )
            return

    accounts.account(email, password, True)
    with accounts.connection() as conn:
        uid = conn.execute("SELECT id FROM users WHERE email=?", (email,)).fetchone()[0]
        conn.execute(
            "UPDATE teams SET plan='Studio' WHERE id IN "
            "(SELECT team_id FROM members WHERE user_id=? AND role='owner')",
            (uid,),
        )
