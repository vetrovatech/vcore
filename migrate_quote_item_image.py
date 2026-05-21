"""Add image_s3_key to quote_items"""
import pymysql, os
from urllib.parse import urlparse

url = urlparse(os.environ['DATABASE_URL'].replace('mysql+pymysql://', 'mysql://'))
conn = pymysql.connect(
    host=url.hostname, port=url.port or 3306,
    user=url.username, password=url.password,
    database=url.path.lstrip('/'),
)
cur = conn.cursor()
cur.execute("ALTER TABLE quote_items ADD COLUMN image_s3_key VARCHAR(500) NULL;")
conn.commit()
print("Done — image_s3_key column added to quote_items")
cur.close()
conn.close()
