import uuid
import json
from typing import Tuple, TypedDict, Optional, List
# pyrefly: ignore [missing-import]
from langgraph.graph import StateGraph, START, END
from sqlalchemy.orm import Session
from models.session import SessionTable
from models.chat_history import ChatHistory
from models.agent_interaction import AgentInteraction
from services.llm import LLMService
from services.todo_docx import add_todo_to_docx, read_todos_from_docx

# pyrefly: ignore [missing-import]
from langchain_core.chat_history import BaseChatMessageHistory
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnablePassthrough

class SQLAlchemyChatMessageHistory(BaseChatMessageHistory):
    """
    Custom LangChain chat message history adapter that integrates directly 
    with the SQLAlchemy ChatHistory model.
    """
    def __init__(self, session_id: str, chat_id: str, db: Session):
        self.session_id = session_id
        self.chat_id = chat_id
        self.db = db
        
        # Load or create the chat history record in the database
        self.chat_history_record = self.db.query(ChatHistory).filter(ChatHistory.chat_id == self.chat_id).first()
        if not self.chat_history_record:
            self.chat_history_record = ChatHistory(
                chat_id=self.chat_id,
                session_id=self.session_id,
                chat_messages=json.dumps([])
            )
            self.db.add(self.chat_history_record)
            self.db.commit()
            self.db.refresh(self.chat_history_record)

    @property
    def messages(self) -> list[BaseMessage]:
        try:
            stored_msgs = json.loads(self.chat_history_record.chat_messages)
        except Exception:
            stored_msgs = []
            
        lg_messages = []
        for msg in stored_msgs:
            role = msg.get("role")
            content = msg.get("content")
            if role == "user":
                lg_messages.append(HumanMessage(content=content))
            elif role == "assistant":
                lg_messages.append(AIMessage(content=content))
            elif role == "system":
                lg_messages.append(SystemMessage(content=content))
        return lg_messages

    def add_messages(self, messages: list[BaseMessage]) -> None:
        try:
            stored_msgs = json.loads(self.chat_history_record.chat_messages)
        except Exception:
            stored_msgs = []
            
        for msg in messages:
            if isinstance(msg, HumanMessage):
                role = "user"
            elif isinstance(msg, AIMessage):
                role = "assistant"
            elif isinstance(msg, SystemMessage):
                role = "system"
            else:
                role = msg.type
            stored_msgs.append({"role": role, "content": msg.content})
            
        self.chat_history_record.chat_messages = json.dumps(stored_msgs)
        self.db.commit()

    def clear(self) -> None:
        self.chat_history_record.chat_messages = json.dumps([])
        self.db.commit()

class AgentState(TypedDict):
    history: str
    user_input: str
    proposed_plan: str
    feedback: str
    is_correct: bool
    iteration: int
    max_iterations: int

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
            messages: A list of LangChain BaseMessage objects.
            
        Returns:
            A formatted history string.
        """
        last_10 = messages[-10:]
        formatted_history = ""
        for msg in last_10:
            role_label = "User" if msg.type == "human" else "Assistant"
            formatted_history += f"{role_label}: {msg.content}\n"
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
        - Uses LangChain's SQLAlchemyChatMessageHistory to manage history.
        - Formats the last 10 messages.
        - Constructs and executes a LangChain LCEL chain to determine tasks.
        - Appends both user message and assistant reply using LangChain's message history.
        - Logs the interaction in the AgentInteraction table and returns it.
        """
        # 1. Retrieve or create the session and chat history
        session_record, chat_history_rec = cls.get_or_create_session(db, session_id, chat_id, user_id)
        current_session_id = session_record.session_id
        current_chat_id = chat_history_rec.chat_id
        
        # 2. Instantiate our SQLAlchemyChatMessageHistory adapter
        history = SQLAlchemyChatMessageHistory(
            session_id=current_session_id,
            chat_id=current_chat_id,
            db=db
        )
        
        # 3. Format the last 10 messages of conversation history (before current user_input is added)
        formatted_history = cls.format_last_10_messages(history.messages)
        
        # 4. Construct prompt and LCEL chain
        prompt = ChatPromptTemplate.from_template("""
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
            {history}

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
        """)
        
        llm = LLMService.get_llm()
        chain = (
            RunnablePassthrough.assign(
                history=lambda x: formatted_history or "No previous history."
            )
            | prompt
            | llm
            | StrOutputParser()
        )
        
        # Critic/Verifier Prompt and Chain
        critic_prompt = ChatPromptTemplate.from_template("""
            You are an autonomous plan verifier/critic.
            Your task is to evaluate the proposed plan against the user's request and conversation history.

            Conversation History:
            {history}

            User Request:
            {user_input}

            Proposed Plan (JSON):
            {proposed_plan}

            Evaluate the proposed plan based on the following criteria:
            1. Does it completely solve the user's request?
            2. Are all tasks necessary and sequence-logical?
            3. Are the assumptions reasonable?
            4. Are there any missing tasks?

            Provide your evaluation in the following JSON format:
            {{
                "is_correct": true/false,
                "feedback": "Detailed feedback describing what is wrong, missing, or needs improvement in the plan. Leave empty if is_correct is true."
            }}
        """)
        
        critic_chain = critic_prompt | llm | StrOutputParser()

        # Refiner Prompt and Chain
        refiner_prompt = ChatPromptTemplate.from_template("""
            You are an autonomous planning refiner.
            Your task is to correct and refine the proposed plan based on feedback from the plan verifier.

            Conversation History:
            {history}

            User Request:
            {user_input}

            Previously Proposed Plan:
            {proposed_plan}

            Verifier Feedback:
            {feedback}

            Refine the plan to address the feedback. Keep the format exactly the same as the proposed plan.

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
        """)
        
        refiner_chain = refiner_prompt | llm | StrOutputParser()

        # Define node functions (using closures for chains)
        async def planner_node(state: AgentState) -> dict:
            try:
                response = await chain.ainvoke({"user_input": state["user_input"]})
                plan = response.strip()
            except Exception as e:
                plan = f"Error: {e}"
            return {"proposed_plan": plan}

        async def critic_node(state: AgentState) -> dict:
            clean_plan = state["proposed_plan"]
            if "```" in clean_plan:
                lines = [line for line in clean_plan.split("\n") if not line.strip().startswith("```")]
                clean_plan = "\n".join(lines).strip()
            
            try:
                response = await critic_chain.ainvoke({
                    "history": state["history"],
                    "user_input": state["user_input"],
                    "proposed_plan": clean_plan
                })
                response = response.strip()
                
                clean_critic = response
                if "```" in clean_critic:
                    lines = [line for line in clean_critic.split("\n") if not line.strip().startswith("```")]
                    clean_critic = "\n".join(lines).strip()
                
                critic_data = json.loads(clean_critic)
                is_correct = critic_data.get("is_correct", False)
                feedback = critic_data.get("feedback", "")
            except Exception as e:
                print(f"Error in critic node: {e}")
                is_correct = True # Bypass loop on errors to avoid infinite loops
                feedback = str(e)
                
            return {"is_correct": is_correct, "feedback": feedback}

        async def refiner_node(state: AgentState) -> dict:
            clean_plan = state["proposed_plan"]
            if "```" in clean_plan:
                lines = [line for line in clean_plan.split("\n") if not line.strip().startswith("```")]
                clean_plan = "\n".join(lines).strip()
                
            next_iteration = state["iteration"] + 1
            print(f"--- Agent Loop (LangGraph): Iteration {next_iteration} ---")
            print(f"Plan rejected. Feedback: {state['feedback']}")
            
            try:
                response = await refiner_chain.ainvoke({
                    "history": state["history"],
                    "user_input": state["user_input"],
                    "proposed_plan": clean_plan,
                    "feedback": state["feedback"]
                })
                plan = response.strip()
            except Exception as e:
                plan = clean_plan # Keep current plan on error
                print(f"Error in refiner node: {e}")
                
            return {"proposed_plan": plan, "iteration": next_iteration}

        def should_continue(state: AgentState):
            if state["is_correct"] or state["iteration"] >= state["max_iterations"]:
                return "end"
            return "refiner"

        # Build LangGraph workflow
        workflow = StateGraph(AgentState)
        
        workflow.add_node("planner", planner_node)
        workflow.add_node("critic", critic_node)
        workflow.add_node("refiner", refiner_node)
        
        workflow.set_entry_point("planner")
        workflow.add_edge("planner", "critic")
        
        workflow.add_conditional_edges(
            "critic",
            should_continue,
            {
                "end": END,
                "refiner": "refiner"
            }
        )
        
        workflow.add_edge("refiner", "critic")
        
        graph = workflow.compile()

        # Run graph
        initial_state = {
            "history": formatted_history or "No previous history.",
            "user_input": user_input,
            "proposed_plan": "",
            "feedback": "",
            "is_correct": False,
            "iteration": 0,
            "max_iterations": 3
        }
        
        final_state = await graph.ainvoke(initial_state)
        current_plan_str = final_state["proposed_plan"]

        # Clean final plan
        clean_json = current_plan_str
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
            print(f"Failed to parse LLM planner JSON: {e}. Output was: {current_plan_str}")
            add_todo_to_docx(f"Unstructured Task: {current_plan_str}", current_session_id)
            
        # 6. Save the new interaction to LangChain's history adapter
        history.add_messages([
            HumanMessage(content=user_input),
            AIMessage(content=current_plan_str)
        ])
        
        # 7. Record the interaction
        interaction = AgentInteraction(
            user_input=user_input,
            response=current_plan_str,
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
