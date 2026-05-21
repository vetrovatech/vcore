"""Add handling_percentage to quotes table"""
import pymysql, os
from urllib.parse import urlparse

url = urlparse(os.environ['DATABASE_URL'].replace('mysql+pymysql://', 'mysql://'))
conn = pymysql.connect(
    host=url.hostname, port=url.port or 3306,
    user=url.username, password=url.password,
    database=url.path.lstrip('/'),
)
cur = conn.cursor()
cur.execute("ALTER TABLE quotes ADD COLUMN handling_percentage DECIMAL(5,2) NOT NULL DEFAULT 1.00;")
conn.commit()
print("Done — handling_percentage column added to quotes")
cur.close()
conn.close()
