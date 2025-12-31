from pydantic import BaseModel, EmailStr, model_validator
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
    email: Optional[str] = None
    employee_id: Optional[str] = None
    password: str

    @model_validator(mode="after")
    def ensure_identifier(self):
        if not self.email and not self.employee_id:
            raise ValueError("Either email or employee_id must be provided")
        return self

# -----------------------------
# User Response & Update Schemas
class UserResponse(BaseModel):
    id: UUID
    fullname: str
    phone: str
    email: Optional[EmailStr] = None   # <-- allow None
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


class UserProfileCreateSchema(BaseModel):
    user_id: UUID
    province: str
    district: str
    sector: str
    cell: str
    village: str
    profile_image: Optional[str] = None 
    

class UserProfileUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    province: Optional[str] = None
    district: Optional[str] = None
    sector: Optional[str] = None
    cell: Optional[str] = None
    village: Optional[str] = None
    about: Optional[str] = None