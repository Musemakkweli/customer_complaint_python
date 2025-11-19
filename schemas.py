from pydantic import BaseModel, EmailStr
from uuid import UUID

class UserResponse(BaseModel):
    id: UUID
    fullname: str
    phone: str
    email: EmailStr
    role: str
    employee_id: str | None = None

    class Config:
        from_attributes = True  # ✅ Pydantic v2 replacement for orm_mode


from pydantic import BaseModel

class UpdateRoleSchema(BaseModel):
    role: str   # must be: "customer", "employee", "admin"

class UpdateEmployeeIDSchema(BaseModel):
    employee_id: str
