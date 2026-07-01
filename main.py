import uvicorn
from fastapi import FastAPI, Depends
from sqlalchemy.orm import Session

import database
import models
import schemas

# Create database tables
models.Base.metadata.create_all(bind=database.engine)

app = FastAPI(
    title="TODO Agent API",
    description="A FastAPI backend service for the TODO Agent with SQLite storage.",
    version="1.0.0"
)

@app.post("/agent", response_model=schemas.InteractionResponse)
async def process_agent_task(
    payload: schemas.InteractionCreate, 
    db: Session = Depends(database.get_db)
):
    # Simulated agent response based on user input
    agent_response = f"Agent processed task: '{payload.user_input}'. Status: Completed."
    
    # Store interaction in SQLite database
    db_interaction = models.AgentInteraction(
        user_input=payload.user_input,
        response=agent_response
    )
    db.add(db_interaction)
    db.commit()
    db.refresh(db_interaction)
    
    return db_interaction

@app.get("/data-test", response_model=schemas.DataTestResponse)
async def data_test(db: Session = Depends(database.get_db)):
    # 1. Check if mock data already exists. If not, seed it.
    user_count = db.query(models.User).count()
    if user_count == 0:
        # Create a sample user
        test_user = models.User(
            user_name="John Doe",
            user_email="john.doe@example.com",
            password="securepassword123"
        )
        db.add(test_user)
        db.commit()
        db.refresh(test_user)

        # Create a sample chat history
        test_chat = models.ChatHistory(
            chat_id="chat_session_001",
            chat_messages="[{\"role\": \"user\", \"content\": \"Hi, agent!\"}, {\"role\": \"assistant\", \"content\": \"Hello, how can I help you?\"}]"
        )
        db.add(test_chat)
        db.commit()
        db.refresh(test_chat)

        # Create a sample session referencing the user
        test_session = models.SessionTable(
            session_id="session_xyz_987",
            chat_id=test_chat.chat_id,
            user_id=test_user.id
        )
        db.add(test_session)
        db.commit()
        db.refresh(test_session)

    # 2. Query all items
    users = db.query(models.User).all()
    sessions = db.query(models.SessionTable).all()
    chat_histories = db.query(models.ChatHistory).all()

    return {
        "users": users,
        "sessions": sessions,
        "chat_histories": chat_histories
    }

if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
