"""
Complete workflow demonstration:
1. Upload media to Supabase storage (rossa bucket)
2. Insert complaint data in database
3. Verify the data was stored correctly
"""
import os
import sys
from pathlib import Path
from uuid import uuid4
from dotenv import load_dotenv
from supabase import create_client

# Load environment variables
load_dotenv()

# Get credentials
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

# Create client
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

def upload_to_storage(file_path: str) -> dict:
    """
    Upload a file to Supabase storage (rossa bucket)
    
    Returns:
        dict with 'success', 'storage_path', and 'public_url'
    """
    try:
        # Read file
        with open(file_path, 'rb') as f:
            file_bytes = f.read()
        
        # Get file extension
        file_ext = Path(file_path).suffix
        
        # Generate unique storage path
        storage_path = f"complaints/{uuid4()}{file_ext}"
        
        print(f"\n📤 Uploading file to rossa bucket...")
        print(f"   Local path: {file_path}")
        print(f"   Storage path: {storage_path}")
        
        # Upload to Supabase
        response = supabase.storage.from_("rossa").upload(storage_path, file_bytes)
        
        # Get public URL
        public_url = supabase.storage.from_("rossa").get_public_url(storage_path)
        
        print(f"\n✅ Upload successful!")
        print(f"   Public URL: {public_url}")
        
        return {
            "success": True,
            "storage_path": storage_path,
            "public_url": public_url
        }
        
    except Exception as e:
        print(f"\n❌ Upload failed: {str(e)}")
        return {
            "success": False,
            "error": str(e)
        }


def insert_complaint_to_db(
    user_id: str,
    title: str,
    description: str,
    complaint_type: str,
    address: str,
    media_type: str = "text",
    media_url: str = None
) -> dict:
    """
    Insert complaint data into Supabase database
    
    Returns:
        dict with complaint data or error
    """
    try:
        print(f"\n💾 Inserting complaint into database...")
        
        complaint_data = {
            "user_id": user_id,
            "title": title,
            "description": description,
            "complaint_type": complaint_type,
            "address": address,
            "status": "pending",
            "media_type": media_type,
            "media_url": media_url
        }
        
        # Insert into database
        response = supabase.table("complaints").insert(complaint_data).execute()
        
        print(f"✅ Complaint inserted successfully!")
        print(f"   Complaint ID: {response.data[0]['id']}")
        
        return {
            "success": True,
            "data": response.data[0]
        }
        
    except Exception as e:
        print(f"\n❌ Database insertion failed: {str(e)}")
        return {
            "success": False,
            "error": str(e)
        }


def complete_workflow_example():
    """
    Demonstrate the complete workflow:
    1. Upload media file
    2. Insert complaint with media URL
    """
    print("\n" + "="*70)
    print("COMPLETE WORKFLOW: Upload Media + Insert to Database")
    print("="*70)
    
    # Example: Create a sample text file to upload
    sample_file = "sample_complaint_image.txt"
    with open(sample_file, 'w') as f:
        f.write("This is a sample complaint evidence file.")
    
    print(f"\n📄 Created sample file: {sample_file}")
    
    # Step 1: Upload to storage
    upload_result = upload_to_storage(sample_file)
    
    if not upload_result["success"]:
        print("\n❌ Workflow stopped: Upload failed")
        return
    
    # Step 2: Insert to database
    # NOTE: Replace this with a real user_id from your database
    user_id = "00000000-0000-0000-0000-000000000000"  # Placeholder
    
    db_result = insert_complaint_to_db(
        user_id=user_id,
        title="Sample Complaint with Media",
        description="This is a test complaint demonstrating media upload",
        complaint_type="common",
        address="Test Street, Sample City",
        media_type="image",
        media_url=upload_result["public_url"]
    )
    
    # Cleanup
    os.remove(sample_file)
    print(f"\n🧹 Cleaned up sample file")
    
    if db_result["success"]:
        print("\n" + "="*70)
        print("✅ WORKFLOW COMPLETED SUCCESSFULLY!")
        print("="*70)
        print("\n📊 Summary:")
        print(f"   - File uploaded to: rossa bucket")
        print(f"   - Storage path: {upload_result['storage_path']}")
        print(f"   - Public URL: {upload_result['public_url']}")
        print(f"   - Complaint ID: {db_result['data']['id']}")
        print(f"   - Status: {db_result['data']['status']}")
        print("\n🌐 You can access the file at the public URL")
    else:
        print("\n❌ Workflow completed with errors")


def list_recent_complaints(limit: int = 5):
    """
    List recent complaints from database
    """
    try:
        print(f"\n📋 Fetching {limit} most recent complaints...")
        
        response = supabase.table("complaints")\
            .select("*")\
            .order("created_at", desc=True)\
            .limit(limit)\
            .execute()
        
        print(f"\n✅ Found {len(response.data)} complaints:")
        
        for i, complaint in enumerate(response.data, 1):
            print(f"\n   {i}. {complaint.get('title', 'No title')}")
            print(f"      ID: {complaint.get('id')}")
            print(f"      Type: {complaint.get('complaint_type')}")
            print(f"      Status: {complaint.get('status')}")
            print(f"      Media: {complaint.get('media_type', 'text')}")
            if complaint.get('media_url'):
                print(f"      URL: {complaint.get('media_url')[:60]}...")
        
    except Exception as e:
        print(f"\n❌ Error fetching complaints: {str(e)}")


if __name__ == "__main__":
    print("\n" + "="*70)
    print("SUPABASE STORAGE & DATABASE WORKFLOW")
    print("="*70)
    
    print("\nℹ️  This script demonstrates:")
    print("   1. Uploading files to Supabase storage (rossa bucket)")
    print("   2. Inserting complaint data with media URLs into database")
    print("   3. Querying complaints from database")
    
    # Run the complete workflow
    complete_workflow_example()
    
    # List recent complaints
    print("\n" + "="*70)
    list_recent_complaints(5)
    
    print("\n" + "="*70)
    print("🎉 Done!")
    print("="*70)
