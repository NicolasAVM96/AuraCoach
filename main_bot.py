import asyncio
import os
import sys
from contextlib import AsyncExitStack

from dotenv import load_dotenv

# agents.graph (importado más abajo) construye los clientes de OpenAI al cargarse
# el módulo, así que el .env debe estar cargado ANTES de esa importación.
load_dotenv()

from langchain_core.messages import HumanMessage
from langgraph.types import Command
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ChatAction
from telegram.ext import Application, CallbackQueryHandler, ContextTypes, MessageHandler, filters

# Importacion de módulos
from agents.graph import get_graph
from db.logs_repo import insert_log
from parser import procesar_mensaje_completo

if sys.platform == "win32":
    # psycopg async no soporta el ProactorEventLoop por defecto en Windows.
    # No afecta producción (VM Linux).
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

TOKEN = os.getenv("TELEGRAM_TOKEN")

CATEGORIAS_VALIDAS = ["Gym sup", "Gym inf", "Gym sup/inf", "Calistenia", "Rutina complementaria"]


def _es_categoria_valida(tipo_entreno: str) -> bool:
    return tipo_entreno.strip().lower() in {c.lower() for c in CATEGORIAS_VALIDAS}


def _botones_confirmacion() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("✅ Confirmar", callback_data="confirm:approve"),
                InlineKeyboardButton("❌ Cancelar", callback_data="confirm:reject"),
            ]
        ]
    )


def _describir_accion(action: dict) -> str:
    nombre = action["name"]
    args = action["args"]
    if nombre == "set_user_goals":
        notas = f" {args['notes']}" if args.get("notes") else ""
        return f"Anoté como objetivo: {', '.join(args['goals'])}.{notas}\n¿Confirmas guardar esto?"
    if nombre == "set_nutrition_targets":
        return (
            f"Metas propuestas: {args['kcal']} kcal, {args['protein_g']}g proteína, "
            f"{args['carbs_g']}g carbos, {args['fat_g']}g grasas.\n¿Confirmas guardar esto?"
        )
    if nombre == "log_health_event":
        return f"Registrar {args['tipo']}: {args['descripcion']} (desde {args['fecha_inicio']}).\n¿Confirmas guardar esto?"
    return f"¿Confirmas ejecutar {nombre} con {args}?"


async def _responder_resultado(chat_id: str, context: ContextTypes.DEFAULT_TYPE, result: dict, config: dict) -> None:
    if "__interrupt__" in result:
        action = result["__interrupt__"][0].value["action_requests"][0]
        descripcion = _describir_accion(action)
        context.chat_data["pendiente"] = {"config": config, "descripcion": descripcion}
        await context.bot.send_message(chat_id=chat_id, text=descripcion, reply_markup=_botones_confirmacion())
        return

    context.chat_data.pop("pendiente", None)
    respuesta = result["messages"][-1].content
    await context.bot.send_message(chat_id=chat_id, text=respuesta)


async def _procesar_log(chat_id: str, context: ContextTypes.DEFAULT_TYPE, lista_ejercicios: list[dict]) -> None:
    tipo_entreno = lista_ejercicios[0]["tipo_entreno"]
    if not _es_categoria_valida(tipo_entreno):
        categorias = "\n".join(f"- {c}" for c in CATEGORIAS_VALIDAS)
        await context.bot.send_message(
            chat_id=chat_id,
            text=f'❌ "{tipo_entreno}" no es una categoría válida. Usa una de estas:\n{categorias}',
        )
        return

    await context.bot.send_message(chat_id=chat_id, text="⏳ Procesando rutina...")

    exitos = 0
    errores = 0
    for ejercicio_dict in lista_ejercicios:
        if await insert_log(chat_id, ejercicio_dict):
            exitos += 1
        else:
            errores += 1

    respuesta = f"✅ ¡Listo, Nico! Se guardaron {exitos} ejercicios."
    if errores > 0:
        respuesta += f"\n⚠️ Hubo problema guardando {errores} ejercicios."
    await context.bot.send_message(chat_id=chat_id, text=respuesta)


async def _procesar_chat(chat_id: str, context: ContextTypes.DEFAULT_TYPE, texto: str) -> None:
    await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
    graph = context.application.bot_data["graph"]
    config = {"configurable": {"thread_id": chat_id}}
    result = await graph.ainvoke({"messages": [HumanMessage(content=texto)], "chat_id": chat_id}, config=config)
    await _responder_resultado(chat_id, context, result, config)


async def recibir_mensaje(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Esta función se ejecuta cada vez que le envías un mensaje de texto al bot"""
    mensaje_texto = update.message.text
    chat_id = str(update.message.chat_id)

    pendiente = context.chat_data.get("pendiente")
    if pendiente:
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"Antes de seguir, necesito que confirmes lo anterior:\n\n{pendiente['descripcion']}",
            reply_markup=_botones_confirmacion(),
        )
        return

    lista_ejercicios = procesar_mensaje_completo(mensaje_texto)

    if lista_ejercicios:
        await _procesar_log(chat_id, context, lista_ejercicios)
        return

    await _procesar_chat(chat_id, context, mensaje_texto)


async def manejar_confirmacion(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Maneja el click en los botones de Confirmar/Cancelar."""
    query = update.callback_query
    await query.answer()
    chat_id = str(update.effective_chat.id)

    pendiente = context.chat_data.get("pendiente")
    if not pendiente:
        await query.edit_message_reply_markup(reply_markup=None)
        await context.bot.send_message(chat_id=chat_id, text="Ya no hay ninguna confirmación pendiente.")
        return

    decision = "approve" if query.data == "confirm:approve" else "reject"
    await query.edit_message_reply_markup(reply_markup=None)

    graph = context.application.bot_data["graph"]
    config = pendiente["config"]
    result = await graph.ainvoke(Command(resume={"decisions": [{"type": decision}]}), config=config)
    await _responder_resultado(chat_id, context, result, config)


async def post_init(application: Application) -> None:
    stack = AsyncExitStack()
    graph = await stack.enter_async_context(get_graph())
    application.bot_data["graph"] = graph
    application.bot_data["exit_stack"] = stack


async def post_shutdown(application: Application) -> None:
    stack: AsyncExitStack = application.bot_data["exit_stack"]
    await stack.aclose()


if __name__ == '__main__':
    print("🤖 Iniciando el Bot de Entrenamiento...")

    # Construimos la aplicación del bot
    app = Application.builder().token(TOKEN).post_init(post_init).post_shutdown(post_shutdown).build()

    # Mensajes de texto -> log de rutina o chat con los agentes
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, recibir_mensaje))
    # Clicks en los botones de confirmación
    app.add_handler(CallbackQueryHandler(manejar_confirmacion, pattern="^confirm:"))

    print("✅ Bot encendido y escuchando. ¡Envíale un mensaje desde tu celular!")
    # Mantenemos el script corriendo
    app.run_polling()
