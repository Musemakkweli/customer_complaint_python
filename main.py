from fastapi import FastAPI, UploadFile, File, Form, Depends, HTTPException, APIRouter
from fastapi.security import OAuth2PasswordBearer
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from uuid import UUID
import shutil
from database import engine, SessionLocal, Base
from models import UserProfile, User
from schemas import UserProfileCreateSchema
from models import User, Complaint
from schemas import (
    RegisterSchema,
    LoginSchema,
    UserResponse,
    UpdateRoleSchema,
    UpdateEmployeeIDSchema,
    ComplaintCreateSchema,
    ComplaintResponseSchema,
    EmployeeSchema,
    AssignComplaintSchema,
    UpdateComplaintStatusSchema 
)


from datetime import datetime, timedelta
import os
import jwt
from passlib.context import CryptContext
from fastapi import WebSocket, WebSocketDisconnect
import asyncio
from fastapi.staticfiles import StaticFiles
from fastapi import Request
from sqlalchemy import or_
from utils.notifications import create_notification
from models import Notification



# ---------------------- CONFIGURATION ----------------------
SECRET_KEY = os.getenv("SECRET_KEY", "change-me-please")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", 60))

pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")
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

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

@app.post("/login")
def login(data: LoginSchema, db: Session = Depends(get_db)):
    # Find user by email or employee ID
    user = db.query(User).filter(
        or_(User.email == data.email, User.employee_id == data.email)
    ).first()
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Verify password against hash
    if not pwd_context.verify(data.password, user.password):
        raise HTTPException(status_code=400, detail="Incorrect password")
    
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
def submit_complaint(data: ComplaintCreateSchema, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == data.user_id).first()
    if not user:
        raise HTTPException(404, "User not found")
    if user.role != "customer":
        raise HTTPException(403, "Only customers can submit complaints")

    new_complaint = Complaint(
        user_id=data.user_id,
        title=data.title,
        description=data.description,
        complaint_type=data.complaint_type,
        address=data.address,
        status="pending"
    )
    db.add(new_complaint)
    db.commit()
    db.refresh(new_complaint)

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
ALLOWED_EXTENSIONS = ["png", "jpg", "jpeg"]

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
    profile_image: UploadFile = File(None),
    db: Session = Depends(get_db),
    request: Request = None
):
    # Ensure upload directory exists
    os.makedirs(UPLOAD_DIR, exist_ok=True)

    # Convert user_id to UUID
    try:
        user_uuid = UUID(user_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid user_id UUID")

    # Fetch the user
    user = db.query(User).filter(User.id == user_uuid).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Handle file upload
    image_url = None
    if profile_image:
        file_ext = profile_image.filename.split(".")[-1].lower()
        if file_ext not in ALLOWED_EXTENSIONS:
            raise HTTPException(status_code=400, detail="Invalid file type")
        filename = f"{user_id}.{file_ext}"
        file_path = os.path.join(UPLOAD_DIR, filename)
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(profile_image.file, buffer)
        base_url = str(request.base_url).rstrip("/")
        image_url = f"{base_url}/uploads/profile_images/{filename}"

    # Update user info
    user.fullname = fullname
    user.email = email
    user.phone = phone

    # Create or update profile
    profile = db.query(UserProfile).filter(UserProfile.user_id == user_uuid).first()
    if profile:
        profile.province = province
        profile.district = district
        profile.sector = sector
        profile.cell = cell
        profile.village = village
        profile.about = about
        if image_url:
            profile.profile_image = image_url
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
            profile_image=image_url
        )
        db.add(profile)
        message = "User profile created successfully"

    # Commit all changes
    db.commit()
    db.refresh(user)
    db.refresh(profile)

    # Return response
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
            "profile_image_url": profile.profile_image
        }
    }

# ---------------------- GET USER PROFILE ----------------------
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from uuid import UUID
from database import get_db
from models import User, UserProfile  # import your models

@app.get("/user-profile/{user_id}")
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

    # Fetch user profile (additional info)
    profile = db.query(UserProfile).filter(UserProfile.user_id == user_uuid).first()

    # Build profile image URL if available
    image_url = None
    if profile and profile.profile_image:
        base_url = str(request.base_url).rstrip("/")
        filename = profile.profile_image.split("/")[-1]
        image_url = f"{base_url}/uploads/profile_images/{filename}"

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
            "about": profile.about if profile else None,            # Added about
            "profile_image_url": image_url
        }
    }

# ---------------------- CHANGE PASSWORD ----------------------
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

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

    # Truncate to 72 characters to match bcrypt limitation
    old_password_trunc = old_password[:72]
    new_password_trunc = new_password[:72]

    # Verify old password
    if not pwd_context.verify(old_password_trunc, user.password):
        raise HTTPException(status_code=400, detail="Incorrect old password")

    # Hash new password and save
    user.password = pwd_context.hash(new_password_trunc)
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
