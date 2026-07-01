import datetime
from typing import List, Optional
from pydantic import BaseModel

class InteractionCreate(BaseModel):
    user_input: str
    session_id: Optional[str] = None
    chat_id: Optional[str] = None
    user_id: Optional[int] = None

class InteractionResponse(BaseModel):
    id: int
    user_input: str
    response: str
    session_id: Optional[str] = None
    chat_id: Optional[str] = None
    user_id: Optional[int] = None
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

class SessionCreate(BaseModel):
    user_id: Optional[int] = None

class ChatResponse(BaseModel):
    id: int
    chat_id: str
    session_id: str
    created_at: datetime.datetime
    updated_at: datetime.datetime

    class Config:
        from_attributes = True
        orm_mode = True

class SessionResponse(BaseModel):
    id: int
    session_id: str
    user_id: Optional[int]
    created_at: datetime.datetime
    updated_at: datetime.datetime
    chats: List[ChatResponse] = []

    class Config:
        from_attributes = True
        orm_mode = True

class ChatHistoryResponse(BaseModel):
    id: int
    chat_id: str
    session_id: str
    messages: List[dict] = []
    created_at: datetime.datetime
    updated_at: datetime.datetime

    class Config:
        from_attributes = True
        orm_mode = True

class DataTestResponse(BaseModel):
    users: List[UserResponse]
    sessions: List[SessionResponse]
    chat_histories: List[ChatHistoryResponse]

class ChatTestRequest(BaseModel):
    prompt: Optional[str] = "Hello, tell me a short joke."

