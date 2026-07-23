# AuraCoach

Un bot de Telegram que empezó como un logger de rutinas de gimnasio por regex, y evolucionó a un **asistente de entrenamiento conversacional** con RAG híbrido (SQL + búsqueda vectorial) y un sistema multiagente en LangGraph que puede ver tu historial real de entrenamiento, hablar de nutrición, dolores musculares, y recomendarte mejoras a tu rutina.

## Del MVP a AuraCoach

**Cómo empezó:** un único handler de Telegram que parseaba mensajes multilínea con expresiones regulares (`parser.py`) y escribía cada ejercicio como fila en una hoja de Google Sheets, vía una Service Account de Google Cloud. Sin base de datos relacional, sin LLM, sin memoria — un logger, nada más.

**Por qué cambió:** un logger no puede responder preguntas. No sabía si estabas progresando, no podía razonar sobre tu historial, no tenía forma de hablar de nutrición o de una molestia muscular. La evolución a AuraCoach agregó exactamente eso, sin romper lo que ya funcionaba:

1. **Migración de almacenamiento**: Google Sheets → Supabase (Postgres + `pgvector`), necesario para combinar consultas estructuradas con búsqueda semántica en el mismo motor.
2. **Capa de RAG**: cada entrenamiento registrado se guarda como fila estructurada *y* como embedding de su representación en texto.
3. **Agentes especializados en LangGraph**: un supervisor enruta cada mensaje conversacional a uno de cuatro agentes (rutina/progreso, nutrición, dolor muscular, coach de mejora de rutina), cada uno con sus propias tools y guardrails.
4. **Confirmación humana**: cualquier escritura sobre el perfil del usuario (objetivos, metas nutricionales, eventos de salud) pasa por una aprobación explícita del usuario antes de guardarse.

El camino de logging original (regex → Sheets) se mantuvo intacto en su lógica — solo cambió el destino final (Supabase en vez de Sheets) — precisamente porque es gratis, determinístico, y no había razón para meterle un LLM a algo que ya funcionaba bien.

## Arquitectura

```
Telegram (mensaje del usuario)
       │
       ▼
main_bot.py
       │
       ▼
parser.py — procesar_mensaje_completo()   [regex, determinístico, sin costo de LLM]
       │
       ├── matchea formato de rutina ──► valida categoría ──► db/logs_repo.py
       │                                                            │
       │                                                            ├─ embedding (rag/embeddings.py)
       │                                                            └─ INSERT en Supabase (workout_logs)
       │
       └── no matchea (es una pregunta/charla) ──► agents/graph.py (LangGraph)
                                                          │
                                                          ▼
                                                supervisor (clasifica intención)
                                                          │
                        ┌───────────┬────────────┼────────────┬───────────┐
                        ▼           ▼            ▼            ▼           ▼
                    rutina     nutrición       dolor        coach      general
                        │           │            │            │
                        └───────────┴────────────┴────────────┘
                                     tools → db/logs_repo.py (Supabase)
                                                          │
                                                          ▼
                                      respuesta a Telegram (con botones ✅/❌
                                      si la acción requiere confirmación)
```

## Decisiones de diseño

- **RAG híbrido, no solo vectorial.** El historial de entrenamiento es tabular (fecha, ejercicio, series, reps, carga). Para preguntas numéricas ("¿cuánto subí en press banca?"), SQL parametrizado es más preciso que similitud de embeddings. La búsqueda vectorial se reserva para preguntas difusas o cuando el usuario no nombra el ejercicio igual que como quedó guardado.
- **Tools acotadas, nunca SQL libre.** Los agentes no generan SQL: llaman funciones concretas y parametrizadas (`get_exercise_history`, `get_recent_sessions`, `get_progress_summary`, `semantic_search_logs`, etc.). Más seguro, más predecible.
- **Patrón supervisor (LangGraph).** Un nodo clasifica la intención del mensaje con salida estructurada y enruta a uno de los cuatro agentes especializados (`langchain.agents.create_agent`), o a un fallback de charla general. Cada agente termina el turno — no hay traspaso entre agentes en esta versión.
- **Confirmación humana antes de escribir.** `set_user_goals`, `set_nutrition_targets` y `log_health_event` requieren aprobación explícita del usuario (botones de Telegram) antes de tocar la base de datos — implementado con `HumanInTheLoopMiddleware` de LangGraph, que pausa el grafo (`interrupt()`) hasta que el usuario decide.
- **Memoria de dos velocidades.** Los datos que importa recordar para siempre (rutinas, objetivos, nutrición, salud) viven en tablas estructuradas y se consultan bajo demanda — nunca dependen de que el LLM "los recuerde" del chat. La conversación en sí usa una ventana deslizante (últimos N mensajes al LLM); el historial completo queda persistido en un checkpointer de Postgres que sobrevive reinicios del bot.
- **Categorías de entrenamiento fijas.** Se encontraron variantes de tipeo en el historial real importado (`Gym inferior` vs `Gym inf`, etc.) que fragmentaban el agrupamiento de sesiones. Ahora hay una lista cerrada de categorías válidas — un mensaje con una categoría fuera de esa lista se rechaza en vez de crear una nueva silenciosamente.

## Stack técnico

| Capa | Tecnología |
|---|---|
| Lenguaje / paquetes | Python 3.12, `uv` (Astral) |
| Bot | `python-telegram-bot` (polling) |
| Base de datos | Supabase (Postgres + `pgvector`), acceso async vía `psycopg` |
| Agentes | `langchain` / `langgraph` (`create_agent`, supervisor pattern, `HumanInTheLoopMiddleware`, checkpointer de Postgres) |
| LLM | OpenAI (`gpt-4o-mini` para chat, `text-embedding-3-small` para embeddings) vía `langchain-openai` |
| Deploy | VM Linux en Google Cloud Platform, corriendo 24/7 |

## Cómo se construyó el contexto

Todo el proceso de evolución de MVP a AuraCoach se documentó siguiendo el patrón de ["LLM Wiki"](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f) descrito por Andrej Karpathy: en vez de re-derivar el razonamiento de arquitectura en cada sesión de desarrollo, se mantuvo una bóveda de Obsidian (`AuraCouach_vault/`, notas internas de desarrollo — **no forma parte de este repo**, ya que es proceso, no producto) con los objetivos del proyecto, cada decisión de arquitectura y su porqué, la especificación de cada agente, y un log cronológico de cambios. Un archivo `CLAUDE.md` en la raíz actuaba como capa de "esquema": las reglas de cómo leer y mantener esa documentación. El resultado práctico fue que cada sesión de desarrollo arrancaba con contexto completo y consistente del proyecto, sin perder decisiones tomadas semanas antes ni repetir discusiones ya cerradas.

## Bugs reales encontrados y resueltos

Construir esto no fue lineal — algunos de los problemas más informativos:

- **`psycopg` async no soporta el `ProactorEventLoop`** por defecto en Windows — hubo que forzar `WindowsSelectorEventLoopPolicy` para desarrollo local (no afecta la VM de producción, que es Linux).
- **Una contraseña de base de datos con un carácter especial sin escapar** rompía tanto el parseo de URLs de Python como, por separado, la autenticación real contra Supabase. Se diagnosticó de forma puramente estructural (contando ocurrencias de `@` en la URL) sin necesitar exponer la contraseña en ningún momento.
- **Migrar de `langgraph.prebuilt.create_react_agent` a `langchain.agents.create_agent`** rompió silenciosamente el flujo de confirmación humana: un `interrupt()` llamado a mano dentro de una tool dejó de pausar el grafo. La causa raíz era un cambio de API real, no cosmético — la forma correcta en la librería nueva es declarar la aprobación vía `HumanInTheLoopMiddleware`, no un `interrupt()` manual. Se corrigió y se re-verificó con los dos caminos (aprobar y rechazar).

## Desarrollo asistido por IA

Este proyecto se construyó en colaboración con [Claude Code](https://claude.com/claude-code) (Anthropic), usado como compañero de diseño e implementación durante toda la evolución de MVP a AuraCoach. Las decisiones de arquitectura, alcance y tradeoffs fueron dirigidas por el autor en cada paso; Claude implementó, escribió las pruebas de verificación de cada fase, y en más de un caso — como la migración de `create_react_agent` a `create_agent` — detectó y corrigió una regresión real introducida por un cambio de API, no solo generó código.

## Extensiones futuras (documentadas, no implementadas)

- **Resumen automático de memoria**: cuando la ventana deslizante de mensajes se llena, resumir en vez de simplemente descartar los mensajes más antiguos.
- **Traspaso entre agentes**: que un agente pueda derivar la conversación a otro especialista a mitad de turno (hoy cada turno termina en un solo agente).
- **Capa HTTP con FastAPI**: exponer el mismo grafo de agentes vía una API REST (endpoint `/chat`, docs OpenAPI automáticas) como canal adicional a Telegram, útil para demos sin depender de la app de Telegram.

## Instalación y configuración

1. **Clonar el repositorio**
   ```bash
   git clone https://github.com/NicolasAVM96/telegram-to-sheets-bot.git
   cd telegram-to-sheets-bot
   ```

2. **Instalar dependencias**

   Se usa [`uv`](https://docs.astral.sh/uv/) (Astral) como gestor de paquetes.
   ```bash
   uv sync
   ```

3. **Variables de entorno**

   Copia `.env.example` a `.env` y completa los tres valores:
   ```bash
   cp .env.example .env
   ```
   - `TELEGRAM_TOKEN`: hablale a [@BotFather](https://t.me/BotFather) en Telegram, `/newbot`, y te lo entrega.
   - `SUPABASE_DB_URL`: connection string de un proyecto de [Supabase](https://supabase.com) en modo **Session pooler** (Project Settings → Database → Connection string).
   - `OPENAI_API_KEY`: desde [platform.openai.com/api-keys](https://platform.openai.com/api-keys).

4. **Base de datos**

   Sobre un proyecto Supabase nuevo, aplica el schema (extensión `vector`, tablas `workout_logs`, `user_goals`, `nutrition_targets`, `health_events`, RLS habilitado). El SQL completo está pensado para correrse vía el SQL Editor de Supabase o el MCP de Supabase.

5. **Correr el bot**
   ```bash
   uv run main_bot.py
   ```
