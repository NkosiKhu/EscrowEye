from __future__ import annotations

import sqlite3


def seed_demo_data(conn: sqlite3.Connection) -> dict[str, int]:
    now = conn.execute("SELECT datetime('now')").fetchone()[0]
    owner = conn.execute("SELECT * FROM users WHERE hedera_account_id = '0.0.1111'").fetchone()
    if owner is None:
        owner_id = conn.execute(
            "INSERT INTO users (email, user_type, hedera_account_id, hedera_public_key, created_at) VALUES (?, 'owner', '0.0.1111', 'demo-owner-key', ?)",
            ("owner@example.com", now),
        ).lastrowid
    else:
        owner_id = owner["id"]

    supplier = conn.execute("SELECT * FROM users WHERE hedera_account_id = '0.0.2222'").fetchone()
    if supplier is None:
        supplier_id = conn.execute(
            "INSERT INTO users (email, user_type, hedera_account_id, hedera_public_key, created_at) VALUES (?, 'supplier', '0.0.2222', 'demo-supplier-key', ?)",
            ("supplier@example.com", now),
        ).lastrowid
    else:
        supplier_id = supplier["id"]

    existing = conn.execute("SELECT id FROM jobs WHERE title = 'Demo window cleaning escrow'").fetchone()
    if existing:
        return {"owner_id": owner_id, "supplier_id": supplier_id, "job_id": existing["id"]}

    home_id = conn.execute(
        "INSERT INTO homes (owner_user_id, name, address, created_at, updated_at) VALUES (?, 'Demo property', '10b Gerrard Road, Ikoyi, Lagos', ?, ?)",
        (owner_id, now, now),
    ).lastrowid
    job_id = conn.execute(
        """
        INSERT INTO jobs (
            home_id, owner_user_id, supplier_user_id, title, description, suggested_price_tinybar,
            access_notes, available_times, status, hcs_topic_id, creation_fee_paid, created_at, updated_at
        ) VALUES (?, ?, ?, 'Demo window cleaning escrow', 'Clean windows and upload proof for AI validation.',
                  220000000, 'Gate code 1234', 'Sat, 1 Mar 2025', 'escrow_funded', '0.0.88901', 1, ?, ?)
        """,
        (home_id, owner_id, supplier_id, now, now),
    ).lastrowid
    bid_id = conn.execute(
        "INSERT INTO bids (job_id, supplier_user_id, amount_tinybar, message, status, created_at, updated_at) VALUES (?, ?, 220000000, 'Demo quote', 'accepted', ?, ?)",
        (job_id, supplier_id, now, now),
    ).lastrowid
    conn.execute("UPDATE jobs SET accepted_bid_id = ?, escrow_account_id = ? WHERE id = ?", (bid_id, f"0.0.{99000 + job_id}", job_id))
    conn.execute(
        "INSERT INTO audit_events (job_id, type, tx_hash, sequence_number, consensus_timestamp) VALUES (?, 'demo_seeded', 'local:demo_seeded', 1, ?)",
        (job_id, now),
    )
    return {"owner_id": owner_id, "supplier_id": supplier_id, "job_id": job_id}
