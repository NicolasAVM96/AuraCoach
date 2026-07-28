from datetime import datetime

from psycopg.rows import dict_row

from db.client import get_pool
from rag.embeddings import embed_text


def log_to_text(fecha: str, tipo_entreno: str, ejercicio: str, series: int, reps: int, carga: str) -> str:
    return f"{fecha} - {tipo_entreno} - {ejercicio}: {series} series x {reps} reps @ {carga}"


def _fuzzy_ilike_clause(query: str) -> tuple[str, list[str]]:
    """Arma un WHERE que matchea si CUALQUIER palabra significativa de `query`
    aparece en `ejercicio`, en vez de exigir la frase completa como substring.

    Evita que una búsqueda como "flexiones de brazos" deje afuera filas
    guardadas como "Flexiones piso" o "Flexiones" (mismo ejercicio, nombre
    más corto) solo porque no contienen la frase exacta.
    """
    palabras = [p for p in query.split() if len(p) > 2] or [query]
    clausula = " or ".join(["ejercicio ilike %s"] * len(palabras))
    valores = [f"%{p}%" for p in palabras]
    return clausula, valores


async def insert_log(chat_id: str, ejercicio: dict) -> bool:
    try:
        fecha = datetime.strptime(ejercicio["fecha"], "%d/%m/%Y").date()
        texto = log_to_text(
            ejercicio["fecha"],
            ejercicio["tipo_entreno"],
            ejercicio["ejercicio"],
            ejercicio["series"],
            ejercicio["reps"],
            ejercicio["carga"],
        )
        embedding = await embed_text(texto)

        pool = await get_pool()
        async with pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    insert into workout_logs (chat_id, fecha, tipo_entreno, ejercicio, series, reps, carga, embedding)
                    values (%s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        chat_id,
                        fecha,
                        ejercicio["tipo_entreno"],
                        ejercicio["ejercicio"],
                        ejercicio["series"],
                        ejercicio["reps"],
                        ejercicio["carga"],
                        embedding,
                    ),
                )
        return True
    except Exception as e:
        print(f"Error guardando en Supabase: {e}")
        return False


async def get_exercise_history(chat_id: str, ejercicio: str, limit: int = 20) -> list[dict]:
    clausula, valores = _fuzzy_ilike_clause(ejercicio)
    pool = await get_pool()
    async with pool.connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                f"""
                select fecha, tipo_entreno, ejercicio, series, reps, carga
                from workout_logs
                where chat_id = %s and ({clausula})
                order by fecha desc
                limit %s
                """,
                (chat_id, *valores, limit),
            )
            return await cur.fetchall()


async def get_progress_summary(chat_id: str, ejercicio: str, limit: int = 20) -> list[dict]:
    clausula, valores = _fuzzy_ilike_clause(ejercicio)
    pool = await get_pool()
    async with pool.connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                f"""
                select fecha, series, reps, carga
                from workout_logs
                where chat_id = %s and ({clausula})
                order by fecha asc
                limit %s
                """,
                (chat_id, *valores, limit),
            )
            return await cur.fetchall()


async def get_recent_sessions(chat_id: str, n: int = 5, tipo_entreno: str | None = None) -> list[dict]:
    pool = await get_pool()
    async with pool.connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            if tipo_entreno:
                await cur.execute(
                    """
                    select fecha, tipo_entreno, ejercicio, series, reps, carga
                    from workout_logs
                    where chat_id = %s and tipo_entreno ilike %s
                    order by fecha desc, id asc
                    """,
                    (chat_id, tipo_entreno),
                )
            else:
                await cur.execute(
                    """
                    select fecha, tipo_entreno, ejercicio, series, reps, carga
                    from workout_logs
                    where chat_id = %s
                    order by fecha desc, id asc
                    """,
                    (chat_id,),
                )
            rows = await cur.fetchall()

    sessions: dict[tuple, dict] = {}
    for row in rows:
        key = (row["fecha"], row["tipo_entreno"])
        if key not in sessions:
            if len(sessions) >= n:
                continue
            sessions[key] = {"fecha": row["fecha"], "tipo_entreno": row["tipo_entreno"], "ejercicios": []}
        sessions[key]["ejercicios"].append(
            {"ejercicio": row["ejercicio"], "series": row["series"], "reps": row["reps"], "carga": row["carga"]}
        )
    return list(sessions.values())


async def semantic_search_logs(chat_id: str, query_text: str, k: int = 5) -> list[dict]:
    embedding = await embed_text(query_text)
    pool = await get_pool()
    async with pool.connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                select fecha, tipo_entreno, ejercicio, series, reps, carga,
                       1 - (embedding <=> %s::vector) as similarity
                from workout_logs
                where chat_id = %s
                order by embedding <=> %s::vector
                limit %s
                """,
                (embedding, chat_id, embedding, k),
            )
            return await cur.fetchall()


async def get_current_goals(chat_id: str) -> dict | None:
    pool = await get_pool()
    async with pool.connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                select goals, notes, created_at
                from user_goals
                where chat_id = %s
                order by created_at desc
                limit 1
                """,
                (chat_id,),
            )
            return await cur.fetchone()


async def set_user_goals(chat_id: str, goals: list[str], notes: str = "") -> None:
    pool = await get_pool()
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "insert into user_goals (chat_id, goals, notes) values (%s, %s, %s)",
                (chat_id, goals, notes),
            )


async def get_current_nutrition_targets(chat_id: str) -> dict | None:
    pool = await get_pool()
    async with pool.connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                select kcal, protein_g, carbs_g, fat_g, created_at
                from nutrition_targets
                where chat_id = %s
                order by created_at desc
                limit 1
                """,
                (chat_id,),
            )
            return await cur.fetchone()


async def set_nutrition_targets(chat_id: str, kcal: int, protein_g: int, carbs_g: int, fat_g: int) -> None:
    pool = await get_pool()
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                insert into nutrition_targets (chat_id, kcal, protein_g, carbs_g, fat_g)
                values (%s, %s, %s, %s, %s)
                """,
                (chat_id, kcal, protein_g, carbs_g, fat_g),
            )


async def get_active_health_events(chat_id: str) -> list[dict]:
    pool = await get_pool()
    async with pool.connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                select tipo, descripcion, fecha_inicio, fecha_fin
                from health_events
                where chat_id = %s and (fecha_fin is null or fecha_fin >= current_date - interval '14 days')
                order by fecha_inicio desc
                """,
                (chat_id,),
            )
            return await cur.fetchall()


async def log_health_event(
    chat_id: str, tipo: str, descripcion: str, fecha_inicio: str, fecha_fin: str | None = None
) -> None:
    pool = await get_pool()
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                insert into health_events (chat_id, tipo, descripcion, fecha_inicio, fecha_fin)
                values (%s, %s, %s, %s, %s)
                """,
                (chat_id, tipo, descripcion, fecha_inicio, fecha_fin),
            )
