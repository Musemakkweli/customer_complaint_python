from pydantic import BaseModel, EmailStr
from typing import Optional, Literal
from uuid import UUID

# -----------------------------
# Registration/Login Schemas
# -----------------------------
class RegisterSchema(BaseModel):
    fullname: str
    phone: str
    email: EmailStr
    password: Optional[str] = None
    employee_id: Optional[str] = None
    role: str = "customer"

class LoginSchema(BaseModel):
    email: str
    password: str

# -----------------------------
# User Response & Update Schemas
# -----------------------------
class UserResponse(BaseModel):
    id: UUID
    fullname: str
    phone: str
    email: EmailStr
    role: str
    employee_id: Optional[str] = None

    class Config:
        from_attributes = True

class UpdateRoleSchema(BaseModel):
    role: str

class UpdateEmployeeIDSchema(BaseModel):
    employee_id: str

# -----------------------------
# Complaint Schemas
# -----------------------------
class ComplaintCreateSchema(BaseModel):
    user_id: UUID
    title: str
    description: str
    complaint_type: Literal["common", "private"]
    address: str

class ComplaintResponseSchema(BaseModel):
    id: UUID
    user_id: UUID
    title: str
    description: str
    complaint_type: str
    address: str
    status: str
    created_at: str
    updated_at: str

    class Config:
        from_attributes = True

# -----------------------------
# Employee / Assign Complaint
# -----------------------------
class EmployeeSchema(BaseModel):
    id: int
    name: str
    email: str
    position: Optional[str] = None

    class Config:
        from_attributes = True

class AssignComplaintSchema(BaseModel):
    employee_id: str


class UpdateComplaintStatusSchema(BaseModel):
    complaint_id: UUID
    employee_id: str
    status: str  # new status: e.g., "done", "in_progress", "pending"
    notes: Optional[str] = None