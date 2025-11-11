from fastapi import FastAPI, HTTPException, Depends
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session
from database import engine, SessionLocal, Base
from models import User

# Create tables in database automatically
Base.metadata.create_all(bind=engine)

# FastAPI instance
app = FastAPI(title="Customer Complaint System")

# Root route
@app.get("/")
def root():
    return {"message": "Customer Complaint API is running!"}

# Dependency to get DB session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# ------------------------------
# Pydantic models
# ------------------------------
class LoginSchema(BaseModel):
    email: EmailStr
    password: str

class RegisterSchema(BaseModel):
    fullname: str
    phone: str
    email: EmailStr
    password: str = None
    employee_id: str = None
    role: str  # 'customer', 'employee', 'admin'

# ------------------------------
# Routes
# ------------------------------
@app.post("/register")
def register(data: RegisterSchema, db: Session = Depends(get_db)):
    existing = db.query(User).filter(User.email == data.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")

    new_user = User(
        fullname=data.fullname,
        phone=data.phone,
        email=data.email,
        password=data.password,
        employee_id=data.employee_id,
        role=data.role
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return {"message": f"{data.role.capitalize()} registered successfully!"}

@app.post("/login")
def login(data: LoginSchema, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == data.email).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Check password or employee_id based on role
    if user.role == "customer":
        if user.password != data.password:
            raise HTTPException(status_code=400, detail="Incorrect password")
    else:  # admin or employee
        if user.employee_id != data.password:
            raise HTTPException(status_code=400, detail="Incorrect ID")

    return {"message": f"Login successful! Redirect to {user.role} dashboard."}
