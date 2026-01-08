# fix_passwords.py

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from passlib.context import CryptContext
from models import User  # make sure this matches your project

# ----------------- CONFIG -----------------
DATABASE_URL = "postgresql://postgres.vlxwjiktowwzypadnzun:1NAzkfoMm0n0TPIl@aws-1-eu-central-2.pooler.supabase.com:6543/postgres?sslmode=require"

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# ----------------- FIX PASSWORDS -----------------
def fix_user_passwords():
    db: Session = SessionLocal()
    users = db.query(User).all()
    for user in users:
        if user.password:
            # truncate to 72 chars to satisfy bcrypt limit
            truncated_password = user.password[:72]
            user.password = pwd_context.hash(truncated_password)
            print(f"User {user.id} password rehashed (truncated if long).")
        else:
            # set default password if None
            default_password = "ChangeMe123"
            user.password = pwd_context.hash(default_password)
            print(f"User {user.id} had no password. Default password set.")

    db.commit()
    print("All user passwords fixed successfully!")
    db.close()

# ----------------- RUN SCRIPT -----------------
if __name__ == "__main__":
    fix_user_passwords()
