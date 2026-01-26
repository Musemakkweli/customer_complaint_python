"""
Test script to verify Supabase storage upload to 'rossa' bucket
"""
import os
from dotenv import load_dotenv
from supabase import create_client
from uuid import uuid4

# Load environment variables
load_dotenv()

# Get Supabase credentials
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

print(f"SUPABASE_URL: {SUPABASE_URL}")
print(f"SUPABASE_KEY: {SUPABASE_KEY[:20]}...")

# Create Supabase client
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

def test_upload():
    """Test uploading a sample file to rossa bucket"""
    try:
        # Create a test file content
        test_content = b"This is a test file for Supabase storage upload"
        
        # Generate unique filename
        filename = f"test/{uuid4()}.txt"
        
        print(f"\nAttempting to upload to 'rossa' bucket...")
        print(f"File path: {filename}")
        
        # Upload to Supabase Storage
        response = supabase.storage.from_("rossa").upload(filename, test_content)
        
        print(f"\nUpload response: {response}")
        
        # Get public URL
        public_url = supabase.storage.from_("rossa").get_public_url(filename)
        print(f"Public URL: {public_url}")
        
        print("\n✅ Upload successful!")
        return True
        
    except Exception as e:
        print(f"\n❌ Upload failed: {str(e)}")
        return False

def list_buckets():
    """List all available buckets"""
    try:
        print("\nListing all buckets...")
        buckets = supabase.storage.list_buckets()
        print(f"Available buckets: {buckets}")
    except Exception as e:
        print(f"Error listing buckets: {str(e)}")

if __name__ == "__main__":
    print("=" * 50)
    print("SUPABASE STORAGE TEST")
    print("=" * 50)
    
    # List buckets first
    list_buckets()
    
    # Test upload
    test_upload()
    
    print("\n" + "=" * 50)
