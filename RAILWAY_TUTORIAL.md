# Railway Deploy Tutorial

## Schritt 1 - GitHub Account
Gehe zu github.com und erstelle einen kostenlosen Account falls noch nicht vorhanden.

## Schritt 2 - Neues Repository erstellen
1. Auf github.com oben rechts auf "+" klicken
2. "New repository" waehlen
3. Name eingeben z.B. "tg-scheduler"
4. "Private" auswaehlen (wichtig!)
5. "Create repository" klicken

## Schritt 3 - Dateien hochladen
1. Auf der Repository-Seite "uploading an existing file" klicken
2. Diese Dateien hochladen:
   - bot.py
   - requirements.txt
   - Procfile
3. "Commit changes" klicken

## Schritt 4 - Railway Account
1. Gehe zu railway.app
2. "Login" klicken
3. "Login with GitHub" waehlen und bestaetigen

## Schritt 5 - Neues Projekt erstellen
1. Im Railway Dashboard auf "New Project" klicken
2. "Deploy from GitHub repo" waehlen
3. Dein Repository "tg-scheduler" auswaehlen
4. "Deploy Now" klicken

## Schritt 6 - Environment Variables setzen
1. Im Railway Projekt auf deinen Service klicken
2. Oben auf "Variables" klicken
3. Diese Variables einzeln hinzufuegen mit "New Variable":

   BOT_TOKEN = 8645520966:AAHVUX-9a4JdrlEEazv7YpaMjBOFFjlanoA
   API_ID = 39929121
   API_HASH = 7d9ef1b6c49bd9ec169aa513b2291be9
   PHONE = +13677527185
   OWNER_ID = 6717617647

4. Nach jeder Variable "Add" klicken

## Schritt 7 - Deploy
1. Railway deployed automatisch nach dem Setzen der Variables
2. Auf "Deployments" klicken um den Status zu sehen
3. Wenn gruener Haken erscheint ist der Bot live

## Schritt 8 - Ersten Login machen
1. Telegram oeffnen
2. Deinen Bot suchen
3. /login schreiben
4. QR-Code scannen
5. 2FA Passwort eingeben
6. Fertig - Bot laeuft 24/7!

## Wichtig - Session persistent machen
Nach dem ersten Login wird die Session nur im Railway Container gespeichert.
Damit sie bei Neustarts erhalten bleibt, Volume hinzufuegen:

1. Im Railway Service auf "Volumes" klicken
2. "New Volume" klicken
3. Mount Path: /app
4. Speichern

Dann in den Variables noch hinzufuegen:
SESSION_FILE = /app/user_session

## Troubleshooting
- Bot antwortet nicht: Logs in Railway unter "Deployments" checken
- Session verloren: /login nochmal ausfuehren
- Nachrichten werden nicht gesendet: /status checken ob verbunden
