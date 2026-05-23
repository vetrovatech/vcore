"""
One-off: copy existing rows from glassyplatform's `bathspace_quotes` table
into vcore's `bathqube_quotes` table.

Idempotent — skips rows whose external_id is already present in vcore.

Run via docker-compose:
    docker-compose run --rm vcore python backfill_bathqube_quotes.py

The glassy DB URL is read from GLASSY_DATABASE_URL env var; falls back to the
known shared RDS host used by both apps.
"""

import json
import os
import psycopg2
import psycopg2.extras

from app import app, db
from models import BathqubeQuote


GLASSY_DSN = os.getenv(
    'GLASSY_DATABASE_URL',
    'postgresql://dbmasteruser:myvetropgpwd@ls-bcf74fccc09e57a790a55363aa6f915516415ae9.c7cuq02uskcx.ap-south-1.rds.amazonaws.com:5432/glassy_platform?sslmode=require',
)


def _f(cfg, key, default=0):
    """Safe numeric pull from configData."""
    if not isinstance(cfg, dict):
        return default
    v = cfg.get(key)
    try:
        return float(v) if v is not None else default
    except (TypeError, ValueError):
        return default


def backfill():
    print(f"Reading from glassy: {GLASSY_DSN.split('@')[-1].split('?')[0]}")
    conn = psycopg2.connect(GLASSY_DSN)
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("""
        SELECT id, name, phone, email, pincode, variant_size, variant_material,
               source_path, config_data, estimate_number, created_at
        FROM bathspace_quotes
        ORDER BY id ASC
    """)
    rows = cur.fetchall()
    cur.close()
    conn.close()
    print(f"Found {len(rows)} bathspace_quotes rows on glassy.\n")

    inserted = 0
    skipped = 0
    skipped_no_name = 0

    with app.app_context():
        for r in rows:
            ext = str(r['id'])

            # Skip duplicates
            if BathqubeQuote.query.filter_by(external_id=ext).first():
                skipped += 1
                continue

            name = (r.get('name') or '').strip()
            phone = (r.get('phone') or '').strip()
            if not name or not phone:
                # Required fields in vcore — skip incomplete legacy rows
                skipped_no_name += 1
                print(f"  skip id={ext}: missing name or phone")
                continue

            cfg = r.get('config_data') or {}
            if isinstance(cfg, str):
                try:
                    cfg = json.loads(cfg)
                except Exception:
                    cfg = {}

            q = BathqubeQuote(
                external_id=ext,
                estimate_number=r.get('estimate_number'),
                customer_name=name,
                phone=phone,
                email=r.get('email') or None,
                pincode=r.get('pincode') or None,
                site_address=(cfg.get('siteAddress') if isinstance(cfg, dict) else None) or None,
                source_path=r.get('source_path') or None,
                variant_size=r.get('variant_size') or None,
                variant_material=r.get('variant_material') or None,
                config_data=json.dumps(cfg) if cfg else None,
                subtotal=_f(cfg, 'subtotal'),
                cgst=_f(cfg, 'cgst'),
                sgst=_f(cfg, 'sgst'),
                total=_f(cfg, 'total'),
                stage='order_confirmation',
            )
            # Preserve original created_at if available
            if r.get('created_at'):
                q.created_at = r['created_at'].replace(tzinfo=None)
            db.session.add(q)
            inserted += 1
            print(f"  +  id={ext} {q.estimate_number or '(no estimate#)'} {name}")

        db.session.commit()

    print(f"\nDone. inserted={inserted}  skipped_already_present={skipped}  skipped_missing_required={skipped_no_name}")


if __name__ == '__main__':
    backfill()
