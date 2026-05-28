# Agente Blog - Studio Crisciani

Bot Telegram che gestisce il sito WordPress tramite AI.

## Setup su Railway

1. Crea un account su https://railway.app
2. Crea un nuovo progetto → "Deploy from GitHub repo"
   (oppure usa "Empty project" e carica i file manualmente)
3. Vai su "Variables" e aggiungi queste variabili d'ambiente:

```
TELEGRAM_TOKEN=...
ANTHROPIC_API_KEY=...
WP_URL=https://www.studiocrisciani.com
WP_USER=scrisciani
WP_APP_PASSWORD=PwMX SI32 FOLz k4Hi 8KsH uLBO
ALLOWED_USER_ID=...  ← il tuo ID Telegram (vedi sotto)
```

## Come trovare il tuo ID Telegram

1. Apri Telegram e cerca @userinfobot
2. Scrivi /start
3. Ti risponderà con il tuo ID numerico

## Comandi del bot

- `/start` — avvia il bot
- `/reset` — azzera la conversazione

## Esempi di utilizzo

- "Scrivi un articolo sull'importanza dello spazzolino elettrico"
- "Crea una bozza di post sui benefici dell'igiene professionale"
- "Mostrami le pagine disponibili"
- "Aggiorna la pagina 42 con questo testo: ..."
