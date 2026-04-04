# 🤖 Digital Twin AI

Un agent IA qui apprend ta personnalité exacte à travers tes vraies conversations et peut communiquer à ta place — de façon transparente avec ton entourage.

---

## Vue d'ensemble

Digital Twin AI analyse tes exports de conversations (WhatsApp, Telegram, Instagram) pour apprendre ton style unique : ton vocabulaire, tes emojis préférés, ta façon de répondre selon le contexte, la longueur de tes messages, et bien plus. Il génère ensuite des réponses qui te ressemblent via l'API Claude.

**Toutes les données restent en local sur ta machine.**

---

## Architecture

```
digital-twin-ai/
├── backend/
│   ├── main.py                 ← API FastAPI (endpoints REST)
│   ├── personality_engine.py   ← Moteur d'apprentissage du profil
│   ├── conversation_analyzer.py← Parseur WhatsApp/Telegram/Instagram
│   ├── response_generator.py   ← Génération de réponses via Claude
│   └── memory_store.py         ← Mémoire long terme (SQLite)
├── training/
│   ├── import_conversations.py ← Import en batch
│   ├── extract_personality.py  ← Analyse avancée de personnalité
│   └── fine_tune.py            ← Entraînement continu (watch mode)
├── integrations/
│   ├── telegram/bot.py         ← Bot Telegram avec suggestions
│   ├── whatsapp/webhook.py     ← Webhook WhatsApp Business API
│   └── instagram/dm_handler.py ← DMs Instagram Graph API
├── data/
│   ├── raw_conversations/      ← Dépose tes exports ici
│   ├── processed/              ← Conversations traitées
│   └── personality_profile/    ← profile.json (ton profil IA)
└── frontend/app/               ← Interface web (à venir)
```

---

## Installation

### 1. Prérequis

- Python 3.10+
- Une clé API Anthropic ([console.anthropic.com](https://console.anthropic.com))

### 2. Installation des dépendances

```bash
cd digital-twin-ai
pip install -r requirements.txt
```

### 3. Configuration

```bash
cp .env.example .env
# Édite .env et remplis :
# MY_NAME=TonNom (exactement comme dans tes exports)
# ANTHROPIC_API_KEY=sk-ant-...
```

---

## Utilisation

### Étape 1 — Exporter tes conversations

**WhatsApp :**
1. Ouvre une conversation → ⋮ Menu → Plus → Exporter la discussion
2. Choisis "Sans médias"
3. Envoie-toi le fichier `.txt` et place-le dans `data/raw_conversations/`

**Telegram :**
1. Paramètres → Avancés → Exporter les données Telegram
2. Sélectionne "Messages" au format JSON
3. Place `result.json` dans `data/raw_conversations/`

**Instagram :**
1. Paramètres → Sécurité → Données et accès → Télécharger tes données
2. Sélectionne "Messages" en format JSON
3. Place les fichiers `message_1.json` dans `data/raw_conversations/`

### Étape 2 — Importer et analyser

```bash
# Analyser tous les fichiers dans raw_conversations/
python training/import_conversations.py

# Analyser un fichier spécifique
python training/import_conversations.py --file data/raw_conversations/chat.txt

# Voir ton profil extrait
python training/extract_personality.py
```

### Étape 3 — Lancer l'API

```bash
cd backend
python main.py
# → http://localhost:8000
# → Documentation : http://localhost:8000/docs
```

### Étape 4 — Tester une réponse

```bash
curl -X POST http://localhost:8000/suggest \
  -H "Content-Type: application/json" \
  -d '{"message": "Ça va ? T es dispo ce soir ?", "person_type": "close_friend"}'
```

---

## Endpoints API

| Méthode | Endpoint | Description |
|---------|----------|-------------|
| `POST` | `/import` | Importer un fichier de conversation |
| `GET` | `/personality` | Voir le profil complet |
| `GET` | `/personality/summary` | Résumé lisible du profil |
| `GET` | `/personality/prompt-preview` | Voir le prompt Claude généré |
| `POST` | `/suggest` | Obtenir une réponse dans ton style |
| `POST` | `/feedback` | Évaluer une réponse générée |
| `POST` | `/train` | Réentraîner le profil |
| `GET` | `/stats` | Statistiques d'apprentissage |
| `GET` | `/contacts` | Liste des contacts |
| `POST` | `/contacts` | Ajouter/modifier un contact |
| `GET` | `/history` | Historique des réponses générées |

### Exemple de requête /suggest

```json
{
  "message": "Wsh t'es libre demain soir ?",
  "person_type": "close_friend",
  "context_note": "C'est un ami proche, on est décontractés",
  "history": []
}
```

**Types d'interlocuteurs (`person_type`) :**
- `close_friend` — ami proche
- `family` — famille
- `colleague` — collègue
- `client` — client/professionnel
- `unknown` — inconnu

---

## Intégration Telegram

```bash
# Configure dans .env :
# TELEGRAM_BOT_TOKEN=...
# MY_TELEGRAM_CHAT_ID=... (ton ID pour recevoir les suggestions)
# TWIN_MODE=suggest

python integrations/telegram/bot.py
```

**Commandes du bot :**
- `/suggest <message>` — Obtenir une suggestion
- `/profile` — Voir ton profil IA
- `/stats` — Statistiques

---

## Entraînement continu

```bash
# Lancer la surveillance automatique
# (détecte les nouveaux fichiers dans raw_conversations/)
python training/fine_tune.py --watch --interval 300

# Un seul passage
python training/fine_tune.py

# Générer un rapport d'entraînement
python training/fine_tune.py --report rapport.json
```

---

## Qualité du profil

| Messages analysés | Niveau | Fidélité |
|:-----------------:|--------|----------|
| < 10 | Insuffisant | 20% |
| 10 – 50 | Débutant | 40% |
| 50 – 200 | Bon | 60% |
| 200 – 500 | Excellent | 80% |
| 500+ | Expert | 95% |

Plus tu importe de conversations, plus le twin te ressemble.

---

## Roadmap

### Phase 1 — MVP (actuel ✅)
- [x] Parseur WhatsApp, Telegram, Instagram
- [x] Profil de personnalité (vocabulaire, emojis, ton, style)
- [x] Génération de réponses via Claude API
- [x] API FastAPI complète
- [x] Bot Telegram avec suggestions
- [x] Webhook WhatsApp Business
- [x] Mémoire long terme SQLite
- [x] Entraînement continu

### Phase 2 — Amélioration du style
- [ ] RAG sémantique (embeddings) pour chercher des exemples similaires
- [ ] Apprentissage par feedback (les réponses notées 👍 renforcent le profil)
- [ ] Détection automatique du type d'interlocuteur
- [ ] Multi-langue (français/anglais/darija)

### Phase 3 — Interface
- [ ] Dashboard web React (voir les suggestions, valider, noter)
- [ ] Extension Chrome pour suggestions en temps réel
- [ ] Application mobile Flutter

### Phase 4 — Intégrations avancées
- [ ] Migration PostgreSQL pour multi-utilisateurs
- [ ] Synchronisation en temps réel via WebSocket
- [ ] API WhatsApp Business complète (envoi automatique validé)
- [ ] Intégration Signal (via signal-cli)

---

## Sécurité & Vie privée

- Toutes les données restent **localement** sur ta machine
- Les conversations ne sont jamais envoyées à des serveurs tiers (sauf Claude API pour générer des réponses)
- Le profil est stocké en JSON chiffrable
- Mode `suggest` recommandé : tu valides chaque réponse avant envoi

---

## Stack technique

- **LLM** : Claude Sonnet (claude-sonnet-4-6) via Anthropic API
- **Backend** : Python + FastAPI + Uvicorn
- **Base de données** : SQLite (→ PostgreSQL en production)
- **Bot Telegram** : python-telegram-bot
- **WhatsApp** : Meta Cloud API (Graph API v18)
- **Instagram** : Meta Messenger API for Instagram

---

*Projet personnel — toutes les données restent locales.*
