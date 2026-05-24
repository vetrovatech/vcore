"""One-shot MySQL → Postgres data migration for vcore.

- Creates the `vcore` database on Postgres if missing
- Creates schema from SQLAlchemy models (metadata.create_all)
- Copies every table preserving IDs
- Resets sequences to MAX(id)
"""
import os, re, sys
from sqlalchemy import create_engine, text

with open(os.path.join(os.path.dirname(__file__), '.env')) as f:
    env = dict(re.findall(r'^([A-Z_]+)=(.*)$', f.read(), re.M))

# Both URLs come from .env / process env — never hardcode credentials here.
# Required:
#   MYSQL_URL          — source legacy DB (set as DATABASE_URL when run)
#   PG_URL             — target Postgres URL for the `vcore` database
#   PG_ADMIN_URL       — Postgres URL pointing at the `postgres` admin DB on
#                        the same host (used to CREATE DATABASE vcore)
MYSQL_URL    = env.get('MYSQL_URL')    or os.getenv('MYSQL_URL')    or env.get('DATABASE_URL')
PG_URL       = env.get('PG_URL')       or os.getenv('PG_URL')
PG_ADMIN_URL = env.get('PG_ADMIN_URL') or os.getenv('PG_ADMIN_URL')
if not (MYSQL_URL and PG_URL and PG_ADMIN_URL):
    sys.exit("Set MYSQL_URL, PG_URL, PG_ADMIN_URL in .env before running this migration.")

# Step 1: ensure vcore database exists
admin = create_engine(PG_ADMIN_URL, isolation_level="AUTOCOMMIT")
with admin.connect() as c:
    if not c.execute(text("SELECT 1 FROM pg_database WHERE datname='vcore'")).scalar():
        c.execute(text("CREATE DATABASE vcore"))
        print("→ created database 'vcore'")
    else:
        print("→ database 'vcore' already exists")

# Step 2: load models metadata and create schema on PG
from app import app, db  # noqa
pg = create_engine(PG_URL)
print(f"→ creating {len(db.metadata.tables)} tables on postgres…")
db.metadata.create_all(pg)
print("→ schema created")

# Step 3: copy data, in FK-safe order
mysql = create_engine(MYSQL_URL)
total_rows = 0
for table in db.metadata.sorted_tables:
    with mysql.connect() as src:
        rows = [dict(r._mapping) for r in src.execute(table.select())]
    if not rows:
        print(f"   {table.name:24} (empty)")
        continue
    with pg.begin() as dst:
        # Wipe in case of partial prior run
        dst.execute(text(f'TRUNCATE "{table.name}" RESTART IDENTITY CASCADE'))
        dst.execute(table.insert(), rows)
    print(f"   {table.name:24} {len(rows):>5} rows")
    total_rows += len(rows)
print(f"→ total {total_rows} rows copied")

# Step 4: reset sequences to MAX(id)
print("→ resetting sequences…")
with pg.begin() as c:
    for table in db.metadata.tables.values():
        pk_cols = [col for col in table.primary_key.columns if col.autoincrement]
        if not pk_cols:
            continue
        pk = pk_cols[0]
        seq = c.execute(text("SELECT pg_get_serial_sequence(:t, :c)"),
                        {"t": table.name, "c": pk.name}).scalar()
        if not seq:
            continue
        max_id = c.execute(text(f'SELECT COALESCE(MAX("{pk.name}"), 0) FROM "{table.name}"')).scalar()
        next_val = max_id + 1
        c.execute(text(f"SELECT setval(:s, :v, false)"), {"s": seq, "v": next_val})
        print(f"   {table.name:24} seq → {next_val}")

print("\n✅ Migration complete.")
