import os
from supabase import create_client
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Get Supabase credentials from environment variables
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

# Ensure storage endpoint has trailing slash to satisfy SDK expectations
if SUPABASE_URL and not SUPABASE_URL.endswith("/"):
	SUPABASE_URL = f"{SUPABASE_URL}/"

# Create Supabase client
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
