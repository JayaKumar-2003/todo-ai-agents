from sqlalchemy import Column, Integer, String
from database import Base

class User(Base):
    __tablename__ = "user_table"

    id = Column(Integer, primary_key=True, index=True)
    user_name = Column(String, nullable=False)
    user_email = Column(String, unique=True, index=True, nullable=False)
    password = Column(String, nullable=False)
