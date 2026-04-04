# 🚀 Guide de Déploiement — Digital Twin AI

Ce guide te permet de déployer ton Digital Twin sur internet en **30 minutes**, gratuitement.

---

## Architecture de déploiement

```
[Ta machine locale]          [Cloud]
                             
WhatsApp Bridge (port 3001)  →  Backend FastAPI  ←→  Supabase (DB)
     ↑                              ↑
     |                         Render.com
     |                              ↑
     └── Frontend React  ←─────────┘
          (Vercel)
```

> ⚠️ Le **bridge WhatsApp tourne toujours localement** (ta machine).  
> Il ne peut pas être déployé sur un serveur sans accès WhatsApp Web.

---

## Étape 1 — Supabase (Base de données)

1. Va sur [supabase.com](https://supabase.com) → **New project**
2. Choisis une région EU (Frankfurt ou Paris)
3. Note le **mot de passe DB** quelque part
4. Une fois créé : **Settings → API**
   - Copie **Project URL** → `SUPABASE_URL`
   - Copie **anon public** key → `SUPABASE_KEY`
5. Va dans **SQL Editor** → colle le contenu de `backend/supabase_schema.sql` → **Run**

✅ La base est prête.

---

## Étape 2 — Backend sur Render.com

1. Push ton projet sur GitHub (si pas déjà fait) :
   ```bash
   git init
   git add .
   git commit -m "Digital Twin AI initial commit"
   git remote add origin https://github.com/TON_USERNAME/digital-twin-ai.git
   git push -u origin main
   ```

2. Va sur [render.com](https://render.com) → **New → Blueprint**
3. Connecte ton repo GitHub → Render détecte `render.yaml` automatiquement
4. Dans les **Environment Variables**, remplis :
   | Variable | Valeur |
   |----------|--------|
   | `GROQ_API_KEY` | Ta clé Groq (console.groq.com) |
   | `SUPABASE_URL` | Depuis Étape 1 |
   | `SUPABASE_KEY` | Depuis Étape 1 |
   | `ALLOWED_ORIGINS` | `https://TON-PROJET.vercel.app` |
   | `MY_NAME` | Ton prénom |

5. Clique **Apply** → Render build et démarre le backend
6. Note l'URL de ton service : `https://digital-twin-backend.onrender.com`

✅ Backend en ligne.

---

## Étape 3 — Frontend sur Vercel

1. Va sur [vercel.com](https://vercel.com) → **New Project**
2. Importe ton repo GitHub
3. **Root Directory** : `frontend`
4. **Framework** : Vite
5. Dans **Environment Variables**, ajoute :
   | Variable | Valeur |
   |----------|--------|
   | `VITE_API_URL` | `https://digital-twin-backend.onrender.com` |
   | `VITE_WA_BRIDGE_URL` | `http://localhost:3001` |

6. Clique **Deploy**
7. Note ton URL : `https://TON-PROJET.vercel.app`

8. **Important** : retourne sur Render et mets à jour `ALLOWED_ORIGINS` avec cette URL Vercel.

✅ Frontend en ligne.

---

## Étape 4 — WhatsApp Bridge (en local)

Le bridge tourne sur ta machine et fait le lien entre WhatsApp et le backend cloud.

```bash
cd whatsapp-bridge
cp ../.env.example .env

# Dans .env, configure :
# TWIN_API_URL=https://digital-twin-backend.onrender.com
# WA_BRIDGE_PORT=3001
# WA_AUTO_REPLY=false   ← laisse false au début !

npm install
npm start
```

Ouvre ton frontend Vercel → onglet 📱 WhatsApp → scanne le QR code.

✅ WhatsApp connecté.

---

## Étape 5 — Premier import de conversations

1. Exporte tes conversations WhatsApp :
   - WhatsApp → Discussion → ⋮ → Exporter → Sans médias → `.txt`
2. Va sur ton frontend Vercel → onglet 📥 Importer
3. Glisse le fichier `.txt` dans la zone
4. Recommence avec d'autres conversations (Telegram, Instagram)
5. Importe **200+ de tes messages** pour un bon profil

✅ Profil d'apprentissage construit.

---

## Test rapide

```bash
# Santé du backend
curl https://digital-twin-backend.onrender.com/health

# Test de suggestion
curl -X POST https://digital-twin-backend.onrender.com/suggest \
  -H "Content-Type: application/json" \
  -d '{"message": "Ça va ?", "person_type": "close_friend"}'
```

---

## Résolution de problèmes

| Problème | Solution |
|----------|----------|
| CORS error dans le navigateur | Vérifie `ALLOWED_ORIGINS` dans Render |
| 428 sur /suggest | Importe des conversations d'abord |
| 503 GROQ_API_KEY | Vérifie la variable dans Render Dashboard |
| Bridge WhatsApp offline | Relance `npm start` en local |
| Render s'endort (free tier) | Ping régulier avec UptimeRobot (gratuit) |

---

## Variables d'environnement complètes

| Variable | Où | Description |
|----------|----|-------------|
| `MY_NAME` | Render | Ton prénom |
| `GROQ_API_KEY` | Render | Clé API Groq |
| `SUPABASE_URL` | Render | URL Supabase |
| `SUPABASE_KEY` | Render | Clé anon Supabase |
| `ALLOWED_ORIGINS` | Render | URL Vercel frontend |
| `VITE_API_URL` | Vercel | URL backend Render |
| `VITE_WA_BRIDGE_URL` | Vercel | `http://localhost:3001` |
| `TWIN_API_URL` | .env local | URL backend (pour le bridge) |
| `WA_AUTO_REPLY` | .env local | `false` (ou `true` si tu veux l'auto-reply) |

---

*Digital Twin AI — Motaz Sammoud, 2024*
