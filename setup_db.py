import psycopg2
import os

DATABASE_URL = "postgresql://postgres.vlxwjiktowwzypadnzun:1NAzkfoMm0n0TPIl@aws-1-eu-central-2.pooler.supabase.com:6543/postgres?sslmode=require"

# Connect to Supabase database
conn = psycopg2.connect(DATABASE_URL)
cur = conn.cursor()

# Create table if it doesn't exist
cur.execute("""
CREATE TABLE IF NOT EXISTS uploaded_files (
    id SERIAL PRIMARY KEY,
    file_name TEXT NOT NULL,
    file_path TEXT NOT NULL,
    public_url TEXT NOT NULL,
    uploaded_at TIMESTAMP DEFAULT NOW()
)
""")

conn.commit()
cur.close()
conn.close()
print("Table 'uploaded_files' ready in Supabase!")
