# utils/notifications.py
from sqlalchemy.orm import Session
from models import Notification
import uuid

def create_notification(
    db: Session,
    user_id: uuid.UUID,
    sender_id: uuid.UUID,
    complaint_id: uuid.UUID,
    type: str,
    title: str,
    message: str
):
    notification = Notification(
        user_id=user_id,
        sender_id=sender_id,
        complaint_id=complaint_id,
        type=type,
        title=title,
        message=message
    )
    db.add(notification)
    db.commit()
    db.refresh(notification)
    return notification
