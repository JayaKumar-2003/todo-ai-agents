import datetime
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from database import Base

class SessionTable(Base):
    __tablename__ = "session_table"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String, index=True, nullable=False)
    chat_id = Column(String, index=True, nullable=False)
    user_id = Column(Integer, ForeignKey("user_table.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)
