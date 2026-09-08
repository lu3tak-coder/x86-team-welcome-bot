import html
import logging
import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from dotenv import load_dotenv
from telegram import ChatMemberUpdated, InputFile, Update
from telegram.constants import ChatMemberStatus, ParseMode
from telegram.ext import (
    Application,
    ChatMemberHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    TypeHandler,
    filters,
)

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GENERAL_TOPIC_ID = int(os.getenv("GENERAL_TOPIC_ID", "1") or "0")
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


async def send_welcome_photo(bot, chat_id: int, members: list, thread_id: int | None = None) -> bool:
    """Envia o banner e texto de boas-vindas com fallback caso o tópico não exista."""
    target_thread = thread_id if thread_id is not None else (GENERAL_TOPIC_ID if GENERAL_TOPIC_ID > 0 else None)
    try:
        with WELCOME_IMAGE.open("rb") as image_file:
            await bot.send_photo(
                chat_id=chat_id,
                message_thread_id=target_thread,
                photo=InputFile(image_file, filename=WELCOME_IMAGE.name),
                caption=welcome_caption(members),
                parse_mode=ParseMode.HTML,
            )
        logger.info(
            "Boas-vindas enviadas com sucesso para %s no chat %s (thread_id: %s)",
            ", ".join(m.full_name for m in members),
            chat_id,
            target_thread,
        )
        return True
    except Exception as exc:
        logger.warning(
            "Falha ao enviar com message_thread_id=%s: %s. Tentando sem thread_id...",
            target_thread,
            exc,
        )
        try:
            with WELCOME_IMAGE.open("rb") as image_file:
                await bot.send_photo(
                    chat_id=chat_id,
                    photo=InputFile(image_file, filename=WELCOME_IMAGE.name),
                    caption=welcome_caption(members),
                    parse_mode=ParseMode.HTML,
                )
            logger.info(
                "Boas-vindas enviadas (sem tópico) para %s no chat %s",
                ", ".join(m.full_name for m in members),
                chat_id,
            )
            return True
        except Exception as exc2:
            logger.error("Falha ao enviar boas-vindas sem tópico no chat %s: %s", chat_id, exc2)
            return False


def extract_status_change(chat_member_update: ChatMemberUpdated) -> tuple[bool, bool] | None:
    """Determina se a alteração de status corresponde a uma entrada no chat."""
    status_change = chat_member_update.difference().get("status")
    old_is_member, new_is_member = chat_member_update.difference().get("is_member", (None, None))

    if status_change is None:
        return None

    old_status, new_status = status_change
    was_member = old_status in [
        ChatMemberStatus.MEMBER,
        ChatMemberStatus.OWNER,
        ChatMemberStatus.ADMINISTRATOR,
    ] or (old_status == ChatMemberStatus.RESTRICTED and old_is_member is True)

    is_member = new_status in [
        ChatMemberStatus.MEMBER,
        ChatMemberStatus.OWNER,
        ChatMemberStatus.ADMINISTRATOR,
    ] or (new_status == ChatMemberStatus.RESTRICTED and new_is_member is True)

    return was_member, is_member


async def welcome_new_members(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Captura novos membros adicionados via mensagem de servico."""
    message = update.effective_message
    if message is None or not message.new_chat_members:
        return

    members = [member for member in message.new_chat_members if not member.is_bot]
    if not members:
        return

    logger.info("Novo membro via mensagem de servico: %s", [m.full_name for m in members])
    await send_welcome_photo(
        context.bot,
        message.chat_id,
        members,
        thread_id=message.message_thread_id or (GENERAL_TOPIC_ID if GENERAL_TOPIC_ID > 0 else None),
    )


async def welcome_chat_member(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Captura novos membros que entraram via link de convite ou aprovacao."""
    chat_member = update.chat_member
    if chat_member is None:
        return

    result = extract_status_change(chat_member)
    if result is None:
        return

    was_member, is_member = result
    user = chat_member.new_chat_member.user

    if user.is_bot:
        return

    logger.info(
        "Atualizacao de membro em %s: %s (era_membro=%s, e_membro=%s)",
        chat_member.chat.title or chat_member.chat.id,
        user.full_name,
        was_member,
        is_member,
    )

    if not was_member and is_member:
        logger.info("Usuario %s entrou no grupo (ChatMemberUpdated)!", user.full_name)
        await send_welcome_photo(
            context.bot,
            chat_member.chat.id,
            [user],
            thread_id=GENERAL_TOPIC_ID if GENERAL_TOPIC_ID > 0 else None,
        )


async def cmd_teste(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Comando /teste ou /id para verificar IDs do chat/topico e permissao do bot."""
    message = update.effective_message
    user = update.effective_user
    chat = update.effective_chat
    if not message or not user or not chat:
        return

    thread_id = message.message_thread_id
    logger.info(
        "Comando de teste acionado por %s no chat '%s' (ID: %s, thread_id: %s)",
        user.full_name,
        chat.title or chat.id,
        chat.id,
        thread_id,
    )

    info_text = (
        f"🤖 <b>Diagnóstico do Bot X86 Team</b>\n\n"
        f"• <b>Chat:</b> {html.escape(chat.title or 'Privado')}\n"
        f"• <b>Chat ID:</b> <code>{chat.id}</code>\n"
        f"• <b>Tipo do Chat:</b> <code>{chat.type}</code>\n"
        f"• <b>Tópico atual detectado:</b> <code>{thread_id or 'Nenhum (chat principal)'}</code>\n"
        f"• <b>Tópico configurado (GENERAL_TOPIC_ID):</b> <code>{GENERAL_TOPIC_ID}</code>\n\n"
        f"<i>Enviando mensagem de boas-vindas teste abaixo...</i>"
    )
    await message.reply_text(info_text, parse_mode=ParseMode.HTML)
    await send_welcome_photo(context.bot, chat.id, [user], thread_id=thread_id)


async def on_my_chat_member(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Loga quando o proprio bot e adicionado ou promovido no grupo."""
    chat = update.effective_chat
    status = update.my_chat_member.new_chat_member.status if update.my_chat_member else None
    logger.info("Status do bot atualizado no chat %s (%s): %s", chat.title if chat else "Desconhecido", chat.id if chat else "-", status)


async def log_all_updates(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Loga todos os updates recebidos para depuracao no Render."""
    chat = update.effective_chat
    user = update.effective_user
    chat_info = f"{chat.title} ({chat.id})" if chat and chat.title else (str(chat.id) if chat else "N/A")
    user_info = f"{user.full_name} (@{user.username})" if user and user.username else (user.full_name if user else "N/A")
    update_type = "chat_member" if update.chat_member else ("message" if update.message else type(update).__name__)
    logger.info(">>> Update [%s] | Chat: %s | User: %s", update_type, chat_info, user_info)


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error("Erro ao processar atualizacao %s", update, exc_info=context.error)


def main() -> None:
    if not TOKEN:
        raise RuntimeError("Defina TELEGRAM_BOT_TOKEN no ambiente ou no arquivo .env.")
    if not WELCOME_IMAGE.is_file():
        raise FileNotFoundError(f"Banner nao encontrado: {WELCOME_IMAGE}")

    start_health_server()

    application = Application.builder().token(TOKEN).build()

    # Logger de depuracao para acompanhar updates no Render
    application.add_handler(TypeHandler(Update, log_all_updates), group=-1)

    # Comandos de teste
    application.add_handler(CommandHandler(["teste", "test", "id", "start"], cmd_teste))

    # Boas-vindas quando adicionado manualmente por alguem
    application.add_handler(
        MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, welcome_new_members)
    )

    # Boas-vindas quando entra via link de convite ou aprovacao (ChatMemberUpdated)
    application.add_handler(
        ChatMemberHandler(welcome_chat_member, ChatMemberHandler.CHAT_MEMBER)
    )

    # Notificacao quando o proprio bot for adicionado ou alterado
    application.add_handler(
        ChatMemberHandler(on_my_chat_member, ChatMemberHandler.MY_CHAT_MEMBER)
    )

    application.add_error_handler(error_handler)

    logger.info("Bot de boas-vindas iniciado e pronto para receber membros!")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
