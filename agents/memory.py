from langchain_core.messages import BaseMessage
from langchain_core.messages.utils import trim_messages

MAX_MESSAGES = 24


def recent_messages(messages: list[BaseMessage]) -> list[BaseMessage]:
    """Ventana deslizante segura para el LLM.

    A diferencia de un simple messages[-N:], nunca corta dejando un ToolMessage
    huérfano al inicio (sin su AIMessage con tool_calls correspondiente) - eso
    hace que OpenAI rechace la llamada con 400 "tool message must follow
    tool_calls". start_on="human" hace que, si hace falta, la ventana se
    extienda un poco más atrás hasta un punto de corte válido.
    """
    return trim_messages(
        messages,
        strategy="last",
        token_counter=len,
        max_tokens=MAX_MESSAGES,
        start_on="human",
        include_system=True,
    )
