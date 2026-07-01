import uuid
import json
from sqlalchemy.orm import Session
from models.session import SessionTable
from models.chat_history import ChatHistory
from models.agent_interaction import AgentInteraction
from services.llm import LLMService
from typing import Tuple
from services.todo_docx import add_todo_to_docx, read_todos_from_docx

class ChatService:
    """
    Service to manage chat sessions, conversation history, and LLM completions.
    """
    
    @staticmethod
    def get_or_create_session(
        db: Session, 
        session_id: str = None,
        chat_id: str = None,
        user_id: int = None
    ) -> Tuple[SessionTable, ChatHistory]:
        """
        Retrieves an existing session and chat history, or creates them if they don't exist.
        Supports multiple chat_ids under the same session_id.
        
        Args:
            db: The SQLAlchemy Session.
            session_id: The optional session ID. If not provided, a new one is generated.
            chat_id: The optional chat ID representing the specific conversation context.
            user_id: The optional user ID to link to the session.
            
        Returns:
            A tuple of (SessionTable, ChatHistory).
        """
        if not session_id:
            session_id = str(uuid.uuid4())
            
        session_record = db.query(SessionTable).filter(SessionTable.session_id == session_id).first()
        
        if not session_record:
            # Create Session record (unique per session_id)
            session_record = SessionTable(
                session_id=session_id,
                user_id=user_id
            )
            db.add(session_record)
            db.commit()
            db.refresh(session_record)
        elif user_id and session_record.user_id is None:
            # Dynamically link user_id to session if it wasn't set previously
            session_record.user_id = user_id
            db.commit()
            db.refresh(session_record)
            
        chat_history = None
        if chat_id:
            # Look for exact chat_id belonging to this session
            chat_history = db.query(ChatHistory).filter(
                ChatHistory.chat_id == chat_id,
                ChatHistory.session_id == session_id
            ).first()
            
        if not chat_history:
            if not chat_id:
                # Retrieve the latest chat context associated with this session to resume conversation
                latest_chat = db.query(ChatHistory).filter(
                    ChatHistory.session_id == session_id
                ).order_by(ChatHistory.updated_at.desc()).first()
                
                if latest_chat:
                    chat_history = latest_chat
                    chat_id = latest_chat.chat_id
                else:
                    chat_id = f"chat_{uuid.uuid4().hex}"
            
            # If still no chat_history exists (e.g. brand new session), create it on-demand
            if not chat_history:
                chat_history = ChatHistory(
                    chat_id=chat_id,
                    session_id=session_id,
                    chat_messages=json.dumps([])
                )
                db.add(chat_history)
                db.commit()
                db.refresh(chat_history)
                
        return session_record, chat_history

    @staticmethod
    def format_last_10_messages(messages: list) -> str:
        """
        Takes the last 10 messages from a conversation list and formats them into a prompt context.
        
        Args:
            messages: A list of dict messages.
            
        Returns:
            A formatted history string.
        """
        last_10 = messages[-10:]
        formatted_history = ""
        for msg in last_10:
            role_label = "User" if msg["role"] == "user" else "Assistant"
            formatted_history += f"{role_label}: {msg['content']}\n"
        return formatted_history

    @classmethod
    async def process_message(
        cls, 
        db: Session, 
        user_input: str, 
        session_id: str = None,
        chat_id: str = None,
        user_id: int = None
    ) -> Tuple[AgentInteraction, str, str]:
        """
        Processes a new user message:
        - Retrieves/creates a session and its chat history, supporting multiple chat contexts.
        - Extracts and formats the last 10 messages from history.
        - Constructs a prompt differentiating between conversation history and the current message.
        - Invokes the LLM with this prompt context.
        - Appends both user message and assistant reply to the database history.
        - Logs the interaction in the AgentInteraction table.
        
        Args:
            db: The SQLAlchemy Session.
            user_input: The user's prompt text.
            session_id: The session ID, if any.
            chat_id: The chat ID, if any.
            user_id: The user ID, if any.
            
        Returns:
            A tuple containing the created AgentInteraction record, session_id, and chat_id.
        """
        # 1. Retrieve or create the session and chat history
        session_record, chat_history = cls.get_or_create_session(db, session_id, chat_id, user_id)
        current_session_id = session_record.session_id
        current_chat_id = chat_history.chat_id
        
        # 2. Parse the existing message history
        try:
            messages = json.loads(chat_history.chat_messages)
        except Exception:
            messages = []

        
        # Extract and format the last 10 messages of conversation history (before current user_input is added)
        formatted_history = cls.format_last_10_messages(messages)
        
        # 3. Append the new user message to the local list (to update chat log in database)
        messages.append({"role": "user", "content": user_input})
        
        # Construct prompt differentiating the history and the current user input
        planner_prompt = f"""
            You are an autonomous planning agent.

            Your responsibilities:

            1. Understand the user's request.
            2. Analyze previous conversation history if available.
            3. Determine the user's final goal.
            4. Create a detailed TODO/task list required to complete the goal.
            5. Decide if any external information, web search, or tools are required.
            6. Make reasonable assumptions when information is missing.
            7. Return only valid JSON.

            Conversation History:
            {formatted_history or "No previous history."}

            Current User Request:
            {user_input}

            Return JSON in the following format:

            {{
                "goal": "",
                "requires_external_data": true,
                "assumptions": [],
                "tasks": [
                    {{
                        "task_id": 1,
                        "task_name": "",
                        "reason": ""
                    }}
                ]
            }}
        """

        # 4. Invoke the LLM using the structured prompt
        try:
            llm_response = await LLMService.complete_prompt(prompt=planner_prompt)
            choices = llm_response.get("choices", [])
            if choices:
                assistant_response = choices[0].get("message", {}).get("content", "").strip()
            else:
                assistant_response = "Error: No response generated from the LLM."
        except Exception as e:
            assistant_response = f"Error communicating with LLM: {str(e)}"

                # ... (After getting the assistant_response from the LLM) ...
        
        # 1. Parse the LLM's Planner JSON and write it to the DOCX file
        
        # Clean up any markdown code blocks (e.g. ```json ... ```) if the LLM wrapped it
        clean_json = assistant_response.strip()
        if "```" in clean_json:
            lines = [line for line in clean_json.split("\n") if not line.strip().startswith("```")]
            clean_json = "\n".join(lines).strip()
            
        try:
            planner_data = json.loads(clean_json)
            tasks = planner_data.get("tasks", [])
            
            for task in tasks:
                task_name = task.get("task_name")
                reason = task.get("reason", "")
                
                if task_name:
                    # Construct a descriptive task line to write to Word
                    task_description = f"{task_name} (Reason: {reason})" if reason else task_name
                    # Write it to todos_{session_id}.docx
                    add_todo_to_docx(task_description, current_session_id)
                    
        except json.JSONDecodeError as e:
            # Fallback if the LLM output is not valid JSON
            print(f"Failed to parse LLM planner JSON: {e}. Output was: {assistant_response}")
            add_todo_to_docx(f"Unstructured Task: {assistant_response}", current_session_id)

            
        # 5. Append assistant response to history
        messages.append({"role": "assistant", "content": assistant_response})
        
        # 6. Save updated history back to database
        chat_history.chat_messages = json.dumps(messages)
        
        # 7. Record the interaction
        interaction = AgentInteraction(
            user_input=user_input,
            response=assistant_response,
            session_id=current_session_id,
            chat_id=current_chat_id,
            user_id=session_record.user_id
        )
        db.add(interaction)
        db.commit()
        db.refresh(interaction)
        
        return interaction, current_session_id, current_chat_id

    @staticmethod
    def create_session(db: Session, user_id: int = None) -> SessionTable:
        """
        Creates a new session, optionally mapping to user_id.
        Does NOT create a ChatHistory entry until the first user message is processed.
        """
        session_id = str(uuid.uuid4())
        
        session_record = SessionTable(
            session_id=session_id,
            user_id=user_id
        )
        db.add(session_record)
        db.commit()
        db.refresh(session_record)
        return session_record

    @staticmethod
    def get_user_sessions(db: Session, user_id: int) -> list[SessionTable]:
        """
        Retrieves all sessions associated with a specific user_id.
        """
        return db.query(SessionTable).filter(SessionTable.user_id == user_id).all()
