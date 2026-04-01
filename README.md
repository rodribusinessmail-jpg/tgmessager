# Telegram Scheduler Bot – Railway Deploy

## Lokaler Test

```bash
pip install -r requirements.txt
python bot.py
```

## Railway Deploy

1. GitHub Repo erstellen → Dateien hochladen
2. Railway → New Project → Deploy from GitHub
3. Environment Variables setzen (aus railway_env.txt)
4. Deploy!

## Erster Login nach Deploy

Im Bot schreiben:
```
/login
```
Code eingeben → fertig!

## Bot Befehle

| Befehl | Beschreibung |
|--------|-------------|
| /start | Übersicht |
| /login | Mit Telegram verbinden |
| /add | Neue Nachricht planen |
| /list | Nachrichten verwalten |
| /chats | Chats neu laden |
| /status | Verbindungsstatus |
| /help | Hilfe |

## Nachricht planen – Ablauf

1. `/add` senden
2. Name eingeben
3. Nachrichtentext eingeben
4. Uhrzeit eingeben (HH:MM)
5. Wochentage auswählen
6. Chats auswählen
7. Bestätigen → fertig!
