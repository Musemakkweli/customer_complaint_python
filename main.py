from fastapi import FastAPI, HTTPException, Depends, status
from fastapi.security import OAuth2PasswordBearer
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr
from typing import Optional, List
from passlib.context import CryptContext
from sqlalchemy.orm import Session
from database import engine, SessionLocal, Base
from models import User
import os
import datetime
import jwt
from uuid import UUID

# -----------------------
# Config
# -----------------------
SECRET_KEY = os.getenv("SECRET_KEY", "change-me-please")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))

pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/login")

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Customer Complaint System")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -----------------------
# DB Dependency
# -----------------------
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# -----------------------
# Schemas
# -----------------------
class RegisterSchema(BaseModel):
    fullname: str
    phone: str
    email: EmailStr
    password: Optional[str] = None
    employee_id: Optional[str] = None
    role: str = "customer"

class LoginSchema(BaseModel):
    email: str  # For employees this will be employee_id
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
    role: str  # "customer", "employee", "admin"

class UpdateEmployeeIDSchema(BaseModel):
    employee_id: str

# -----------------------
# JWT Utility
# -----------------------
def create_access_token(data: dict, expires_delta: Optional[datetime.timedelta] = None):
    to_encode = data.copy()
    expire = datetime.datetime.utcnow() + (
        expires_delta if expires_delta else datetime.timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    ex = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        identifier: str = payload.get("sub")
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

# -----------------------
# Routes
# -----------------------
@app.get("/")
def root():
    return {"message": "Customer Complaint API is running!"}

@app.post("/register")
def register(data: RegisterSchema, db: Session = Depends(get_db)):
    existing = db.query(User).filter(User.email == data.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")

    employee_id_to_store = data.employee_id if data.role != "customer" else None

    if data.role == "customer" and not data.password:
        raise HTTPException(status_code=400, detail="Password is required for customers")

    if data.role != "customer" and not data.employee_id:
        raise HTTPException(status_code=400, detail="employee_id is required for employees/admins")

    hashed_password = pwd_context.hash(data.password) if data.password else None

    new_user = User(
        fullname=data.fullname,
        phone=data.phone,
        email=data.email,
        password=hashed_password,
        employee_id=employee_id_to_store,
        role=data.role
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    return {"message": f"{data.role.capitalize()} registered successfully!"}

@app.post("/login")
def login(data: LoginSchema, db: Session = Depends(get_db)):
    # Employees use employee_id, customers use email
    user = db.query(User).filter(
        (User.email == data.email) | (User.employee_id == data.email)
    ).first()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if user.role == "customer":
        if not user.password or not pwd_context.verify(data.password, user.password):
            raise HTTPException(status_code=400, detail="Incorrect password")
        login_identifier = user.email
    else:
        if user.employee_id != data.email:
            raise HTTPException(status_code=400, detail="Incorrect employee ID")
        if not user.password or not pwd_context.verify(data.password, user.password):
            raise HTTPException(status_code=400, detail="Incorrect password")
        login_identifier = user.employee_id

    token = create_access_token(
        data={"sub": login_identifier, "role": user.role},
        expires_delta=datetime.timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
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

@app.get("/me")
def read_me(current_user: User = Depends(get_current_user)):
    return {
        "id": str(current_user.id),
        "fullname": current_user.fullname,
        "email": current_user.email if current_user.role == "customer" else current_user.employee_id,
        "role": current_user.role,
    }

@app.get("/users", response_model=List[UserResponse])
def get_all_users(db: Session = Depends(get_db)):
    return db.query(User).all()

@app.put("/users/{user_id}/role")
def update_user_role(user_id: str, data: UpdateRoleSchema, db: Session = Depends(get_db)):
    allowed_roles = ["customer", "employee", "admin"]
    if data.role not in allowed_roles:
        raise HTTPException(status_code=400, detail="Invalid role")

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.role = data.role
    if data.role == "customer":
        user.employee_id = None

    db.commit()
    db.refresh(user)

    return {
        "message": "Role updated successfully",
        "user": {
            "id": str(user.id),
            "fullname": user.fullname,
            "email": user.email,
            "role": user.role
        }
    }

@app.put("/users/{user_id}/employee-id")
def update_employee_id(user_id: str, data: UpdateEmployeeIDSchema, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.role != "employee":
        raise HTTPException(status_code=400, detail="Only employees can have an employee_id")

    user.employee_id = data.employee_id
    db.commit()
    db.refresh(user)

    return {
        "message": "Employee ID updated successfully",
        "user": {
            "id": str(user.id),
            "fullname": user.fullname,
            "email": user.email,
            "role": user.role,
            "employee_id": user.employee_id
        }
    }
