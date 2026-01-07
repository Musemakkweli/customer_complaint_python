from dotenv import load_dotenv
import os, psycopg2, traceback, sys
load_dotenv()
url = os.getenv('DATABASE_URL')
print('Testing DATABASE_URL:', url)
try:
    conn = psycopg2.connect(url, connect_timeout=10)
    print('Connected successfully')
    conn.close()
except Exception:
    traceback.print_exc()
    sys.exit(1)
