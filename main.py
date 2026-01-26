# -------------------- IMPORTS --------------------
import os
import shutil
import random
import asyncio
from pydantic import BaseModel
from uuid import UUID, uuid4
from datetime import datetime, timedelta
from pathlib import Path
from fastapi import (
    FastAPI, UploadFile, File, Form, Depends, HTTPException,
    APIRouter, WebSocket, WebSocketDisconnect, Request, Body
)
from fastapi.security import OAuth2PasswordBearer
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi_mail import ConnectionConfig, FastMail, MessageSchema

from supabase_client import supabase

from sqlalchemy.orm import Session
from sqlalchemy import or_, func

from passlib.context import CryptContext
import bcrypt
import jwt

# -------------------- LOAD ENVIRONMENT --------------------
from dotenv import load_dotenv

# Load .env from the current directory
load_dotenv()

# Debug: check if env variables are loaded correctly
print("MAIL_USERNAME:", os.getenv("MAIL_USERNAME"))
print("MAIL_PASSWORD:", os.getenv("MAIL_PASSWORD"))
print("MAIL_SERVER:", os.getenv("MAIL_SERVER"))
print("MAIL_FROM:", os.getenv("MAIL_FROM"))

# -------------------- DATABASE AND MODELS --------------------
from database import engine, SessionLocal, Base
from models import UserProfile, User, Complaint, Notification, UserOTP
from schemas import (
    UserProfileCreateSchema,
    RegisterSchema,
    LoginSchema,
    UserResponse,
    UpdateRoleSchema,
    UpdateEmployeeIDSchema,
    ComplaintCreateSchema,
    ComplaintResponseSchema,
    EmployeeSchema,
    AssignComplaintSchema,
    UpdateComplaintStatusSchema,
    UserProfileUpdate
)
from utils.notifications import create_notification
from supabase import create_client, Client

# -------------------- EMAIL CONFIGURATION --------------------
conf = ConnectionConfig(
    MAIL_USERNAME=os.getenv("MAIL_USERNAME"),
    MAIL_PASSWORD=os.getenv("MAIL_PASSWORD"),
    MAIL_FROM=os.getenv("MAIL_FROM"),
    MAIL_PORT=int(os.getenv("MAIL_PORT", 587)),  # default to 587
    MAIL_SERVER=os.getenv("MAIL_SERVER"),
    MAIL_STARTTLS=os.getenv("MAIL_STARTTLS") == "True",
    MAIL_SSL_TLS=os.getenv("MAIL_SSL_TLS") == "True",
    USE_CREDENTIALS=os.getenv("USE_CREDENTIALS") == "True",
    VALIDATE_CERTS=os.getenv("VALIDATE_CERTS") == "True"
)

fm = FastMail(conf)

# ---------------------- CONFIGURATION ----------------------
SECRET_KEY = os.getenv("SECRET_KEY", "change-me-please")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", 60))

pwd_context = CryptContext(
    schemes=["argon2", "pbkdf2_sha256"],
    deprecated="auto"
)

BCRYPT_MAX_BYTES = 72
BCRYPT_PREFIXES = ("$2a$", "$2b$", "$2y$")

def _is_bcrypt_hash(hash_value: str | None) -> bool:
    return bool(hash_value) and hash_value.startswith(BCRYPT_PREFIXES)

def _bcrypt_safe_password_bytes(password: str) -> bytes:
    return password.encode("utf-8")[:BCRYPT_MAX_BYTES]

def _verify_bcrypt_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(_bcrypt_safe_password_bytes(password), hashed.encode("utf-8"))
    except ValueError:
        return False

def _verify_password(password: str, hashed: str | None) -> bool:
    if not hashed:
        return False
    if _is_bcrypt_hash(hashed):
        return _verify_bcrypt_password(password, hashed)
    return pwd_context.verify(password, hashed)
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/login")

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Customer Complaint System")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------- DATABASE CONNECTION ----------------------
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# ---------------------- JWT UTILITIES ----------------------
def create_access_token(data: dict, expires_delta=None):
    to_encode = data.copy()
    expire = datetime.utcnow() + (
        expires_delta if expires_delta else timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    ex = HTTPException(
        status_code=401,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        identifier = payload.get("sub")
        if identifier is None:
            raise ex
    except Exception:
        raise ex

    user = db.query(User).filter(
        (User.email == identifier) | (User.employee_id == identifier)
    ).first()
    if not user:
        raise ex
    return user

# ---------------------- ROUTES ----------------------
@app.get("/")
def root():
    return {"message": "Customer Complaint API is running!"}

# ---------------------- REGISTER ----------------------
@app.post("/register")
def register(data: RegisterSchema, db: Session = Depends(get_db)):
    existing = db.query(User).filter(User.email == data.email).first()
    if existing:
        raise HTTPException(400, "Email already registered")

    if data.role == "customer":
        if not data.password:
            raise HTTPException(400, "Password is required for customers")
        employee_id = None
    else:
        if not data.employee_id:
            raise HTTPException(400, "Employee ID is required for employees or admins")
        employee_id = data.employee_id

    hashed_password = pwd_context.hash(data.password) if data.password else None

    new_user = User(
        fullname=data.fullname,
        phone=data.phone,
        email=data.email,
        password=hashed_password,
        employee_id=employee_id,
        role=data.role
    )

    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    return {"message": f"{data.role.capitalize()} registered successfully"}

# ---------------------- LOGIN ----------------------

@app.post("/login")
def login(data: LoginSchema, db: Session = Depends(get_db)):
    filters = []
    if data.employee_id:
        filters.append(User.employee_id == data.employee_id)

    if data.email:
        if "@" in data.email:
            filters.append(User.email == data.email)
        else:
            filters.append(User.employee_id == data.email)

    if not filters:
        raise HTTPException(status_code=400, detail="Email/identifier is required for login")

    user = db.query(User).filter(or_(*filters)).first()
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Verify password against hash (handle legacy bcrypt separately)
    if not _verify_password(data.password, user.password):
        raise HTTPException(status_code=400, detail="Incorrect password")

    needs_rehash = (
        _is_bcrypt_hash(user.password)
        or pwd_context.needs_update(user.password)
    )
    if needs_rehash:
        user.password = pwd_context.hash(data.password)
        db.commit()
        db.refresh(user)
    
    login_identifier = user.email if user.role in ["customer", "admin"] else user.employee_id
    
    token = create_access_token(
        {"sub": login_identifier, "role": user.role},
        expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    
    return {
        "message": "Login successful",
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "id": str(user.id),
            "fullname": user.fullname,
            "email": user.email,
            "role": user.role,
            "employee_id": user.employee_id
        }
    }

# ---------------------- CURRENT USER ----------------------
@app.get("/me")
def read_me(current_user: User = Depends(get_current_user)):
    return {
        "id": str(current_user.id),
        "fullname": current_user.fullname,
        "email": current_user.email if current_user.role == "customer" else current_user.employee_id,
        "role": current_user.role,
    }

# ---------------------- GET ALL USERS ----------------------
@app.get("/users", response_model=list[UserResponse])
def get_all_users(db: Session = Depends(get_db)):
    users = db.query(User).all()
    return [
        UserResponse(
            id=user.id,
            fullname=user.fullname,
            phone=user.phone,
            email=user.email if user.email and "@" in user.email else None,
            role=user.role,
            employee_id=user.employee_id
        )
        for user in users
    ]

# ---------------------- UPDATE ROLE ----------------------
@app.put("/users/{user_id}/role")
def update_role(user_id: str, data: UpdateRoleSchema, db: Session = Depends(get_db)):
    allowed = ["customer", "employee", "admin"]
    if data.role not in allowed:
        raise HTTPException(400, "Invalid role")

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(404, "User not found")

    user.role = data.role
    if data.role == "customer":
        user.employee_id = None

    db.commit()
    db.refresh(user)

    return {"message": "Role updated successfully"}

# ---------------------- UPDATE EMPLOYEE ID ----------------------
@app.put("/users/{user_id}/employee-id")
def update_employee_id(user_id: str, data: UpdateEmployeeIDSchema, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(404, "User not found")
    if user.role != "employee":
        raise HTTPException(400, "Only employees can have an employee_id")
    user.employee_id = data.employee_id
    db.commit()
    db.refresh(user)
    return {"message": "Employee ID updated successfully"}

# ---------------------- CREATE COMPLAINT ----------------------

@app.post("/complaints")
async def submit_complaint(
    user_id: str = Form(...),
    title: str = Form(...),
    description: str = Form(None),
    complaint_type: str = Form(...),
    address: str = Form(...),
    media: UploadFile = File(None),
    db: Session = Depends(get_db)  # Your DB dependency
):
    # -----------------------------
    # 1. Validate user
    # -----------------------------
    try:
        user_uuid = UUID(user_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid user_id UUID")

    user = db.query(User).filter(User.id == user_uuid).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.role != "customer":
        raise HTTPException(status_code=403, detail="Only customers can submit complaints")

    # -----------------------------
    # 2. Validate content
    # -----------------------------
    if (not description or description.strip() == "") and not media:
        raise HTTPException(
            status_code=400,
            detail="You must provide either a description or a media file"
        )

    media_type = "text"
    media_url = None

    # -----------------------------
    # 3. Handle media upload (Supabase Storage)
    # -----------------------------
    if media:
        allowed_types = {
            "image/jpeg": "image",
            "image/png": "image",
            "audio/mpeg": "audio",
            "audio/wav": "audio",
            "video/mp4": "video"
        }

        if media.content_type not in allowed_types:
            raise HTTPException(status_code=400, detail="Unsupported file type")

        file_ext = Path(media.filename).suffix
        storage_path = f"complaints/{uuid4()}{file_ext}"

        # Read file bytes
        file_bytes = await media.read()

        try:
            # Upload to Supabase
            upload_response = supabase.storage.from_("rossa").upload(storage_path, file_bytes)

            # Check for errors (UploadResponse has .error attr, not subscriptable)
            if getattr(upload_response, "error", None):
                raise Exception(upload_response.error.message)

            # Get public URL (this returns a string)
            media_url = supabase.storage.from_("rossa").get_public_url(storage_path)
            media_type = allowed_types[media.content_type]

        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to upload media: {str(e)}")

    # -----------------------------
    # 4. Create complaint in DB
    # -----------------------------
    new_complaint = Complaint(
        user_id=user_uuid,
        title=title,
        description=description,
        complaint_type=complaint_type,
        address=address,
        status="pending",
        media_type=media_type,
        media_url=media_url
    )

    db.add(new_complaint)
    db.commit()
    db.refresh(new_complaint)

    # -----------------------------
    # 5. Return response
    # -----------------------------
    return {
        "success": True,
        "message": "Complaint submitted successfully",
        "complaint": {
            "id": str(new_complaint.id),
            "title": title,
            "description": description,
            "complaint_type": complaint_type,
            "address": address,
            "status": "pending",
            "media_type": media_type,
            "media_url": media_url
        }
    }
    # ----------------------------------------
    # CREATE NOTIFICATION FOR ADMIN
    # ----------------------------------------
    admin = db.query(User).filter(User.role == "admin").first()
    notification_admin = None
    if admin:
        notification_admin = Notification(
            user_id=admin.id,
            sender_id=user.id,  # the user who submitted the complaint
            complaint_id=new_complaint.id,
            type="new_complaint",
            title="New Complaint Submitted",
            message=f"User '{user.fullname}' submitted a new complaint: '{new_complaint.title}'.",
        )
        db.add(notification_admin)

    # ----------------------------------------
    # OPTIONAL: CREATE NOTIFICATION FOR USER
    # ----------------------------------------
    notification_user = Notification(
        user_id=user.id,
        sender_id=None,  # system
        complaint_id=new_complaint.id,
        type="submitted",
        title="Complaint Submitted",
        message=f"Your complaint '{new_complaint.title}' has been submitted successfully.",
    )
    db.add(notification_user)

    db.commit()
    if admin:
        db.refresh(notification_admin)
    db.refresh(notification_user)

    return {
        "message": "Complaint submitted successfully",
        "complaint_id": str(new_complaint.id),
        "notification_admin_id": str(notification_admin.id) if admin else None,
        "notification_user_id": str(notification_user.id)
    }

# ---------------------- GET ALL COMPLAINTS ----------------------
@app.get("/complaints")
def get_all_complaints(db: Session = Depends(get_db)):
    complaints = db.query(Complaint).all()

    response = []

    for c in complaints:
        user = db.query(User).filter(User.id == c.user_id).first()

        response.append({
            "id": str(c.id),
            "user_fullname": user.fullname if user else None,  # 👈 changed
            "title": c.title,
            "description": c.description,
            "complaint_type": c.complaint_type,
            "address": c.address,
            "status": c.status,
            "assigned_to": c.assigned_to,
            "created_at": c.created_at.isoformat() if c.created_at else None,
            "updated_at": c.updated_at.isoformat() if c.updated_at else None
        })

    return response
@app.put("/complaints/{complaint_id}/assign")
def assign_complaint(complaint_id: UUID, data: AssignComplaintSchema, db: Session = Depends(get_db)):
    complaint = db.query(Complaint).filter(Complaint.id == complaint_id).first()
    if not complaint:
        raise HTTPException(status_code=404, detail="Complaint not found")

    employee = db.query(User).filter(
        User.employee_id == data.employee_id,
        User.role == "employee"
    ).first()
    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found")

    # Assign complaint
    complaint.assigned_to = data.employee_id
    complaint.status = "assigned"
    db.commit()
    db.refresh(complaint)

    # ----------------------------------------
    # CREATE NOTIFICATION FOR EMPLOYEE
    # ----------------------------------------
    notification_employee = Notification(
        user_id=employee.id,
        sender_id=None,
        complaint_id=complaint.id,
        type="assigned",
        title="New Task Assigned",
        message=f"You have been assigned to complaint: {complaint.title}",
    )
    db.add(notification_employee)

    # ----------------------------------------
    # CREATE NOTIFICATION FOR USER
    # ----------------------------------------
    notification_user = Notification(
        user_id=complaint.user_id,
        sender_id=None,
        complaint_id=complaint.id,
        type="assigned",
        title="Your Complaint Has Been Assigned",
        message=f"Your complaint '{complaint.title}' has been assigned to {employee.fullname}.",
    )
    db.add(notification_user)

    db.commit()
    db.refresh(notification_employee)
    db.refresh(notification_user)

    return {
        "message": f"Complaint assigned to {employee.fullname} successfully",
        "employee_notification_id": str(notification_employee.id),
        "user_notification_id": str(notification_user.id)
    }

# ---------------------- GET ALL EMPLOYEES ----------------------
@app.get("/employees", response_model=list[dict])
def get_all_employees(db: Session = Depends(get_db)):
    employees = db.query(User).filter(User.role == "employee").all()
    
    response = []
    for emp in employees:
        assigned_count = db.query(Complaint).filter(Complaint.assigned_to == emp.employee_id).count()
        response.append({
            "id": str(emp.id),
            "name": emp.fullname,
            "email": emp.email,
            "employee_id": emp.employee_id,
            "position": getattr(emp, "position", None),  # Optional field
            "assigned_complaints_count": assigned_count
        })
    
    return response
# ---------------------- GET COMPLAINTS BY USER ----------------------
@app.get("/complaints/user/{user_id}")
def get_complaints_by_user(user_id: UUID, db: Session = Depends(get_db)):
    # Fetch all complaints for the given user
    complaints = db.query(Complaint).filter(Complaint.user_id == user_id).all()

    if not complaints:
        return {"message": "No complaints found for this user", "data": []}

    results = []
    for c in complaints:
        # Get employee UUID if assigned
        employee_uuid = None
        if c.assigned_to:
            employee = db.query(User).filter(User.employee_id == c.assigned_to).first()
            if employee:
                employee_uuid = str(employee.id)

        results.append({
            "id": str(c.id),
            "user_id": str(c.user_id),
            "title": c.title,
            "description": c.description,
            "complaint_type": c.complaint_type,
            "address": c.address,
            "status": c.status,
            "assigned_to": c.assigned_to,    # Employee code
            "employee_id": employee_uuid,    # Employee UUID
            "created_at": c.created_at.isoformat() if c.created_at else None,
            "updated_at": c.updated_at.isoformat() if c.updated_at else None
        })

    return results


# ---------------------- USER-SPECIFIC COMPLAINT STATISTICS ----------------------
@app.get("/complaints/stats/user/{user_id}")
def user_complaint_statistics(user_id: UUID, db: Session = Depends(get_db)):

    # Count complaints submitted by this user
    total = db.query(Complaint).filter(Complaint.user_id == user_id).count()

    # Count status types for this user
    pending = db.query(Complaint).filter(
        Complaint.user_id == user_id,
        Complaint.status == "pending"
    ).count()

    resolved = db.query(Complaint).filter(
        Complaint.user_id == user_id,
        Complaint.status == "resolved"
    ).count()

    in_progress = db.query(Complaint).filter(
        Complaint.user_id == user_id,
        Complaint.status == "in_progress"
    ).count()

    assigned = db.query(Complaint).filter(
        Complaint.user_id == user_id,
        Complaint.status == "assigned"
    ).count()

    # Count complaint types (common / private)
    common = db.query(Complaint).filter(
        Complaint.user_id == user_id,
        Complaint.complaint_type == "common"
    ).count()

    private = db.query(Complaint).filter(
        Complaint.user_id == user_id,
        Complaint.complaint_type == "private"
    ).count()

    # Count recent complaints (created in last 7 days)
    seven_days_ago = datetime.utcnow() - timedelta(days=7)
    recent = db.query(Complaint).filter(
        Complaint.user_id == user_id,
        Complaint.created_at >= seven_days_ago
    ).count()

    # Return packed statistics for frontend use
    return {
        "user_id": str(user_id),
        "total_complaints": total,
        "pending": pending,
        "resolved": resolved,
        "in_progress": in_progress,
        "assigned": assigned,
        "common": common,
        "private": private,
        "recent": recent
    }

# ---------------------- REAL-TIME SYSTEM-WIDE COMPLAINT STATS ----------------------
@app.websocket("/complaints/stats/ws")
async def complaints_stats_ws(websocket: WebSocket):
    # Accept the WebSocket connection
    await websocket.accept()

    try:
        while True:
            db = SessionLocal()  # Open a DB session

            # System-wide counts
            total = db.query(Complaint).count()
            pending = db.query(Complaint).filter(Complaint.status == "pending").count()
            resolved = db.query(Complaint).filter(Complaint.status == "resolved").count()
            in_progress = db.query(Complaint).filter(Complaint.status == "in_progress").count()
            assigned = db.query(Complaint).filter(Complaint.status == "assigned").count()
            common = db.query(Complaint).filter(Complaint.complaint_type == "common").count()
            private = db.query(Complaint).filter(Complaint.complaint_type == "private").count()
            seven_days_ago = datetime.utcnow() - timedelta(days=7)
            recent = db.query(Complaint).filter(Complaint.created_at >= seven_days_ago).count()

            db.close()  # Close the DB session

            # Send data to client
            await websocket.send_json({
                "total": total,
                "pending": pending,
                "in_progress": in_progress,
                "resolved": resolved,
                "assigned": assigned,
                "common": common,
                "private": private,
                "recent": recent
            })

            await asyncio.sleep(3)  # Update interval (seconds)

    except WebSocketDisconnect:
        print("Client disconnected from WebSocket")

@app.websocket("/test/ws")
async def test_ws(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            await websocket.send_text("Hello from WebSocket!")
    except WebSocketDisconnect:
        print("Client disconnected")

# ---------------------- GET COMPLAINTS BY EMPLOYEE ----------------------
@app.get("/complaints/employee/{employee_id}")
def get_complaints_by_employee(employee_id: str, db: Session = Depends(get_db)):
    # Join Complaint with User to get fullname
    complaints = db.query(Complaint, User).join(User, Complaint.user_id == User.id)\
        .filter(Complaint.assigned_to == employee_id).all()

    if not complaints:
        return {"message": "No complaints assigned to this employee", "complaints": []}

    return [
        {
            "id": str(c.Complaint.id),
            "user_id": str(c.User.id),          # <-- added user_id
            "user_fullname": c.User.fullname,   # <-- keep fullname
            "title": c.Complaint.title,
            "description": c.Complaint.description,
            "complaint_type": c.Complaint.complaint_type,
            "address": c.Complaint.address,
            "status": c.Complaint.status,
            "assigned_to": c.Complaint.assigned_to,
            "created_at": c.Complaint.created_at.isoformat() if c.Complaint.created_at else None,
            "updated_at": c.Complaint.updated_at.isoformat() if c.Complaint.updated_at else None
        }
        for c in complaints
    ]
# ---------------------- UPDATE COMPLAINT STATUS ----------------------
@app.patch("/complaints/update-status")
def update_complaint_status(data: UpdateComplaintStatusSchema, db: Session = Depends(get_db)):
    # Get the complaint
    complaint = db.query(Complaint).filter(Complaint.id == data.complaint_id).first()
    if not complaint:
        raise HTTPException(status_code=404, detail="Complaint not found")
    
    # Get the employee by employee_id string
    employee = db.query(User).filter(User.employee_id == data.employee_id, User.role == "employee").first()
    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found")
    
    # Verify employee is assigned
    if complaint.assigned_to != employee.employee_id:
        raise HTTPException(status_code=403, detail="You are not assigned to this complaint")
    
    # Update status and notes
    complaint.status = data.status
    if data.notes:
        complaint.notes = data.notes

    db.commit()
    db.refresh(complaint)

    # Get user info
    user = db.query(User).filter(User.id == complaint.user_id).first()

    # ------------------------------
    # CREATE NOTIFICATION FOR USER IF DONE
    # ------------------------------
    notification_user = None
    if complaint.status.lower() == "done" and user:
        notification_user = Notification(
            user_id=user.id,
            sender_id=employee.id,  # UUID of employee
            complaint_id=complaint.id,
            type="done",
            title="Your Complaint Is Completed",
            message=f"Your complaint '{complaint.title}' has been marked as done by the assigned employee.",
        )
        db.add(notification_user)

    # ------------------------------
    # CREATE NOTIFICATION FOR ADMIN IF DONE
    # ------------------------------
    admins = db.query(User).filter(User.role == "admin").all()
    for admin in admins:
        notification_admin = Notification(
            user_id=admin.id,
            sender_id=employee.id,  # UUID of employee
            complaint_id=complaint.id,
            type="done",
            title="Complaint Completed by Employee",
            message=f"The complaint '{complaint.title}' submitted by {user.fullname} has been marked as done by {employee.fullname}.",
        )
        db.add(notification_admin)

    db.commit()  # Commit both user and admin notifications
    if notification_user:
        db.refresh(notification_user)

    return {
        "message": "Complaint updated successfully",
        "complaint": {
            "id": str(complaint.id),
            "user_id": str(user.id) if user else None,
            "user_fullname": user.fullname if user else None,
            "title": complaint.title,
            "status": complaint.status,
            "assigned_to": complaint.assigned_to,
            "notes": complaint.notes
        },
        "notification_id_user": str(notification_user.id) if notification_user else None
    }

# ---------------------- STATIC FILES ----------------------
UPLOAD_DIR = "uploads/profile_images"
os.makedirs(UPLOAD_DIR, exist_ok=True)

# Serve uploaded images as static files
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")
from uuid import UUID
# ---------------------- CREATE OR UPDATE USER PROFILE ----------------------


UPLOAD_DIR = "uploads/profile_images"
ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png", "webp"}  # allowed image types
os.makedirs(UPLOAD_DIR, exist_ok=True)

@app.post("/user-profile")
async def create_or_update_user_profile(
    user_id: str = Form(...),
    fullname: str = Form(...),
    email: str = Form(...),
    phone: str = Form(...),
    province: str = Form(...),
    district: str = Form(...),
    sector: str = Form(...),
    cell: str = Form(...),
    village: str = Form(...),
    about: str = Form(None),
    profile_image: UploadFile | None = File(None),
    db: Session = Depends(get_db),
    request: Request = None
):
    # Convert user_id to UUID
    try:
        user_uuid = UUID(user_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid user_id UUID")

    # Fetch the user
    user = db.query(User).filter(User.id == user_uuid).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # ---- Handle file upload ----
    image_url = None
    if profile_image:
        file_ext = profile_image.filename.split(".")[-1].lower()
        if file_ext not in ALLOWED_EXTENSIONS:
            raise HTTPException(status_code=400, detail="Invalid file type")
        filename = f"{user_id}.{file_ext}"
        file_path = os.path.join(UPLOAD_DIR, filename)

        # Save file asynchronously
        with open(file_path, "wb") as f:
            f.write(await profile_image.read())

        # Save relative path in DB (forward slashes)
        relative_path = f"profile_images/{filename}".replace("\\", "/")
        image_url = f"{str(request.base_url).rstrip('/')}/uploads/{relative_path}"

    # ---- Update user info ----
    user.fullname = fullname
    user.email = email
    user.phone = phone

    # ---- Create or update profile ----
    profile = db.query(UserProfile).filter(UserProfile.user_id == user_uuid).first()
    if profile:
        profile.province = province
        profile.district = district
        profile.sector = sector
        profile.cell = cell
        profile.village = village
        profile.about = about
        if image_url:
            profile.profile_image = relative_path  # store relative path
        message = "User profile updated successfully"
    else:
        profile = UserProfile(
            user_id=user_uuid,
            province=province,
            district=district,
            sector=sector,
            cell=cell,
            village=village,
            about=about,
            profile_image=relative_path if profile_image else None
        )
        db.add(profile)
        message = "User profile created successfully"

    # Commit all changes
    db.commit()
    db.refresh(user)
    db.refresh(profile)

    # Build final URL to send to frontend
    public_image_url = f"{str(request.base_url).rstrip('/')}/uploads/{profile.profile_image}" if profile.profile_image else None

    return {
        "message": message,
        "user": {
            "id": str(user.id),
            "fullname": user.fullname,
            "email": user.email,
            "phone": user.phone,
            "role": getattr(user, "role", None)
        },
        "profile": {
            "id": str(profile.id),
            "province": profile.province,
            "district": profile.district,
            "sector": profile.sector,
            "cell": profile.cell,
            "village": profile.village,
            "about": profile.about,
            "profile_image_url": public_image_url
        }
    }

# ---------------------- GET USER PROFILE ----------------------
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from uuid import UUID
from database import get_db
from models import User, UserProfile  # import your models

# ---------------------- GET USER PROFILE ----------------------
@app.get("/user-profile/{user_id}", response_model=dict)
def get_user_profile(user_id: str, db: Session = Depends(get_db), request: Request = None):
    # Validate UUID
    try:
        user_uuid = UUID(user_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid UUID format")

    # Fetch user
    user = db.query(User).filter(User.id == user_uuid).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Fetch user profile
    profile = db.query(UserProfile).filter(UserProfile.user_id == user_uuid).first()

    # Build image URL
    image_url = None
    if profile and profile.profile_image:
        base_url = str(request.base_url).rstrip("/")
        image_url = f"{base_url}/uploads/{profile.profile_image}"

    return {
        "user": {
            "id": str(user.id),
            "fullname": user.fullname,
            "email": user.email,
            "phone": user.phone,
            "role": user.role,
            "employee_id": user.employee_id
        },
        "profile": {
            "province": profile.province if profile else None,
            "district": profile.district if profile else None,
            "sector": profile.sector if profile else None,
            "cell": profile.cell if profile else None,
            "village": profile.village if profile else None,
            "about": profile.about if profile else None,
            "profile_image_url": image_url
        }
    }

# ---------------------- CHANGE PASSWORD ----------------------
@app.post("/change-password")
def change_password(
    user_id: str = Form(...),
    old_password: str = Form(...),
    new_password: str = Form(...),
    db: Session = Depends(get_db)
):
    try:
        user_uuid = UUID(user_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid user_id UUID")

    user = db.query(User).filter(User.id == user_uuid).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if not user.password:
        raise HTTPException(status_code=400, detail="User has no password set")

    if not _verify_password(old_password, user.password):
        raise HTTPException(status_code=400, detail="Incorrect old password")

    # Hash new password using Argon2/pbkdf2 context
    user.password = pwd_context.hash(new_password)
    db.commit()
    db.refresh(user)

    return {"message": "Password changed successfully"}

# ---------------------- GET USER NOTIFICATIONS ----------------------

@app.get("/notifications/{user_id}")
def get_notifications(user_id: UUID, db: Session = Depends(get_db)):
    notifications = db.query(Notification)\
        .filter(Notification.user_id == user_id)\
        .order_by(Notification.created_at.desc())\
        .all()

    if notifications is None:
        raise HTTPException(status_code=404, detail="No notifications found")

    # Convert to JSON-friendly dicts
    notifications_list = []
    for n in notifications:
        notifications_list.append({
            "id": str(n.id),
            "title": n.title,
            "message": n.message,
            "type": n.type,
            "created_at": n.created_at.isoformat() if n.created_at else None,
            "is_read": n.is_read
        })

    unread_count = sum(1 for n in notifications if n.is_read == 0)

    return {
        "notifications": notifications_list,
        "unread_count": unread_count
    }
# ---------------------- REJECT COMPLAINT ----------------------
@app.put("/complaints/{complaint_id}/reject")
def reject_complaint(complaint_id: UUID, db: Session = Depends(get_db)):
    complaint = db.query(Complaint).filter(Complaint.id == complaint_id).first()
    if not complaint:
        raise HTTPException(status_code=404, detail="Complaint not found")

    complaint.status = "rejected"
    db.commit()
    db.refresh(complaint)

    # Notification for user
    notification_user = Notification(
        user_id=complaint.user_id,
        sender_id=None,
        complaint_id=complaint.id,
        type="rejected",
        title="Your Complaint Has Been Rejected",
        message=f"Your complaint '{complaint.title}' has been rejected.",
    )
    db.add(notification_user)
    db.commit()
    db.refresh(notification_user)

    return {"message": "Complaint rejected", "notification_id": str(notification_user.id)}
  
# ---------------------- MARK NOTIFICATION AS READ ----------------------
@app.put("/notifications/{notification_id}/read")
def mark_notification_as_read(notification_id: UUID, db: Session = Depends(get_db)):
    notification = db.query(Notification).filter(Notification.id == notification_id).first()
    if not notification:
        raise HTTPException(status_code=404, detail="Notification not found")
    
    notification.is_read = 1
    notification.read_at = func.now()
    db.commit()
    db.refresh(notification)

    return {"message": "Notification marked as read"}
             
# ---------------------- SEND OTP ----------------------

class OTPRequest(BaseModel):
    email: str
# ---------------
@app.post("/send-otp")
async def send_otp(request: OTPRequest, db: Session = Depends(get_db)):
    email = request.email
    otp_code = str(random.randint(100000, 999999))
    expires_at = datetime.utcnow() + timedelta(minutes=5)

    user_otp = UserOTP(email=email, otp=otp_code, expires_at=expires_at)
    db.add(user_otp)
    db.commit()
    db.refresh(user_otp)

    message = MessageSchema(
        subject="Your OTP Code",
        recipients=[email],
        body=f"Your OTP is {otp_code}. It expires in 5 minutes.",
        subtype="plain"
    )
    await fm.send_message(message)

    return {"message": f"OTP sent to {email}"}

# -------------------- VERIFY OTP --------------------
@app.post("/verify-otp")
def verify_otp(email: str, otp: str, db: Session = Depends(get_db)):
    otp_record = db.query(UserOTP).filter(
        UserOTP.email == email,
        UserOTP.otp == otp,
        UserOTP.is_used == 0,
        UserOTP.expires_at >= datetime.utcnow()
    ).first()

    if not otp_record:
        raise HTTPException(400, "Invalid or expired OTP")

    otp_record.is_used = 1
    db.commit()

    return {"message": "OTP verified successfully"}

# ---------------------- USER COMPLAINT TREND ----------------------
@app.get("/complaints/trend/user/{user_id}")
def user_complaint_trend(user_id: UUID, db: Session = Depends(get_db)):
    """
    Returns the number of complaints submitted by a user for each of the last 7 days.
    """
    today = datetime.utcnow().date()
    trend = []

    # Loop through last 7 days
    for i in range(6, -1, -1):  # from 6 days ago to today
        day = today - timedelta(days=i)
        count = db.query(Complaint).filter(
            Complaint.user_id == user_id,
            Complaint.created_at >= datetime.combine(day, datetime.min.time()),
            Complaint.created_at <= datetime.combine(day, datetime.max.time())
        ).count()
        trend.append({"day": day.strftime("%a"), "count": count})

    return {"user_id": str(user_id), "trend": trend}

# ---------------------- RECENT COMMON COMPLAINTS ----------------------
@app.get("/complaints/recent/common")
def recent_common_complaints(
    db: Session = Depends(get_db),
    limit: int = 5
):
    complaints = (
        db.query(Complaint, User)
        .join(User, User.id == Complaint.user_id)
        .filter(Complaint.complaint_type == "common")
        .order_by(Complaint.created_at.desc())
        .limit(limit)
        .all()
    )

    result = [
        {
            "id": str(complaint.id),
            "user_name": user.fullname,   # ✅ works
            "title": complaint.title,
            "status": complaint.status.capitalize()
        }
        for complaint, user in complaints
    ]

    return {"recent_common_complaints": result}

# ---------------------- UPDATE USER PROFILE ----------------------

UPLOAD_DIR = "uploads/profile_images"
os.makedirs(UPLOAD_DIR, exist_ok=True)

from fastapi import Form

@app.put("/user-profile/{user_id}", response_model=dict)
async def update_user_profile(
    user_id: str,
    name: str | None = Form(None),
    email: str | None = Form(None),
    phone: str | None = Form(None),
    province: str | None = Form(None),
    district: str | None = Form(None),
    sector: str | None = Form(None),
    cell: str | None = Form(None),
    village: str | None = Form(None),
    about: str | None = Form(None),
    profile_image: UploadFile | None = File(None),
    db: Session = Depends(get_db),
    request: Request = None
):
    # Validate UUID
    try:
        user_uuid = UUID(user_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid UUID format")

    # Fetch user
    user = db.query(User).filter(User.id == user_uuid).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Fetch user profile
    profile = db.query(UserProfile).filter(UserProfile.user_id == user_uuid).first()

    # ---- Update User fields ----
    if name is not None:
        user.fullname = name
    if email is not None:
        user.email = email
    if phone is not None:
        user.phone = phone

    # ---- Update UserProfile fields ----
    if profile:
        profile.province = province or profile.province
        profile.district = district or profile.district
        profile.sector = sector or profile.sector
        profile.cell = cell or profile.cell
        profile.village = village or profile.village
        profile.about = about or profile.about
    else:
        profile = UserProfile(
            user_id=user_uuid,
            province=province or "",
            district=district or "",
            sector=sector or "",
            cell=cell or "",
            village=village or "",
            about=about or "",
        )
        db.add(profile)

    # ---- Handle profile image upload ----
    if profile_image:
        filename = f"{user_id}_{profile_image.filename}"
        file_path = os.path.join(UPLOAD_DIR, filename)
        with open(file_path, "wb") as f:
            f.write(await profile_image.read())
        profile.profile_image = file_path  # Save path in DB

    db.commit()
    db.refresh(user)
    db.refresh(profile)

    # Build public image URL
    base_url = str(request.base_url).rstrip("/") if request else ""
    image_url = f"{base_url}/{profile.profile_image}" if profile.profile_image else None

    return {
        "message": "Profile updated successfully",
        "user": {
            "id": str(user.id),
            "fullname": user.fullname,
            "email": user.email,
            "phone": user.phone,
        },
        "profile": {
            "province": profile.province,
            "district": profile.district,
            "sector": profile.sector,
            "cell": profile.cell,
            "village": profile.village,
            "about": profile.about,
            "profile_image_url": image_url,
        }
    }

# ---------------------- UPLOAD DIRECTORY ----------------------
UPLOAD_DIR = "uploads/profile_images"
os.makedirs(UPLOAD_DIR, exist_ok=True)

# Mount uploads folder for public access
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

# ---------------------- UPDATE USER PROFILE ----------------------
@app.put("/user-profile/{user_id}", response_model=dict)
async def update_user_profile(
    user_id: str,
    name: str | None = Form(None),
    email: str | None = Form(None),
    phone: str | None = Form(None),
    province: str | None = Form(None),
    district: str | None = Form(None),
    sector: str | None = Form(None),
    cell: str | None = Form(None),
    village: str | None = Form(None),
    about: str | None = Form(None),
    profile_image: UploadFile | None = File(None),
    db: Session = Depends(get_db),
    request: Request = None
):
    # Validate UUID
    try:
        user_uuid = UUID(user_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid UUID format")

    # Fetch user
    user = db.query(User).filter(User.id == user_uuid).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Fetch user profile
    profile = db.query(UserProfile).filter(UserProfile.user_id == user_uuid).first()

    # ---- Update User fields ----
    if name is not None:
        user.fullname = name
    if email is not None:
        user.email = email
    if phone is not None:
        user.phone = phone

    # ---- Update UserProfile fields ----
    if profile:
        profile.province = province or profile.province
        profile.district = district or profile.district
        profile.sector = sector or profile.sector
        profile.cell = cell or profile.cell
        profile.village = village or profile.village
        profile.about = about or profile.about
    else:
        profile = UserProfile(
            user_id=user_uuid,
            province=province or "",
            district=district or "",
            sector=sector or "",
            cell=cell or "",
            village=village or "",
            about=about or "",
        )
        db.add(profile)

# ---------------------- UPLOAD DIRECTORY ----------------------
UPLOAD_DIR = "uploads/profile_images"
os.makedirs(UPLOAD_DIR, exist_ok=True)

# Mount uploads folder to serve images publicly
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

# ---------------------- UPDATE USER PROFILE ----------------------
@app.put("/user-profile/{user_id}", response_model=dict)
async def update_user_profile(
    user_id: str,
    name: str | None = Form(None),
    email: str | None = Form(None),
    phone: str | None = Form(None),
    province: str | None = Form(None),
    district: str | None = Form(None),
    sector: str | None = Form(None),
    cell: str | None = Form(None),
    village: str | None = Form(None),
    about: str | None = Form(None),
    profile_image: UploadFile | None = File(None),
    db: Session = Depends(get_db),
    request: Request = None
):
    # Validate UUID
    try:
        user_uuid = UUID(user_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid UUID format")

    # Fetch user
    user = db.query(User).filter(User.id == user_uuid).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Fetch user profile
    profile = db.query(UserProfile).filter(UserProfile.user_id == user_uuid).first()

    # ---- Update User fields ----
    if name is not None:
        user.fullname = name
    if email is not None:
        user.email = email
    if phone is not None:
        user.phone = phone

    # ---- Update UserProfile fields ----
    if profile:
        profile.province = province or profile.province
        profile.district = district or profile.district
        profile.sector = sector or profile.sector
        profile.cell = cell or profile.cell
        profile.village = village or profile.village
        profile.about = about or profile.about
    else:
        profile = UserProfile(
            user_id=user_uuid,
            province=province or "",
            district=district or "",
            sector=sector or "",
            cell=cell or "",
            village=village or "",
            about=about or "",
        )
        db.add(profile)

    # ---- Handle profile image upload ----
    if profile_image:
        filename = f"{user_id}_{profile_image.filename}"
        file_path = os.path.join(UPLOAD_DIR, filename)
        # Save file to disk
        with open(file_path, "wb") as f:
            f.write(await profile_image.read())
        # Save relative path with forward slashes
        profile.profile_image = f"profile_images/{filename}".replace("\\", "/")

    db.commit()
    db.refresh(user)
    db.refresh(profile)

    # Build public URL
    base_url = str(request.base_url).rstrip("/") if request else ""
    image_url = f"{base_url}/uploads/{profile.profile_image}" if profile.profile_image else None

    return {
        "message": "Profile updated successfully",
        "user": {
            "id": str(user.id),
            "fullname": user.fullname,
            "email": user.email,
            "phone": user.phone,
        },
        "profile": {
            "province": profile.province,
            "district": profile.district,
            "sector": profile.sector,
            "cell": profile.cell,
            "village": profile.village,
            "about": profile.about,
            "profile_image_url": image_url,
        }
    }



# ----------------- Supabase Config -----------------
SUPABASE_URL = "https://bwxwqmtalpwizbukbqcb.supabase.co"
SUPABASE_SERVICE_ROLE_KEY = "sb_secret_g5_DZTmuG5e8M4fCx9jQ4Q_GLUJDJvP"
BUCKET_NAME = "rossa"

supabase: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)

# ----------------- Test Upload Endpoint -----------------
@app.post("/upload-test/")
async def upload_test(file: UploadFile = File(...)):
    try:
        # Save temp file locally
        temp_file_path = f"temp_{file.filename}"
        with open(temp_file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        file_path = f"test/{file.filename}"

        # Delete first if exists (simulate upsert)
        try:
            supabase.storage.from_(BUCKET_NAME).remove([file_path])
        except Exception:
            pass

        # Upload file
        with open(temp_file_path, "rb") as f:
            supabase.storage.from_(BUCKET_NAME).upload(file_path, f)

        # Remove local temp file
        os.remove(temp_file_path)

        # Get public URL (Python SDK returns string)
        public_url = supabase.storage.from_(BUCKET_NAME).get_public_url(file_path)

        return {"message": "Upload successful", "url": public_url}

    except Exception as e:
        return {"error": str(e)}
from sqlalchemy import text  # ✅ make sure this import is at the top

@app.get("/db-test")
def db_test(db: Session = Depends(get_db)):
    result = db.execute(
        text("SELECT current_database(), current_schema()")
    ).fetchone()
    return {
        "current_database": result[0],
        "current_schema": result[1]
    }
