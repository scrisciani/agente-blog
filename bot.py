import os
import logging
import requests
import anthropic
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

# --- Configurazione ---
TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
WP_URL = os.environ["WP_URL"]
WP_USER = os.environ["WP_USER"]
WP_APP_PASSWORD = os.environ["WP_APP_PASSWORD"]
ALLOWED_USER_ID = int(os.environ.get("ALLOWED_USER_ID", "0"))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

# --- Stato conversazione per utente ---
conversation_history = {}

SYSTEM_PROMPT = """Sei un assistente per la gestione del sito web dello Studio Odontoiatrico Crisciani.
Puoi eseguire queste azioni sul sito WordPress:
- Scrivere e pubblicare articoli del blog
- Aggiornare il contenuto delle pagine esistenti

Quando l'utente ti chiede di creare un articolo, genera un contenuto professionale e appropriato per uno studio dentistico.
Usa un tono professionale ma accessibile ai pazienti.

Quando devi eseguire un'azione, rispondi SEMPRE con un JSON nel seguente formato (e nient'altro):

Per creare un articolo:
{"action": "create_post", "title": "Titolo articolo", "content": "Contenuto HTML dell'articolo", "status": "publish"}

Per creare una bozza (non pubblicare subito):
{"action": "create_post", "title": "Titolo articolo", "content": "Contenuto HTML dell'articolo", "status": "draft"}

Per aggiornare una pagina esistente:
{"action": "update_page", "page_id": 123, "content": "Nuovo contenuto HTML"}

Se l'utente vuole solo parlare o fare domande senza eseguire azioni, rispondi normalmente in testo.
Se l'utente vuole vedere le pagine disponibili, rispondi con:
{"action": "list_pages"}
"""

def wp_create_post(title, content, status="publish"):
    """Crea un nuovo post su WordPress."""
    url = f"{WP_URL}/wp-json/wp/v2/posts"
    auth = (WP_USER, WP_APP_PASSWORD)
    data = {
        "title": title,
        "content": content,
        "status": status,
    }
    response = requests.post(url, json=data, auth=auth)
    response.raise_for_status()
    return response.json()

def wp_update_page(page_id, content):
    """Aggiorna il contenuto di una pagina WordPress."""
    url = f"{WP_URL}/wp-json/wp/v2/pages/{page_id}"
    auth = (WP_USER, WP_APP_PASSWORD)
    data = {"content": content}
    response = requests.post(url, json=data, auth=auth)
    response.raise_for_status()
    return response.json()

def wp_list_pages():
    """Lista le pagine disponibili su WordPress."""
    url = f"{WP_URL}/wp-json/wp/v2/pages?per_page=20"
    auth = (WP_USER, WP_APP_PASSWORD)
    response = requests.get(url, auth=auth)
    response.raise_for_status()
    pages = response.json()
    return [(p["id"], p["title"]["rendered"]) for p in pages]

def parse_and_execute(text):
    """Prova a interpretare la risposta dell'AI come un'azione WordPress."""
    import json
    try:
        # Cerca JSON nella risposta
        start = text.find("{")
        end = text.rfind("}") + 1
        if start == -1:
            return None, text

        json_str = text[start:end]
        action = json.loads(json_str)

        if action["action"] == "create_post":
            result = wp_create_post(action["title"], action["content"], action.get("status", "publish"))
            link = result.get("link", "")
            status = "pubblicato" if action.get("status") == "publish" else "salvato come bozza"
            return True, f"✅ Articolo *{action['title']}* {status} con successo!\n🔗 {link}"

        elif action["action"] == "update_page":
            wp_update_page(action["page_id"], action["content"])
            return True, f"✅ Pagina aggiornata con successo!"

        elif action["action"] == "list_pages":
            pages = wp_list_pages()
            lines = [f"• `{pid}` — {title}" for pid, title in pages]
            return True, "📄 *Pagine disponibili:*\n" + "\n".join(lines)

    except json.JSONDecodeError:
        pass
    except Exception as e:
        return False, f"❌ Errore durante l'esecuzione: {str(e)}"

    return None, text

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if ALLOWED_USER_ID and user_id != ALLOWED_USER_ID:
        await update.message.reply_text("⛔ Non sei autorizzato ad usare questo bot.")
        return
    conversation_history[user_id] = []
    await update.message.reply_text(
        "👋 Ciao! Sono il tuo assistente per il sito dello Studio Crisciani.\n\n"
        "Puoi chiedermi di:\n"
        "• Scrivere e pubblicare articoli del blog\n"
        "• Aggiornare il contenuto delle pagine\n"
        "• Mostrare le pagine disponibili\n\n"
        "Come posso aiutarti?"
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if ALLOWED_USER_ID and user_id != ALLOWED_USER_ID:
        await update.message.reply_text("⛔ Non sei autorizzato.")
        return

    user_text = update.message.text

    if user_id not in conversation_history:
        conversation_history[user_id] = []

    conversation_history[user_id].append({"role": "user", "content": user_text})

    # Limita la storia a 20 messaggi
    if len(conversation_history[user_id]) > 20:
        conversation_history[user_id] = conversation_history[user_id][-20:]

    await update.message.reply_text("⏳ Sto elaborando...")

    try:
        response = client.messages.create(
            model="claude-opus-4-5",
            max_tokens=2000,
            system=SYSTEM_PROMPT,
            messages=conversation_history[user_id],
        )

        ai_text = response.content[0].text
        conversation_history[user_id].append({"role": "assistant", "content": ai_text})

        executed, reply = parse_and_execute(ai_text)

        await update.message.reply_text(reply, parse_mode="Markdown")

    except Exception as e:
        logger.error(f"Errore: {e}")
        await update.message.reply_text(f"❌ Errore: {str(e)}")

async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    conversation_history[user_id] = []
    await update.message.reply_text("🔄 Conversazione resettata.")

if __name__ == "__main__":
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("reset", reset))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    logger.info("Bot avviato!")
    app.run_polling()
