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

def sanitize(text):
    return text.replace("*", "").replace("_", "").replace("`", "").replace("[", "").replace("]", "")

def wp_create_post(title, content, status="publish"):
    url = f"{WP_URL}/wp-json/wp/v2/posts"
    auth = (WP_USER, WP_APP_PASSWORD)
    data = {"title": title, "content": content, "status": status}
    response = requests.post(url, json=data, auth=auth)
    response.raise_for_status()
    return response.json()

def wp_update_page(page_id, content):
    url = f"{WP_URL}/wp-json/wp/v2/pages/{page_id}"
    auth = (WP_USER, WP_APP_PASSWORD)
    data = {"content": content}
    response = requests.post(url, json=data, auth=auth)
    response.raise_for_status()
    return response.json()

def wp_list_pages():
    url = f"{WP_URL}/wp-json/wp/v2/pages?per_page=20"
    auth = (WP_USER, WP_APP_PASSWORD)
    response = requests.get(url, auth=auth)
    response.raise_for_status()
    pages = response.json()
    return [(p["id"], p["title"]["rendered"]) for p in pages]

def parse_and_execute(text):
    import json
    logger.info(f"parse_and_execute ricevuto: {text[:200]}")
    try:
        start = text.find("{")
        end = text.rfind("}") + 1
        if start == -1:
            logger.info("Nessun JSON trovato nel testo")
            return None, text

        json_str = text[start:end]
        logger.info(f"JSON estratto: {json_str[:200]}")
        action = json.loads(json_str)
        logger.info(f"Action parsata: {action.get('action')}")

        # Normalizza varianti dell'action
        action_name = action.get("action", "").replace("createpost", "create_post").replace("updatepage", "update_page").replace("listpages", "list_pages").replace("list_page", "list_pages")
        logger.info(f"Action normalizzata: {action_name}")

        if action_name == "create_post":
            result = wp_create_post(action["title"], action["content"], action.get("status", "publish"))
            link = result.get("link", "")
            status = "pubblicato" if action.get("status", "publish") == "publish" else "salvato come bozza"
            return True, f"Articolo '{action['title']}' {status} con successo!\n{link}"

        elif action_name == "update_page":
            wp_update_page(action["page_id"], action["content"])
            return True, "Pagina aggiornata con successo!"

        elif action_name == "list_pages":
            pages = wp_list_pages()
            lines = [f"- ID {pid}: {title}" for pid, title in pages]
            return True, "Pagine disponibili:\n" + "\n".join(lines)

        else:
            logger.warning(f"Action non riconosciuta: {action_name}")
            return None, text

    except json.JSONDecodeError as e:
        logger.error(f"JSONDecodeError: {e}")
        return None, text
    except Exception as e:
        logger.error(f"Errore parse_and_execute: {e}")
        return False, f"Errore durante l'esecuzione: {str(e)}"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if ALLOWED_USER_ID and user_id != ALLOWED_USER_ID:
        await update.message.reply_text("Non sei autorizzato ad usare questo bot.")
        return
    conversation_history[user_id] = []
    await update.message.reply_text(
        "Ciao! Sono il tuo assistente per il sito dello Studio Crisciani.\n\n"
        "Puoi chiedermi di:\n"
        "- Scrivere e pubblicare articoli del blog\n"
        "- Aggiornare il contenuto delle pagine\n"
        "- Mostrare le pagine disponibili\n\n"
        "Come posso aiutarti?"
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if ALLOWED_USER_ID and user_id != ALLOWED_USER_ID:
        await update.message.reply_text("Non sei autorizzato.")
        return

    user_text = update.message.text

    if user_id not in conversation_history:
        conversation_history[user_id] = []

    conversation_history[user_id].append({"role": "user", "content": user_text})

    if len(conversation_history[user_id]) > 20:
        conversation_history[user_id] = conversation_history[user_id][-20:]

    await update.message.reply_text("Sto elaborando...")

    try:
        response = client.messages.create(
            model="claude-opus-4-5",
            max_tokens=2000,
            system=SYSTEM_PROMPT,
            messages=conversation_history[user_id],
        )

        ai_text = response.content[0].text
        logger.info(f"Risposta AI: {ai_text[:300]}")
        conversation_history[user_id].append({"role": "assistant", "content": ai_text})

        executed, reply = parse_and_execute(ai_text)
        reply = sanitize(reply)

        MAX_LENGTH = 4000
        if len(reply) <= MAX_LENGTH:
            await update.message.reply_text(reply)
        else:
            chunks = [reply[i:i+MAX_LENGTH] for i in range(0, len(reply), MAX_LENGTH)]
            for chunk in chunks:
                await update.message.reply_text(chunk)

    except Exception as e:
        logger.error(f"Errore handle_message: {e}")
        await update.message.reply_text(f"Errore: {str(e)}")

async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    conversation_history[user_id] = []
    await update.message.reply_text("Conversazione resettata.")

if __name__ == "__main__":
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("reset", reset))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    logger.info("Bot avviato!")
    app.run_polling()
