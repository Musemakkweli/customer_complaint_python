from fastapi import FastAPI, HTTPException, Depends
from fastapi.security import OAuth2PasswordBearer
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from uuid import UUID
from database import engine, SessionLocal, Base
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
    AssignComplaintSchema
)
from datetime import datetime, timedelta
import os
import jwt
from passlib.context import CryptContext
from fastapi import WebSocket, WebSocketDisconnect
import asyncio

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
@app.post("/login")
def login(data: LoginSchema, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == data.email).first()
    if not user:
        user = db.query(User).filter(User.employee_id == data.email).first()
    if not user:
        raise HTTPException(404, "User not found")

    if user.role in ["customer", "admin"]:
        if not pwd_context.verify(data.password, user.password):
            raise HTTPException(400, "Incorrect password")
        login_identifier = user.email
    elif user.role == "employee":
        if user.employee_id != data.email or not pwd_context.verify(data.password, user.password):
            raise HTTPException(400, "Incorrect credentials")
        login_identifier = user.employee_id
    else:
        raise HTTPException(400, "Invalid role")

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
            "email": login_identifier,
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
    return db.query(User).all()

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

    return {"message": "Complaint submitted successfully", "complaint_id": str(new_complaint.id)}
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

# ---------------------- ASSIGN COMPLAINT ----------------------
@app.put("/complaints/{complaint_id}/assign")
def assign_complaint(complaint_id: UUID, data: AssignComplaintSchema, db: Session = Depends(get_db)):
    complaint = db.query(Complaint).filter(Complaint.id == complaint_id).first()
    if not complaint:
        raise HTTPException(404, "Complaint not found")

    employee = db.query(User).filter(User.employee_id == data.employee_id, User.role == "employee").first()
    if not employee:
        raise HTTPException(404, "Employee not found")

    complaint.assigned_to = data.employee_id
    complaint.status = "assigned"
    db.commit()
    db.refresh(complaint)

    return {"message": f"Complaint assigned to {employee.fullname} successfully"}

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
    complaints = db.query(Complaint).filter(Complaint.user_id == user_id).all()

    if not complaints:
        return {"message": "No complaints found for this user", "data": []}

    return [
        {
            "id": str(c.id),
            "user_id": str(c.user_id),
            "title": c.title,
            "description": c.description,
            "complaint_type": c.complaint_type,
            "address": c.address,
            "status": c.status,
            "assigned_to": c.assigned_to,
            "created_at": c.created_at.isoformat() if c.created_at else None,
            "updated_at": c.updated_at.isoformat() if c.updated_at else None
        }
        for c in complaints
    ]
from datetime import datetime, timedelta


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
            "user_fullname": c.User.fullname,  # <-- return fullname instead of user_id
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
