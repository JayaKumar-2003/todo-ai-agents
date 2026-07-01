import datetime
from typing import List, Optional
from pydantic import BaseModel

class InteractionCreate(BaseModel):
    user_input: str

class InteractionResponse(BaseModel):
    id: int
    user_input: str
    response: str
    timestamp: datetime.datetime

    class Config:
        from_attributes = True
        orm_mode = True

class UserResponse(BaseModel):
    id: int
    user_name: str
    user_email: str

    class Config:
        from_attributes = True
        orm_mode = True

class SessionResponse(BaseModel):
    id: int
    session_id: str
    chat_id: str
    user_id: Optional[int]
    created_at: datetime.datetime
    updated_at: datetime.datetime

    class Config:
        from_attributes = True
        orm_mode = True

class ChatHistoryResponse(BaseModel):
    id: int
    chat_id: str
    chat_messages: str
    created_at: datetime.datetime
    updated_at: datetime.datetime

    class Config:
        from_attributes = True
        orm_mode = True

class DataTestResponse(BaseModel):
    users: List[UserResponse]
    sessions: List[SessionResponse]
    chat_histories: List[ChatHistoryResponse]
