"""Migrate quote_items.particular from VARCHAR(300) to TEXT"""
import pymysql, os
from urllib.parse import urlparse

url = urlparse(os.environ['DATABASE_URL'].replace('mysql+pymysql://', 'mysql://'))

conn = pymysql.connect(
    host=url.hostname,
    port=url.port or 3306,
    user=url.username,
    password=url.password,
    database=url.path.lstrip('/'),
)
cur = conn.cursor()
cur.execute("ALTER TABLE quote_items MODIFY COLUMN particular TEXT NOT NULL;")
conn.commit()
print("Done — particular is now TEXT (unlimited length)")
cur.close()
conn.close()
