from pydantic import BaseModel, EmailStr
from uuid import UUID


# ------------------------------------
# User Response Schema
# ------------------------------------
class UserResponse(BaseModel):
    id: UUID
    fullname: str
    phone: str
    email: EmailStr
    role: str
    employee_id: str | None = None

    class Config:
        from_attributes = True  # Pydantic v2


# ------------------------------------
# Update Role Schema
# ------------------------------------
class UpdateRoleSchema(BaseModel):
    role: str  # "customer", "employee", "admin"


# ------------------------------------
# Update Employee ID Schema
# ------------------------------------
class UpdateEmployeeIDSchema(BaseModel):
    employee_id: str
from pydantic import BaseModel
from typing import Literal
from uuid import UUID

# ------------------------------------
# Complaint Creation Schema
# ------------------------------------
class ComplaintCreateSchema(BaseModel):
    user_id: UUID
    title: str
    description: str
    complaint_type: Literal["common", "private"]  # Only allows "common" or "private"
    address: str


# ------------------------------------
# Complaint Response Schema
# ------------------------------------
class ComplaintResponseSchema(BaseModel):
    id: UUID
    user_id: UUID
    title: str
    description: str
    complaint_type: str
    address: str
    status: str
    created_at: str
    updated_at: str  # Added updated_at field

    class Config:
        from_attributes = True
