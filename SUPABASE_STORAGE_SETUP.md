# Supabase Storage Setup - Complete Guide

## ✅ What Has Been Configured

### 1. Environment Variables (.env)
Your `.env` file now contains:
```env
SUPABASE_URL=https://vlxwjiktowwzypadnzun.supabase.co
SUPABASE_KEY=sb_secret_e-N5yCa8RTx6Ggfdh73sOg_sp6Q8SVh
```

### 2. Supabase Client (supabase_client.py)
Updated to load credentials from `.env` instead of hardcoded values:
- ✅ Uses `os.getenv()` to read SUPABASE_URL and SUPABASE_KEY
- ✅ Automatically loads environment variables with `dotenv`

### 3. Complaint Submission Endpoint
Your `/complaints` endpoint in `main.py` already supports:
- ✅ Uploading media files to Supabase storage bucket: **rossa**
- ✅ Storing media URLs in the database
- ✅ Supporting multiple file types:
  - Images: JPEG, PNG
  - Audio: MP3, WAV
  - Video: MP4

### 4. Storage Bucket
- **Bucket Name**: `rossa`
- **Bucket Type**: Public (files can be accessed via public URLs)
- **Upload Path Pattern**: `complaints/{uuid}{file_extension}`

## 🚀 How It Works

### Upload Flow:
1. **Client sends request** to `/complaints` endpoint with form data + media file
2. **API validates** user and file type
3. **File is uploaded** to Supabase storage bucket `rossa`
4. **Public URL** is generated for the uploaded file
5. **Complaint record** is created in database with:
   - `media_type`: "image", "audio", "video", or "text"
   - `media_url`: Public URL to access the file
6. **Response** returned with complaint details and media URL

### Example Upload Path:
```
complaints/e4c8d9a1-2b3c-4d5e-8f9a-1b2c3d4e5f6a.jpg
```

### Example Public URL:
```
https://vlxwjiktowwzypadnzun.supabase.co/storage/v1/object/public/rossa/complaints/e4c8d9a1-2b3c-4d5e-8f9a-1b2c3d4e5f6a.jpg
```

## 📝 Database Schema

The `complaints` table includes these media-related columns:
```sql
media_type VARCHAR(20)   -- 'image', 'audio', 'video', 'text'
media_url  VARCHAR(500)  -- Full public URL to the file
```

## 🧪 Testing

### Run the test script:
```bash
python test_supabase_upload.py
```

This will:
- ✅ Verify connection to Supabase
- ✅ List available buckets
- ✅ Upload a test file to 'rossa' bucket
- ✅ Generate and display the public URL

### Test Results:
```
✅ Upload successful!
Public URL: https://vlxwjiktowwzypadnzun.supabase.co/storage/v1/object/public/rossa/test/...
```

## 📤 How to Submit a Complaint with Media

### Using cURL:
```bash
curl -X POST "http://localhost:8000/complaints" \
  -F "user_id=YOUR_USER_UUID" \
  -F "title=Pothole on Main Street" \
  -F "description=Large pothole causing damage" \
  -F "complaint_type=common" \
  -F "address=Main Street, Downtown" \
  -F "media=@/path/to/image.jpg"
```

### Using Python (requests):
```python
import requests

response = requests.post(
    "http://localhost:8000/complaints",
    data={
        "user_id": "YOUR_USER_UUID",
        "title": "Pothole on Main Street",
        "description": "Large pothole causing damage",
        "complaint_type": "common",
        "address": "Main Street, Downtown"
    },
    files={
        "media": open("image.jpg", "rb")
    }
)

result = response.json()
print(f"Media URL: {result['complaint']['media_url']}")
```

### Using Postman:
1. Set method to **POST**
2. URL: `http://localhost:8000/complaints`
3. Body → form-data:
   - `user_id`: (text) YOUR_USER_UUID
   - `title`: (text) Pothole on Main Street
   - `description`: (text) Large pothole causing damage
   - `complaint_type`: (text) common
   - `address`: (text) Main Street, Downtown
   - `media`: (file) Select your image/audio/video file

## ✨ Features

### Supported File Types:
| Type  | MIME Types          | Extensions    |
|-------|---------------------|---------------|
| Image | image/jpeg, image/png | .jpg, .png    |
| Audio | audio/mpeg, audio/wav | .mp3, .wav    |
| Video | video/mp4            | .mp4          |

### Media Handling:
- ✅ Optional media upload (text-only complaints allowed)
- ✅ Automatic file type detection
- ✅ Unique filename generation (UUID-based)
- ✅ Public URL generation for easy access
- ✅ File validation (type and size)

### Database Integration:
- ✅ Media URL stored in database
- ✅ Media type tracked for filtering
- ✅ Linked to complaint record
- ✅ Accessible via complaint queries

## 🔐 Security Notes

1. **Bucket is PUBLIC** - Anyone with the URL can access files
2. **No authentication required** for file access
3. **File validation** ensures only allowed types are uploaded
4. **UUID filenames** prevent name collisions and guessing

## 🎯 Next Steps

To use this in production:

1. **Start your FastAPI server**:
   ```bash
   uvicorn main:app --reload
   ```

2. **Create a user** (if you haven't):
   ```bash
   POST /register
   ```

3. **Submit a complaint with media**:
   - Use the example script: `example_submit_complaint.py`
   - Or use Postman/cURL as shown above

4. **Access the uploaded file**:
   - The public URL is returned in the response
   - Files are immediately accessible

## 📊 Example Response

```json
{
  "success": true,
  "message": "Complaint submitted successfully",
  "complaint": {
    "id": "e4c8d9a1-2b3c-4d5e-8f9a-1b2c3d4e5f6a",
    "title": "Pothole on Main Street",
    "description": "Large pothole causing damage",
    "complaint_type": "common",
    "address": "Main Street, Downtown",
    "status": "pending",
    "media_type": "image",
    "media_url": "https://vlxwjiktowwzypadnzun.supabase.co/storage/v1/object/public/rossa/complaints/abc123.jpg"
  }
}
```

## 🛠️ Troubleshooting

### Issue: Upload fails
- ✅ Check Supabase credentials in .env
- ✅ Verify bucket 'rossa' exists in Supabase dashboard
- ✅ Ensure bucket is public
- ✅ Check file size limits

### Issue: Public URL not accessible
- ✅ Verify bucket permissions are public
- ✅ Check if file was actually uploaded
- ✅ Try accessing URL in browser

### Issue: Environment variables not loading
- ✅ Ensure .env file is in project root
- ✅ Check for typos in variable names
- ✅ Restart your FastAPI server

---

**✅ Setup Complete!** Your application now uploads media to Supabase storage and stores the data in your database.
