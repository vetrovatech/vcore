import pymysql
import os

db_url = os.environ.get('DATABASE_URL', '')
# parse: mysql+pymysql://user:pass@host:port/db
parts = db_url.replace('mysql+pymysql://', '')
user_pass, rest = parts.split('@')
user, password = user_pass.split(':')
host_port, dbname = rest.split('/')
host, port = (host_port.split(':') + ['3306'])[:2]

conn = pymysql.connect(host=host, port=int(port), user=user, password=password, database=dbname)
cur  = conn.cursor()

cur.execute("SHOW COLUMNS FROM quotes LIKE 'cash_received'")
if cur.fetchone():
    print("cash_received already exists, skipping.")
else:
    cur.execute("ALTER TABLE quotes ADD COLUMN cash_received DECIMAL(10,2) NOT NULL DEFAULT 0.00 AFTER amount_received")
    conn.commit()
    print("Added cash_received column to quotes table.")

cur.close()
conn.close()
print("Migration complete.")
