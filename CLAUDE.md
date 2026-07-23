# AuraCoach

## Resumen del proyecto

Bot de Telegram que registra entrenamientos (gimnasio y calistenia) y funciona como asistente conversacional de entrenamiento: RAG híbrido (SQL + búsqueda vectorial) sobre el historial real del usuario, y un sistema multiagente en LangGraph (rutina/progreso, nutrición, dolor muscular, coach de mejora de rutina) con confirmación humana antes de escribir cualquier dato de perfil.

**Estado actual del código:** funcional de punta a punta. `main_bot.py` recibe todo mensaje de Telegram; `parser.py` (regex, sin cambios desde el MVP original) decide si es un log de rutina — en ese caso se valida la categoría y se guarda en Supabase vía `db/logs_repo.py` (con embedding) — o si es una pregunta/charla, en cuyo caso se despacha al grafo de agentes de `agents/graph.py`. Ver [README.md](README.md) para la arquitectura completa, las decisiones de diseño, y cómo evolucionó desde el MVP original (regex + Google Sheets).

## Dónde vive la documentación de proceso

El desarrollo se documentó siguiendo el patrón de ["LLM Wiki"](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f) de Karpathy, en una bóveda de Obsidian (`AuraCouach_vault/AuraCoach/`) con los objetivos, cada decisión de arquitectura y su porqué, especificación de agentes, y un log cronológico.

**Importante:** esa bóveda está en `.gitignore` — es proceso de desarrollo, no parte de la app, y no viaja con el repo cuando se clona desde GitHub. Si estás en una sesión de Claude Code sobre un clon fresco de este repo y `AuraCouach_vault/` no existe, es esperado — no es un enlace roto que haya que arreglar. La fuente de verdad para entender el proyecto en ese caso es el código mismo y el [README.md](README.md).

Si `AuraCouach_vault/AuraCoach/` sí existe localmente (ej. en la máquina donde se desarrolló originalmente), las reglas para mantenerla son:

1. Leer primero `AuraCouach_vault/AuraCoach/index.md` (catálogo de páginas) antes de responder preguntas de arquitectura.
2. Toda decisión de arquitectura nueva se refleja como "ingest" en la página correspondiente (o una nueva), y `index.md` se actualiza en el mismo paso.
3. Todo ingest/query/lint se registra en `AuraCouach_vault/AuraCoach/log.md`, formato `## [YYYY-MM-DD] ingest|query|lint | Título`, append-only.
4. Wikilinks de Obsidian (`[[Nombre de la página]]`) para cruzar referencias entre páginas relacionadas.
5. `AuraCouach_vault/AuraCoach/roadmap.md` es el documento vivo de fases — se actualiza a medida que se completan, no se deja desactualizado.

## Stack

- Python 3.12, gestor de paquetes `uv` (Astral)
- Telegram Bot API (`python-telegram-bot`, polling)
- Supabase (Postgres + `pgvector`), acceso async vía `psycopg`
- `langchain` / `langgraph` (`create_agent`, patrón supervisor, `HumanInTheLoopMiddleware`, checkpointer de Postgres)
- OpenAI (`gpt-4o-mini` + `text-embedding-3-small`) vía `langchain-openai`
- Deploy: VM Linux en Google Cloud Platform, corriendo 24/7
