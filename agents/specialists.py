from langchain.agents import create_agent
from langchain.agents.middleware import HumanInTheLoopMiddleware, wrap_model_call
from langchain_openai import ChatOpenAI

from agents.memory import recent_messages
from agents.prompts import COACH_PROMPT, DOLOR_PROMPT, NUTRICION_PROMPT, RUTINA_PROMPT
from agents.state import AgentState
from agents.tools import COACH_TOOLS, DOLOR_TOOLS, NUTRICION_TOOLS, RUTINA_TOOLS

MODEL = "gpt-4o-mini"


@wrap_model_call
async def trim_history(request, handler):
    return await handler(request.override(messages=recent_messages(request.messages)))


def _llm() -> ChatOpenAI:
    return ChatOpenAI(model=MODEL)


rutina_agent = create_agent(
    _llm(), tools=RUTINA_TOOLS, system_prompt=RUTINA_PROMPT, state_schema=AgentState, middleware=[trim_history]
)
nutricion_agent = create_agent(
    _llm(),
    tools=NUTRICION_TOOLS,
    system_prompt=NUTRICION_PROMPT,
    state_schema=AgentState,
    middleware=[
        trim_history,
        HumanInTheLoopMiddleware(interrupt_on={"set_nutrition_targets": {"allowed_decisions": ["approve", "reject"]}}),
    ],
)
dolor_agent = create_agent(
    _llm(),
    tools=DOLOR_TOOLS,
    system_prompt=DOLOR_PROMPT,
    state_schema=AgentState,
    middleware=[
        trim_history,
        HumanInTheLoopMiddleware(interrupt_on={"log_health_event": {"allowed_decisions": ["approve", "reject"]}}),
    ],
)
coach_agent = create_agent(
    _llm(),
    tools=COACH_TOOLS,
    system_prompt=COACH_PROMPT,
    state_schema=AgentState,
    middleware=[
        trim_history,
        HumanInTheLoopMiddleware(interrupt_on={"set_user_goals": {"allowed_decisions": ["approve", "reject"]}}),
    ],
)
