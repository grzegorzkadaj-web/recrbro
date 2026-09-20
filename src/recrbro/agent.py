from __future__ import annotations

from ag_ui_langgraph import add_langgraph_fastapi_endpoint
from copilotkit import LangGraphAGUIAgent
from fastapi import FastAPI
from langchain_core.messages import SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, MessagesState, StateGraph

from recrbro.config import OPENAI_MODEL


async def call_model(state: MessagesState) -> dict:
    model = ChatOpenAI(model=OPENAI_MODEL, temperature=0.2)
    response = await model.ainvoke(
        [
            SystemMessage(
                content=(
                    "You are Recrbro's concise job-search copilot. Help the user improve "
                    "their visible candidate profile and search criteria. Use only facts "
                    "provided in the conversation or page context. Never claim that a job "
                    "is active or suitable without evidence. The website performs searches; "
                    "guide the user and explain results rather than inventing offers."
                )
            ),
            *state["messages"],
        ]
    )
    return {"messages": response}


def add_agent_endpoint(app: FastAPI) -> None:
    builder = StateGraph(MessagesState)
    builder.add_node("call_model", call_model)
    builder.add_edge(START, "call_model")
    builder.add_edge("call_model", END)
    graph = builder.compile(checkpointer=MemorySaver())

    add_langgraph_fastapi_endpoint(
        app=app,
        agent=LangGraphAGUIAgent(
            name="recrbro_agent",
            description="Helps refine candidate profiles and job-search criteria.",
            graph=graph,
        ),
        path="/agent",
    )
