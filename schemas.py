from pydantic import BaseModel, EmailStr
from uuid import UUID

# -----------------------
# User response schema
# -----------------------
class UserResponse(BaseModel):
    id: UUID
    fullname: str
    phone: str
    email: EmailStr
    role: str
    employee_id: str | None = None  # Optional field

    class Config:
        from_attributes = True  # ✅ Pydantic v2 replacement for orm_mode


# -----------------------
# Update role schema
# -----------------------
class UpdateRoleSchema(BaseModel):
    role: str  # must be: "customer", "employee", or "admin"


# -----------------------
# Update employee ID schema
# -----------------------
class UpdateEmployeeIDSchema(BaseModel):
    employee_id: str


# -----------------------
# Complaint creation schema
# -----------------------
class ComplaintCreateSchema(BaseModel):
    title: str
    description: str
    user_id: str  # UUID of the customer submitting the complaint
