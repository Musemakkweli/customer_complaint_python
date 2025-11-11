from sqlalchemy import Column, Integer, String
from database import Base

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    fullname = Column(String(255), nullable=False)
    phone = Column(String(50), nullable=False)
    email = Column(String(255), unique=True, nullable=False)
    password = Column(String(255))        # for customers
    employee_id = Column(String(50))      # for employees/admins
    role = Column(String(20), nullable=False)  # 'customer', 'employee', 'admin'
