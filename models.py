from sqlalchemy import Column, String, Integer, DateTime, ForeignKey, text
from sqlalchemy.types import TypeDecorator, CHAR
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from database import Base
import uuid
from pydantic import BaseModel


# Cross-database UUID type
class GUID(TypeDecorator):
    impl = CHAR
    cache_ok = True
    
    def load_dialect_impl(self, dialect):
        if dialect.name == 'postgresql':
            return dialect.type_descriptor(PGUUID())
        else:
            return dialect.type_descriptor(CHAR(32))
    
    def process_bind_param(self, value, dialect):
        if value is None:
            return value
        elif dialect.name == 'postgresql':
            return str(value)
        else:
            if not isinstance(value, uuid.UUID):
                return "%.32x" % uuid.UUID(value).int
            else:
                return "%.32x" % value.int

    def process_result_value(self, value, dialect):
        if value is None:
            return value
        else:
            if not isinstance(value, uuid.UUID):
                return uuid.UUID(value)
            else:
                return value


# ------------------------------------
# USERS TABLE
# ------------------------------------
class User(Base):
    __tablename__ = "users"

    id = Column(
        GUID(),
        primary_key=True,
        default=uuid.uuid4
    )
    fullname = Column(String(255), nullable=False)
    phone = Column(String(50), nullable=False)
    email = Column(String(255), unique=True, nullable=False)
    password = Column(String(255), nullable=True)        # For customers
    employee_id = Column(String(50), nullable=True)      # For employees
    role = Column(
        String(20),
        nullable=False,
        default="customer"
    )  # customer, employee, admin

# ------------------------------------
# COMPLAINTS TABLE
# ------------------------------------
class Complaint(Base):
    __tablename__ = "complaints"

    id = Column(
        GUID(),
        primary_key=True,
        default=uuid.uuid4
    )

    user_id = Column(
        GUID(),
        ForeignKey("users.id"),
        nullable=False
    )

    title = Column(String(255), nullable=False)
    description = Column(String, nullable=True)  # allow null if media-only
    complaint_type = Column(
        String(20),
        nullable=False,
        default="common"
    )   # 'common' or 'private'

    status = Column(
        String(20),
        nullable=False,
        default="pending"
    )

    address = Column(String(255), nullable=False)
    assigned_to = Column(String(50), nullable=True)  # Employee ID

    # ✅ ADD THESE TWO COLUMNS
    media_type = Column(String(20), nullable=True)   # image / audio / video / text
    media_url = Column(String(500), nullable=True)   # complaints/<filename>

    created_at = Column(
        DateTime(timezone=True),
        default=func.now()
    )

    updated_at = Column(
        DateTime(timezone=True),
        onupdate=func.now()
    )

    

class UserProfile(Base):
    __tablename__ = "user_profiles"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    user_id = Column(GUID(), ForeignKey("users.id"), nullable=False)
    
    # Location fields
    province = Column(String(100), nullable=False)
    district = Column(String(100), nullable=False)
    sector = Column(String(100), nullable=False)
    cell = Column(String(100), nullable=False)
    village = Column(String(100), nullable=False)
    about = Column(String)
    
    profile_image = Column(String, nullable=True)  # store image path or URL

    # Relationship to user (optional)
    user = relationship("User", backref="profile")

# ------------------------------------notifications TABLE
class Notification(Base):
    __tablename__ = "notifications"

    id = Column(
        GUID(),
        primary_key=True,
        default=uuid.uuid4
    )

    user_id = Column(
        GUID(),
        ForeignKey("users.id"),
        nullable=False
    )

    sender_id = Column(
        GUID(),
        ForeignKey("users.id"),
        nullable=True
    )

    complaint_id = Column(
        GUID(),
        ForeignKey("complaints.id"),
        nullable=True
    )

    type = Column(String(50), nullable=False)
    title = Column(String(255), nullable=False)
    message = Column(String, nullable=False)

    is_read = Column(
        Integer,
        default=0
    )

    created_at = Column(
        DateTime(timezone=True),
        default=func.now()
    )

    # Relationship to user
    user = relationship("User", foreign_keys=[user_id], backref="notifications")
    sender = relationship("User", foreign_keys=[sender_id])
    complaint = relationship("Complaint", backref="notifications")


class PasswordResetToken(Base):
    __tablename__ = "password_reset_tokens"

    id = Column(
        GUID(),
        primary_key=True,
        default=uuid.uuid4
    )

    email = Column(String, nullable=False)  # <-- Add email field

    otp = Column(String(6), nullable=False)

    expires_at = Column(DateTime(timezone=True), nullable=False)

    is_used = Column(
        Integer,
        default=0
    )

    created_at = Column(
        DateTime(timezone=True),
        default=func.now()
    )
class OTPRequest(BaseModel):
    email: str


# Create UserOTP alias for compatibility with main.py imports
UserOTP = PasswordResetToken