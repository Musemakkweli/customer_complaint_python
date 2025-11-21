from fastapi import FastAPI, HTTPException, Depends, status
from fastapi.security import OAuth2PasswordBearer
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr
from typing import Optional, List
from passlib.context import CryptContext
from sqlalchemy.orm import Session
from uuid import UUID
from database import engine, SessionLocal, Base
from models import User, Complaint
import datetime
import os
import jwt

# -------------------------------------------------------
# CONFIGURATION
# -------------------------------------------------------
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

# -------------------------------------------------------
# DATABASE CONNECTION
# -------------------------------------------------------
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# -------------------------------------------------------
# SCHEMAS
# -------------------------------------------------------
class RegisterSchema(BaseModel):
    fullname: str
    phone: str
    email: EmailStr
    password: Optional[str] = None
    employee_id: Optional[str] = None
    role: str = "customer"

class LoginSchema(BaseModel):
    email: str       # employees will use employee_id here
    password: str

class UserResponse(BaseModel):
    id: UUID
    fullname: str
    phone: str
    email: str
    role: str
    employee_id: Optional[str] = None

    class Config:
        from_attributes = True

class UpdateRoleSchema(BaseModel):
    role: str   # "customer", "employee", "admin"

class UpdateEmployeeIDSchema(BaseModel):
    employee_id: str

class ComplaintCreateSchema(BaseModel):
    user_id: UUID
    title: str
    description: str
    complaint_type: str     # common or private
    address: str

# -------------------------------------------------------
# JWT UTILITY FUNCTIONS
# -------------------------------------------------------
def create_access_token(data: dict, expires_delta=None):
    to_encode = data.copy()
    expire = datetime.datetime.utcnow() + (
        expires_delta if expires_delta else datetime.timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode.update({"exp": expire})

    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
):
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

# -------------------------------------------------------
# ROUTES
# -------------------------------------------------------
@app.get("/")
def root():
    return {"message": "Customer Complaint API is running!"}

# ------------------------
# REGISTER
# ------------------------
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

# ------------------------
# LOGIN
# ------------------------
@app.post("/login")
def login(data: LoginSchema, db: Session = Depends(get_db)):

    # Search by email first
    user = db.query(User).filter(User.email == data.email).first()

    # If not email, check employee_id
    if not user:
        user = db.query(User).filter(User.employee_id == data.email).first()

    if not user:
        raise HTTPException(404, "User not found")

    # CUSTOMER OR ADMIN LOGIN USING EMAIL
    if user.role in ["customer", "admin"]:
        if not pwd_context.verify(data.password, user.password):
            raise HTTPException(400, "Incorrect password")
        login_identifier = user.email

    # EMPLOYEE LOGIN USING EMPLOYEE ID
    elif user.role == "employee":
        if user.employee_id != data.email:
            raise HTTPException(400, "Incorrect employee ID")
        if not pwd_context.verify(data.password, user.password):
            raise HTTPException(400, "Incorrect password")
        login_identifier = user.employee_id

    else:
        raise HTTPException(400, "Invalid role")

    token = create_access_token(
        {"sub": login_identifier, "role": user.role},
        expires_delta=datetime.timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
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

# ------------------------
# GET CURRENT USER
# ------------------------
@app.get("/me")
def read_me(current_user: User = Depends(get_current_user)):
    return {
        "id": str(current_user.id),
        "fullname": current_user.fullname,
        "email": current_user.email if current_user.role == "customer" else current_user.employee_id,
        "role": current_user.role,
    }

# ------------------------
# GET ALL USERS
# ------------------------
@app.get("/users", response_model=List[UserResponse])
def get_all_users(db: Session = Depends(get_db)):
    return db.query(User).all()

# ------------------------
# UPDATE USER ROLE
# ------------------------
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

# ------------------------
# UPDATE EMPLOYEE ID
# ------------------------
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

# -------------------------------------------------------
# COMPLAINT ROUTES
# -------------------------------------------------------

# -----------------------
# CREATE COMPLAINT
# -----------------------
@app.post("/complaints")
def submit_complaint(data: ComplaintCreateSchema, db: Session = Depends(get_db)):

    user = db.query(User).filter(User.id == data.user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if user.role != "customer":
        raise HTTPException(status_code=403, detail="Only customers can submit complaints")

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

    return {
        "message": "Complaint submitted successfully",
        "complaint": {
            "id": str(new_complaint.id),
            "user_id": str(new_complaint.user_id),
            "title": new_complaint.title,
            "description": new_complaint.description,
            "complaint_type": new_complaint.complaint_type,
            "address": new_complaint.address,
            "status": new_complaint.status,
            "created_at": new_complaint.created_at.isoformat() if new_complaint.created_at else None,
            "updated_at": new_complaint.updated_at.isoformat() if new_complaint.updated_at else None
        }
    }

# -----------------------
# GET ALL COMPLAINTS
# -----------------------
@app.get("/complaints")
def get_all_complaints(db: Session = Depends(get_db)):
    complaints = db.query(Complaint).all()
    return [
        {
            "id": str(c.id),
            "user_id": str(c.user_id),
            "title": c.title,
            "description": c.description,
            "complaint_type": c.complaint_type,
            "address": c.address,
            "status": c.status,
            "created_at": c.created_at.isoformat() if c.created_at else None,
            "updated_at": c.updated_at.isoformat() if c.updated_at else None
        }
        for c in complaints
    ]

# -----------------------
# GET COMPLAINTS BY USER ID
# -----------------------
@app.get("/complaints/user/{user_id}")
def get_complaints_by_user(user_id: UUID, db: Session = Depends(get_db)):
    complaints = db.query(Complaint).filter(Complaint.user_id == user_id).all()
    if not complaints:
        raise HTTPException(status_code=404, detail="No complaints found for this user")

    return [
        {
            "id": str(c.id),
            "user_id": str(c.user_id),
            "title": c.title,
            "description": c.description,
            "complaint_type": c.complaint_type,
            "address": c.address,
            "status": c.status,
            "created_at": c.created_at.isoformat() if c.created_at else None,
            "updated_at": c.updated_at.isoformat() if c.updated_at else None
        }
        for c in complaints
    ]