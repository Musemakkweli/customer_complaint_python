"""
Example script demonstrating how to upload media to Supabase storage 
and create a complaint with the uploaded file.

This shows the complete flow:
1. Read credentials from .env
2. Upload file to Supabase 'rossa' bucket
3. Insert complaint data in database
"""
import os
import requests
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Your API endpoint
API_URL = "http://localhost:8000"  # Update if your server runs on a different port

def submit_complaint_with_media(
    user_id: str,
    title: str,
    description: str,
    complaint_type: str,
    address: str,
    media_file_path: str = None
):
    """
    Submit a complaint with optional media file.
    
    Args:
        user_id: UUID of the user submitting the complaint
        title: Title of the complaint
        description: Description of the issue
        complaint_type: Either 'common' or 'private'
        address: Address where the issue occurred
        media_file_path: Path to the media file (image/audio/video)
    """
    
    endpoint = f"{API_URL}/complaints"
    
    # Prepare form data
    data = {
        "user_id": user_id,
        "title": title,
        "description": description,
        "complaint_type": complaint_type,
        "address": address
    }
    
    files = None
    if media_file_path and os.path.exists(media_file_path):
        # Open the file for upload
        files = {
            "media": open(media_file_path, "rb")
        }
    
    try:
        # Make the request
        print(f"\n📤 Submitting complaint to {endpoint}...")
        response = requests.post(endpoint, data=data, files=files)
        
        if response.status_code == 200:
            result = response.json()
            print("\n✅ Complaint submitted successfully!")
            print(f"\nComplaint ID: {result['complaint']['id']}")
            print(f"Title: {result['complaint']['title']}")
            print(f"Status: {result['complaint']['status']}")
            print(f"Media Type: {result['complaint']['media_type']}")
            
            if result['complaint']['media_url']:
                print(f"Media URL: {result['complaint']['media_url']}")
                print("\n🌐 You can access the uploaded file at the URL above")
            
            return result
        else:
            print(f"\n❌ Error: {response.status_code}")
            print(response.json())
            return None
            
    except Exception as e:
        print(f"\n❌ Error submitting complaint: {str(e)}")
        return None
    finally:
        if files and files.get("media"):
            files["media"].close()


def example_text_only_complaint():
    """Example: Submit a text-only complaint"""
    print("\n" + "="*60)
    print("EXAMPLE 1: Text-only complaint")
    print("="*60)
    
    submit_complaint_with_media(
        user_id="YOUR_USER_UUID_HERE",  # Replace with actual user UUID
        title="Street Light Not Working",
        description="The street light on Main Street has been out for 3 days",
        complaint_type="common",
        address="Main Street, Downtown"
    )


def example_complaint_with_image():
    """Example: Submit a complaint with an image"""
    print("\n" + "="*60)
    print("EXAMPLE 2: Complaint with image")
    print("="*60)
    
    # You need to provide the path to an actual image file
    submit_complaint_with_media(
        user_id="YOUR_USER_UUID_HERE",  # Replace with actual user UUID
        title="Pothole on Road",
        description="Large pothole causing traffic issues",
        complaint_type="common",
        address="Highway 45, Mile Marker 12",
        media_file_path="path/to/your/image.jpg"  # Replace with actual file path
    )


def example_complaint_with_audio():
    """Example: Submit a complaint with an audio file"""
    print("\n" + "="*60)
    print("EXAMPLE 3: Complaint with audio")
    print("="*60)
    
    submit_complaint_with_media(
        user_id="YOUR_USER_UUID_HERE",  # Replace with actual user UUID
        title="Noise Complaint",
        description="Excessive noise from construction site",
        complaint_type="private",
        address="Industrial Zone, Sector 5",
        media_file_path="path/to/your/audio.mp3"  # Replace with actual file path
    )


if __name__ == "__main__":
    print("\n" + "="*60)
    print("COMPLAINT SUBMISSION EXAMPLES")
    print("="*60)
    print("\nℹ️  Instructions:")
    print("1. Make sure your FastAPI server is running")
    print("2. Replace 'YOUR_USER_UUID_HERE' with a valid user UUID")
    print("3. Update file paths to point to actual media files")
    print("4. Uncomment the example you want to test")
    print("\n" + "="*60)
    
    # Uncomment one of the examples below to test:
    # example_text_only_complaint()
    # example_complaint_with_image()
    # example_complaint_with_audio()
    
    print("\n✨ Update the script with your details and uncomment an example to test!")
