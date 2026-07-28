import os
from contextlib import asynccontextmanager
from typing import Literal

from langchain_core.messages import AIMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.graph import END, StateGraph
from pydantic import BaseModel

from agents.memory import recent_messages
from agents.prompts import GENERAL_PROMPT, SUPERVISOR_PROMPT
from agents.specialists import coach_agent, dolor_agent, nutricion_agent, rutina_agent
from agents.state import AgentState

MODEL = "gpt-4o-mini"

Route = Literal["rutina", "nutricion", "dolor", "coach", "general"]


class RouteDecision(BaseModel):
    category: Route


async def supervisor_node(state: AgentState) -> dict:
    llm = ChatOpenAI(model=MODEL)
    recientes = recent_messages(state["messages"])
    decision = await llm.with_structured_output(RouteDecision).ainvoke(
        [SystemMessage(content=SUPERVISOR_PROMPT), *recientes]
    )
    return {"next": decision.category}


async def general_node(state: AgentState) -> dict:
    llm = ChatOpenAI(model=MODEL)
    recientes = recent_messages(state["messages"])
    respuesta = await llm.ainvoke([SystemMessage(content=GENERAL_PROMPT), *recientes])
    return {"messages": [AIMessage(content=respuesta.content)]}


def _route(state: AgentState) -> str:
    return state["next"]


def build_graph(checkpointer) -> object:
    builder = StateGraph(AgentState)
    builder.add_node("supervisor", supervisor_node)
    builder.add_node("rutina", rutina_agent)
    builder.add_node("nutricion", nutricion_agent)
    builder.add_node("dolor", dolor_agent)
    builder.add_node("coach", coach_agent)
    builder.add_node("general", general_node)

    builder.set_entry_point("supervisor")
    builder.add_conditional_edges(
        "supervisor",
        _route,
        {"rutina": "rutina", "nutricion": "nutricion", "dolor": "dolor", "coach": "coach", "general": "general"},
    )
    builder.add_edge("rutina", END)
    builder.add_edge("nutricion", END)
    builder.add_edge("dolor", END)
    builder.add_edge("coach", END)
    builder.add_edge("general", END)

    return builder.compile(checkpointer=checkpointer)


@asynccontextmanager
async def get_graph():
    async with AsyncPostgresSaver.from_conn_string(os.environ["SUPABASE_DB_URL"]) as checkpointer:
        await checkpointer.setup()
        yield build_graph(checkpointer)
