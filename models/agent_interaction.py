import datetime
from sqlalchemy import Column, Integer, String, DateTime
from database import Base

class AgentInteraction(Base):
    __tablename__ = "agent_interactions"

    id = Column(Integer, primary_key=True, index=True)
    user_input = Column(String, nullable=False)
    response = Column(String, nullable=False)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)
