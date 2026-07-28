from typing import Annotated, Literal

from langchain_core.tools import tool
from langgraph.prebuilt import InjectedState

from db import logs_repo

ChatId = Annotated[str, InjectedState("chat_id")]


@tool
async def get_exercise_history(ejercicio: str, chat_id: ChatId) -> str:
    """Historial de un ejercicio específico: fecha, series, reps y carga en cada sesión registrada."""
    rows = await logs_repo.get_exercise_history(chat_id, ejercicio)
    if not rows:
        return f"No hay historial registrado para '{ejercicio}'."
    return "\n".join(f"{r['fecha']}: {r['series']}x{r['reps']} @ {r['carga']}" for r in rows)


@tool
async def get_progress_summary(ejercicio: str, chat_id: ChatId) -> str:
    """Evolución cronológica (de más antiguo a más reciente) de un ejercicio: series, reps y carga."""
    rows = await logs_repo.get_progress_summary(chat_id, ejercicio)
    if not rows:
        return f"No hay historial registrado para '{ejercicio}'."
    return "\n".join(f"{r['fecha']}: {r['series']}x{r['reps']} @ {r['carga']}" for r in rows)


def _format_sessions(sessions: list[dict]) -> str:
    partes = []
    for s in sessions:
        ejercicios = ", ".join(f"{e['ejercicio']} {e['series']}x{e['reps']} @ {e['carga']}" for e in s["ejercicios"])
        partes.append(f"{s['fecha']} ({s['tipo_entreno']}): {ejercicios}")
    return "\n".join(partes)


@tool
async def get_recent_sessions(n: int, chat_id: ChatId) -> str:
    """Últimas N sesiones de entrenamiento registradas, con sus ejercicios."""
    sessions = await logs_repo.get_recent_sessions(chat_id, n)
    if not sessions:
        return "No hay sesiones registradas."
    return _format_sessions(sessions)


@tool
async def get_sessions_by_category(categoria: str, n: int, chat_id: ChatId) -> str:
    """Últimas N sesiones de una categoría de entrenamiento (no de un ejercicio puntual).

    Categorías válidas: "Gym sup" (tren superior), "Gym inf" (piernas), "Gym sup/inf" (full body),
    "Calistenia" (peso corporal), "Rutina complementaria". Usa esta tool cuando el usuario pregunte
    por un grupo muscular o tipo de rutina (ej. "piernas", "gym inf", "tren superior") en vez de un
    ejercicio con nombre propio.
    """
    sessions = await logs_repo.get_recent_sessions(chat_id, n, tipo_entreno=categoria)
    if not sessions:
        return f"No hay sesiones registradas para la categoría '{categoria}'."
    return _format_sessions(sessions)


@tool
async def semantic_search_logs(query: str, chat_id: ChatId) -> str:
    """Busca en el historial de entrenamiento por significado, no por texto exacto.

    Útil para preguntas difusas o cuando no se sabe el nombre exacto del ejercicio.
    """
    rows = await logs_repo.semantic_search_logs(chat_id, query, k=5)
    if not rows:
        return "No se encontraron resultados relevantes."
    return "\n".join(
        f"{r['fecha']} ({r['tipo_entreno']}) {r['ejercicio']}: {r['series']}x{r['reps']} @ {r['carga']}"
        for r in rows
    )


@tool
async def get_current_goals(chat_id: ChatId) -> str:
    """Objetivos de entrenamiento actuales del usuario (el más reciente declarado)."""
    goals = await logs_repo.get_current_goals(chat_id)
    if not goals:
        return "El usuario no ha declarado objetivos todavía."
    return f"Objetivos: {', '.join(goals['goals'])}. Notas: {goals['notes'] or '(sin notas)'}"


@tool
async def get_current_nutrition_targets(chat_id: ChatId) -> str:
    """Metas nutricionales actuales del usuario (kcal, proteína, carbos, grasas)."""
    targets = await logs_repo.get_current_nutrition_targets(chat_id)
    if not targets:
        return "El usuario no ha declarado metas nutricionales todavía."
    return (
        f"kcal: {targets['kcal']}, proteína: {targets['protein_g']}g, "
        f"carbos: {targets['carbs_g']}g, grasas: {targets['fat_g']}g"
    )


@tool
async def get_active_health_events(chat_id: ChatId) -> str:
    """Dolores, lesiones o reposos activos/recientes del usuario."""
    events = await logs_repo.get_active_health_events(chat_id)
    if not events:
        return "No hay eventos de salud activos registrados."
    return "\n".join(
        f"{e['tipo']} desde {e['fecha_inicio']}"
        + (f" hasta {e['fecha_fin']}" if e["fecha_fin"] else " (en curso)")
        + f": {e['descripcion']}"
        for e in events
    )


@tool
async def set_user_goals(
    goals: list[Literal["perder_grasa", "ganar_musculo", "salud", "fuerza"]],
    notes: str,
    chat_id: ChatId,
) -> str:
    """Guarda o actualiza los objetivos de entrenamiento del usuario.

    La confirmación humana antes de ejecutar esta tool la maneja HumanInTheLoopMiddleware
    (ver agents/specialists.py), no esta función.
    """
    await logs_repo.set_user_goals(chat_id, goals, notes)
    return "Objetivos guardados correctamente."


@tool
async def set_nutrition_targets(kcal: int, protein_g: int, carbs_g: int, fat_g: int, chat_id: ChatId) -> str:
    """Guarda o actualiza las metas nutricionales diarias del usuario.

    La confirmación humana antes de ejecutar esta tool la maneja HumanInTheLoopMiddleware
    (ver agents/specialists.py), no esta función.
    """
    await logs_repo.set_nutrition_targets(chat_id, kcal, protein_g, carbs_g, fat_g)
    return "Metas nutricionales guardadas correctamente."


@tool
async def log_health_event(
    tipo: Literal["dolor_muscular", "resfrio", "lesion", "otro"],
    descripcion: str,
    fecha_inicio: str,
    chat_id: ChatId,
    fecha_fin: str | None = None,
) -> str:
    """Registra un dolor, resfrío, lesión o reposo.

    fecha_inicio y fecha_fin van en formato YYYY-MM-DD. fecha_fin es opcional (evento en curso).
    La confirmación humana antes de ejecutar esta tool la maneja HumanInTheLoopMiddleware
    (ver agents/specialists.py), no esta función.
    """
    await logs_repo.log_health_event(chat_id, tipo, descripcion, fecha_inicio, fecha_fin)
    return "Evento de salud guardado correctamente."


RUTINA_TOOLS = [
    get_exercise_history,
    get_progress_summary,
    get_recent_sessions,
    get_sessions_by_category,
    semantic_search_logs,
    get_current_goals,
]
NUTRICION_TOOLS = [get_recent_sessions, get_current_nutrition_targets, set_nutrition_targets]
DOLOR_TOOLS = [get_exercise_history, get_recent_sessions, get_active_health_events, log_health_event]
COACH_TOOLS = [
    get_recent_sessions,
    get_sessions_by_category,
    get_progress_summary,
    get_exercise_history,
    get_current_goals,
    set_user_goals,
]
