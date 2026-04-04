"""
integrations/telegram/bot.py — Bot Telegram pour le Digital Twin
Le bot suggère des réponses ou répond automatiquement selon le mode.

Prérequis :
  pip install python-telegram-bot
  TELEGRAM_BOT_TOKEN=... dans .env

Modes :
  --mode suggest    → le bot t'envoie des suggestions (mode par défaut)
  --mode auto       → le bot répond automatiquement (utilise avec prudence)
"""

import asyncio
import logging
import os
import sys
from pathlib import Path

try:
    from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
    from telegram.ext import (
        Application,
        CommandHandler,
        MessageHandler,
        CallbackQueryHandler,
        ContextTypes,
        filters,
    )
except ImportError:
    print("❌ python-telegram-bot non installé.")
    print("   pip install python-telegram-bot")
    sys.exit(1)

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "backend"))

from personality_engine import PersonalityEngine
from response_generator import ResponseGenerator
from memory_store import MemoryStore


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────────────────────

BASE_DIR  = Path(__file__).parent.parent.parent
PROF_PATH = BASE_DIR / "data" / "personality_profile" / "profile.json"
DB_PATH   = BASE_DIR / "data" / "memory.db"

TOKEN     = os.getenv("TELEGRAM_BOT_TOKEN", "")
MY_NAME   = os.getenv("MY_NAME", "Motaz")
# ID Telegram de TON compte (pour recevoir les suggestions)
MY_CHAT_ID = int(os.getenv("MY_TELEGRAM_CHAT_ID", "0"))
MODE      = os.getenv("TWIN_MODE", "suggest")   # suggest | auto

engine    = PersonalityEngine(profile_path=PROF_PATH)
generator = ResponseGenerator(engine=engine)
store     = MemoryStore(db_path=str(DB_PATH))

# Cache temporaire des réponses en attente de validation
pending: dict = {}   # {callback_id: {response, alternatives, ...}}


# ─────────────────────────────────────────────────────────────
# Handlers
# ─────────────────────────────────────────────────────────────

async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    profile = engine.get_profile()
    await update.message.reply_text(
        f"🤖 Digital Twin de {MY_NAME} — En ligne !\n"
        f"📊 {profile.total_messages_analyzed} messages appris\n"
        f"Mode : {'Suggestions' if MODE == 'suggest' else '🤖 Automatique'}\n\n"
        f"Commandes :\n"
        f"/suggest <message> — Obtenir une suggestion\n"
        f"/profile — Voir le profil\n"
        f"/stats — Statistiques"
    )


async def cmd_suggest(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Commande manuelle : /suggest <message>"""
    if not ctx.args:
        await update.message.reply_text("Usage : /suggest <message à répondre>")
        return

    incoming = " ".join(ctx.args)
    await _send_suggestion(update, ctx, incoming, chat_id=update.effective_chat.id)


async def cmd_profile(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    profile = engine.get_profile()
    await update.message.reply_text(profile.summary())


async def cmd_stats(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    stats = store.get_stats()
    text = (
        f"📊 Statistiques Digital Twin\n\n"
        f"Messages appris : {stats['messages_analyzed']}\n"
        f"Réponses générées : {stats['responses_generated']}\n"
        f"Réponses utilisées : {stats['responses_used']}\n"
        f"Confiance moyenne : {int(stats['avg_confidence']*100)}%\n"
        f"👍 : {stats['ratings']['good']}  "
        f"👎 : {stats['ratings']['bad']}"
    )
    await update.message.reply_text(text)


async def handle_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Reçoit tous les messages et agit selon le mode."""
    msg = update.message.text
    chat_id = update.effective_chat.id

    if MODE == "auto" and chat_id != MY_CHAT_ID:
        # Mode automatique — répondre directement
        result = generator.suggest(msg)
        if result.get("response"):
            await update.message.reply_text(result["response"])
            store.save_response(
                incoming=msg,
                response=result["response"],
                alternatives=result.get("alternatives", []),
                person_type="close_friend",
                confidence=result.get("confidence", 0.0),
                model=result.get("model", ""),
            )

    elif MODE == "suggest" and MY_CHAT_ID and chat_id != MY_CHAT_ID:
        # Mode suggestion — envoyer la suggestion à TOI
        await _send_suggestion_to_owner(ctx, msg, from_chat=chat_id, from_user=update.effective_user.name)


async def _send_suggestion(update, ctx, incoming: str, chat_id: int, person_type: str = "close_friend"):
    """Envoie une suggestion avec boutons d'action."""
    msg_wait = await update.message.reply_text("⏳ Génération en cours...")

    result = generator.suggest(incoming, person_type=person_type)

    if "error" in result:
        await msg_wait.edit_text(f"❌ Erreur : {result['error']}")
        return

    response_id = store.save_response(
        incoming=incoming,
        response=result["response"],
        alternatives=result.get("alternatives", []),
        person_type=person_type,
        confidence=result.get("confidence", 0.0),
        model=result.get("model", ""),
    )

    key = str(response_id)
    pending[key] = {
        "response": result["response"],
        "alternatives": result.get("alternatives", []),
        "response_id": response_id,
    }

    keyboard = [
        [
            InlineKeyboardButton("✅ Utiliser", callback_data=f"use:{key}"),
            InlineKeyboardButton("🔄 Alternative 1", callback_data=f"alt1:{key}"),
        ],
        [
            InlineKeyboardButton("👍 Bon style", callback_data=f"rate_good:{key}"),
            InlineKeyboardButton("👎 Mauvais style", callback_data=f"rate_bad:{key}"),
        ],
    ]

    text = (
        f"💬 Message reçu :\n_{incoming}_\n\n"
        f"🤖 Réponse suggérée ({int(result['confidence']*100)}% confiance) :\n"
        f"*{result['response']}*"
    )

    await msg_wait.edit_text(
        text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def _send_suggestion_to_owner(ctx, incoming: str, from_chat: int, from_user: str):
    """Envoie une suggestion au propriétaire du bot."""
    if not MY_CHAT_ID:
        return

    result = generator.suggest(incoming)
    if "error" in result or not result.get("response"):
        return

    response_id = store.save_response(
        incoming=incoming,
        response=result["response"],
        alternatives=result.get("alternatives", []),
        person_type="close_friend",
        confidence=result.get("confidence", 0.0),
        model=result.get("model", ""),
    )

    key = str(response_id)
    pending[key] = {
        "response": result["response"],
        "alternatives": result.get("alternatives", []),
        "response_id": response_id,
        "from_chat": from_chat,
    }

    keyboard = [[
        InlineKeyboardButton("✅ Envoyer", callback_data=f"send:{key}:{from_chat}"),
        InlineKeyboardButton("👍", callback_data=f"rate_good:{key}"),
        InlineKeyboardButton("👎", callback_data=f"rate_bad:{key}"),
    ]]

    await ctx.bot.send_message(
        chat_id=MY_CHAT_ID,
        text=(
            f"📨 Nouveau message de @{from_user} :\n_{incoming}_\n\n"
            f"💡 Suggestion ({int(result['confidence']*100)}%) :\n*{result['response']}*"
        ),
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def handle_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Gestion des boutons inline."""
    query = update.callback_query
    await query.answer()
    data = query.data

    if data.startswith("use:"):
        key = data.split(":")[1]
        p = pending.get(key, {})
        if p:
            store.rate_response(p["response_id"], rating=1, used=True)
            await query.edit_message_text(f"✅ Réponse utilisée :\n{p['response']}")
            pending.pop(key, None)

    elif data.startswith("alt1:"):
        key = data.split(":")[1]
        p = pending.get(key, {})
        alts = p.get("alternatives", [])
        if alts:
            await query.edit_message_text(f"🔄 Alternative :\n*{alts[0]}*", parse_mode="Markdown")
        else:
            await query.edit_message_text("❌ Pas d'alternative disponible.")

    elif data.startswith("rate_good:"):
        key = data.split(":")[1]
        p = pending.get(key, {})
        if p:
            store.rate_response(p["response_id"], rating=1)
            await query.answer("👍 Merci pour le feedback !")

    elif data.startswith("rate_bad:"):
        key = data.split(":")[1]
        p = pending.get(key, {})
        if p:
            store.rate_response(p["response_id"], rating=-1)
            await query.answer("👎 Noté — le profil s'améliorera !")

    elif data.startswith("send:"):
        parts = data.split(":")
        key = parts[1]
        target_chat = int(parts[2])
        p = pending.get(key, {})
        if p:
            await ctx.bot.send_message(chat_id=target_chat, text=p["response"])
            store.rate_response(p["response_id"], rating=1, used=True)
            await query.edit_message_text(f"✅ Envoyé !")
            pending.pop(key, None)


# ─────────────────────────────────────────────────────────────
# Lancement
# ─────────────────────────────────────────────────────────────

def main():
    if not TOKEN:
        print("❌ TELEGRAM_BOT_TOKEN non configuré dans .env")
        sys.exit(1)

    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("suggest", cmd_suggest))
    app.add_handler(CommandHandler("profile", cmd_profile))
    app.add_handler(CommandHandler("stats", cmd_stats))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(CallbackQueryHandler(handle_callback))

    print(f"🤖 Bot Telegram démarré — Mode : {MODE}")
    print(f"👤 Twin de : {MY_NAME}")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
