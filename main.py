import os
import uvicorn
from fastapi import FastAPI, Depends
from sqlalchemy.orm import Session
from dotenv import load_dotenv

import database
import models
import schemas

# Load environment variables from .env
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, ".env"))


# Create database tables
models.Base.metadata.create_all(bind=database.engine)

app = FastAPI(
    title="TODO Agent API",
    description="A FastAPI backend service for the TODO Agent with SQLite storage and OpenRouter integration.",
    version="1.0.0"
)

from services.chat import ChatService

# To run the application:
# uvicorn main:app --reload
#
# To test this endpoint:
# curl -X POST "http://127.0.0.1:8000/agent" \
#      -H "Content-Type: application/json" \
#      -d '{"user_input": "Hello Agent!", "session_id": "optional-session-id", "chat_id": "optional-chat-id", "user_id": 1}'
@app.post("/agent", response_model=schemas.InteractionResponse)
async def process_agent_task(
    payload: schemas.InteractionCreate, 
    db: Session = Depends(database.get_db)
):
    db_interaction, session_id, chat_id = await ChatService.process_message(
        db=db,
        user_input=payload.user_input,
        session_id=payload.session_id,
        chat_id=payload.chat_id,
        user_id=payload.user_id
    )
    return db_interaction


# To generate/create a new session ID (optionally for a user):
# curl -X POST "http://127.0.0.1:8000/session" \
#      -H "Content-Type: application/json" \
#      -d '{"user_id": 1}'
@app.post("/session", response_model=schemas.SessionResponse)
def create_session(
    payload: schemas.SessionCreate, 
    db: Session = Depends(database.get_db)
):
    return ChatService.create_session(db=db, user_id=payload.user_id)


# To get a logged-in user's active session IDs:
# curl -X GET "http://127.0.0.1:8000/sessions/user/1"
@app.get("/sessions/user/{user_id}", response_model=list[schemas.SessionResponse])
def get_user_sessions(
    user_id: int, 
    db: Session = Depends(database.get_db)
):
    return ChatService.get_user_sessions(db=db, user_id=user_id)


if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
