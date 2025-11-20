from sqlalchemy import Column, String, DateTime, ForeignKey, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from database import Base
import uuid


class User(Base):
    __tablename__ = "users"

    # Use UUID primary key (Postgres). Python-side default uses uuid.uuid4(),
    # DB-side server_default uses gen_random_uuid() (requires pgcrypto extension).
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()"))
    fullname = Column(String(255), nullable=False)
    phone = Column(String(50), nullable=False)
    email = Column(String(255), unique=True, nullable=False)
    password = Column(String(255))        # for customers
    # employee_id should be NULL by default (nullable=True)
    employee_id = Column(String(50), nullable=True)
    # role defaults to 'customer' - set both Python default and a DB server default
    role = Column(String(20), nullable=False, default="customer", server_default=text("'customer'"))  # 'customer', 'employee', 'admin'


class Complaint(Base):
    __tablename__ = "complaints"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    title = Column(String, nullable=False)
    description = Column(String, nullable=False)
    status = Column(String, default="pending")
    created_at = Column(DateTime(timezone=True), server_default=func.now())