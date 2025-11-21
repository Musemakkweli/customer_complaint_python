from sqlalchemy import Column, String, Integer, DateTime, ForeignKey, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from database import Base
import uuid


# ------------------------------------
# USERS TABLE
# ------------------------------------
class User(Base):
    __tablename__ = "users"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()")
    )
    fullname = Column(String(255), nullable=False)
    phone = Column(String(50), nullable=False)
    email = Column(String(255), unique=True, nullable=False)
    password = Column(String(255), nullable=True)        # For customers
    employee_id = Column(String(50), nullable=True)      # For employees
    role = Column(
        String(20),
        nullable=False,
        default="customer",
        server_default=text("'customer'")
    )  # customer, employee, admin


# ------------------------------------
# COMPLAINTS TABLE
# ------------------------------------
class Complaint(Base):
    __tablename__ = "complaints"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()")
    )
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=False
    )
    title = Column(String(255), nullable=False)
    description = Column(String, nullable=False)
    complaint_type = Column(
        String(20),
        nullable=False,
        default="common",
        server_default=text("'common'")
    )   # 'common' or 'private'
    status = Column(
        String(20),
        nullable=False,
        default="pending",
        server_default=text("'pending'")
    )
    address = Column(String(255), nullable=False)
    assigned_to = Column(String(50), nullable=True)  # Employee ID of the assigned employee
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now()
    )
    updated_at = Column(
        DateTime(timezone=True),
        onupdate=func.now()
    )
