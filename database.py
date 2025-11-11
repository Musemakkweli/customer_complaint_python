from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import os
from dotenv import load_dotenv

load_dotenv()  # Load variables from .env

# Prefer a single DATABASE_URL if provided (useful for deployments).
# Fall back to individual DB_* variables for local development.
DATABASE_URL = os.getenv("DATABASE_URL")
# Create engine
engine = create_engine(DATABASE_URL)

# Session
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base class for models
Base = declarative_base()
