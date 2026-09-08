import html
import logging
import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from dotenv import load_dotenv
from telegram import InputFile, Update
from telegram.constants import ParseMode
from telegram.ext import Application, ContextTypes, MessageHandler, filters


BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GENERAL_TOPIC_ID = int(os.getenv("GENERAL_TOPIC_ID", "1"))
image_setting = Path(
    os.getenv("WELCOME_IMAGE", "photo_2026-08-28_02-08-41.jpg")
)
WELCOME_IMAGE = image_setting if image_setting.is_absolute() else BASE_DIR / image_setting

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


def start_health_server() -> None:
    """Inicia um servidor HTTP simples em segundo plano para o health check do Render."""
    class HealthHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            self.send_response(200)
            self.send_header("Content-type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"Bot Telegram Online 24/7")

        def log_message(self, format: str, *args: object) -> None:
            pass  # Silencia logs de requisicoes de ping

    port = int(os.getenv("PORT", "10000"))
    try:
        server = HTTPServer(("0.0.0.0", port), HealthHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        logger.info("Servidor HTTP de health check ativo na porta %s", port)
    except Exception as exc:
        logger.warning("Nao foi possivel iniciar servidor de health check na porta %s: %s", port, exc)


def member_mention(user) -> str:
    """Return a visible, clickable mention for a Telegram user."""
    if user.username:
        username = html.escape(user.username)
        return f'<a href="tg://user?id={user.id}">@{username}</a>'

    name = html.escape(user.full_name)
    return f'<a href="tg://user?id={user.id}">{name}</a>'


def welcome_caption(members) -> str:
    mentions = ", ".join(member_mention(member) for member in members)
    greeting = "Bem-vindo" if len(members) == 1 else "Bem-vindos"

    return (
        "<blockquote>"
        f"👋 <b>{greeting}, {mentions}!</b>\n\n"
        "X86 Team é uma comunidade focada em Cybersegurança, Hacking Ético, "
        "Programação, Redes e Tecnologia.\n\n"
        "🔐 Aqui, conhecimento é a nossa principal ferramenta. Exploramos "
        "conceitos de segurança ofensiva e defensiva, análise de "
        "vulnerabilidades, privacidade."
        "</blockquote>"
    )


async def welcome_new_members(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    message = update.effective_message
    if message is None or not message.new_chat_members:
        return

    members = [member for member in message.new_chat_members if not member.is_bot]
    if not members:
        return

    with WELCOME_IMAGE.open("rb") as image_file:
        try:
            await context.bot.send_photo(
                chat_id=message.chat_id,
                message_thread_id=GENERAL_TOPIC_ID if GENERAL_TOPIC_ID > 0 else None,
                photo=InputFile(image_file, filename=WELCOME_IMAGE.name),
                caption=welcome_caption(members),
                parse_mode=ParseMode.HTML,
            )
        except Exception as exc:
            logger.warning(
                "Falha ao enviar para message_thread_id=%s: %s. Tentando sem thread_id...",
                GENERAL_TOPIC_ID,
                exc,
            )
            image_file.seek(0)
            await context.bot.send_photo(
                chat_id=message.chat_id,
                photo=InputFile(image_file, filename=WELCOME_IMAGE.name),
                caption=welcome_caption(members),
                parse_mode=ParseMode.HTML,
            )

    logger.info(
        "Mensagem de boas-vindas enviada para %s em %s",
        ", ".join(member.full_name for member in members),
        message.chat.title or message.chat.id,
    )


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error("Erro ao processar atualização %s", update, exc_info=context.error)


def main() -> None:
    if not TOKEN:
        raise RuntimeError(
            "Defina TELEGRAM_BOT_TOKEN no ambiente ou no arquivo .env."
        )
    if not WELCOME_IMAGE.is_file():
        raise FileNotFoundError(f"Banner não encontrado: {WELCOME_IMAGE}")

    start_health_server()

    application = Application.builder().token(TOKEN).build()
    application.add_handler(
        MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, welcome_new_members)
    )
    application.add_error_handler(error_handler)

    logger.info("Bot de boas-vindas iniciado")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
