import datetime
import json
from sqlalchemy import Column, Integer, String, DateTime, Text, ForeignKey
from sqlalchemy.orm import relationship
from database import Base

class ChatHistory(Base):
    __tablename__ = "chat_history"

    id = Column(Integer, primary_key=True, index=True)
    chat_id = Column(String, unique=True, index=True, nullable=False)
    session_id = Column(String, ForeignKey("session_table.session_id"), nullable=False)
    chat_messages = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

    # Relationship back to SessionTable
    session = relationship("SessionTable", back_populates="chats")

    @property
    def messages(self) -> list:
        """
        Parses and returns the JSON messages string as a list of dictionaries.
        """
        try:
            return json.loads(self.chat_messages)
        except Exception:
            return []
