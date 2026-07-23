from langchain.agents.middleware import AgentState as BaseAgentState


class AgentState(BaseAgentState):
    chat_id: str
    next: str
