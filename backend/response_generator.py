"""
response_generator.py — Digital Twin AI — version améliorée
══════════════════════════════════════════════════════════════
Améliorations v2 :
  1. Modèle 70B au lieu de 8B (llama-3.3-70b-versatile)
  2. RAG : exemples réels tirés de Supabase
  3. Contexte par contact : style spécifique à chaque personne
  4. Prompt engineering avancé avec few-shot examples
  5. Score de qualité avec validation du style
"""

import os
import re
from collections import Counter
from typing import List, Optional

from openai import OpenAI

from personality_engine import PersonalityEngine, PersonalityProfile


# ─────────────────────────────────────────────────────────────
# Constantes
# ─────────────────────────────────────────────────────────────

# 70B = 9× plus puissant que 8B, toujours gratuit sur Groq
DEFAULT_MODEL       = "llama-3.3-70b-versatile"
FALLBACK_MODEL      = "llama-3.1-70b-versatile"   # fallback si quota atteint
DEFAULT_MAX_TOKENS  = 512   # réponses courtes = plus naturelles
DEFAULT_TEMPERATURE = 0.75  # équilibre précision/créativité


# ─────────────────────────────────────────────────────────────
# ResponseGenerator
# ─────────────────────────────────────────────────────────────

class ResponseGenerator:
    """
    Génère des réponses imitant exactement le style de l'utilisateur.

    Pipeline :
    1. Fetch RAG examples depuis Supabase (échanges similaires réels)
    2. Build contact-specific context
    3. Build dynamic system prompt avec few-shot examples
    4. Appel Groq 70B
    5. Validation du style (longueur, emojis)
    """

    def __init__(
        self,
        engine: Optional[PersonalityEngine] = None,
        api_key: Optional[str] = None,
        model: str = DEFAULT_MODEL,
    ):
        self.engine = engine or PersonalityEngine()
        self.client = OpenAI(
            api_key=api_key or os.environ.get("GROQ_API_KEY", ""),
            base_url="https://api.groq.com/openai/v1",
        )
        self.model = model
        self._supabase = self._init_supabase()

    def _init_supabase(self):
        """Initialise le client Supabase pour le RAG."""
        url = os.environ.get("SUPABASE_URL", "")
        key = os.environ.get("SUPABASE_SERVICE_KEY") or os.environ.get("SUPABASE_KEY", "")
        if url and key:
            try:
                from supabase import create_client
                client = create_client(url, key)
                print("✅ ResponseGenerator : Supabase RAG activé")
                return client
            except Exception as e:
                print(f"⚠️  Supabase RAG non disponible : {e}")
        return None

    # ─────────────────────────────────────────────────────────
    # API principale
    # ─────────────────────────────────────────────────────────

    def suggest(
        self,
        incoming_message: str,
        conversation_history: Optional[List[dict]] = None,
        person_type: str = "close_friend",
        context_note: str = "",
        contact_id: str = "",
        contact_name: str = "",
    ) -> dict:
        """
        Génère une réponse dans le style exact de l'utilisateur.

        Paramètres :
          incoming_message     : le message reçu
          conversation_history : [{role, content}, ...] — derniers échanges
          person_type          : close_friend | family | colleague | client | unknown
          context_note         : note contextuelle libre
          contact_id           : chat_id WhatsApp pour RAG ciblé
          contact_name         : nom du contact pour contexte personnalisé
        """
        profile = self.engine.get_profile()
        ctx = self.engine.build_system_prompt_context()

        # ── 1. RAG : exemples réels similaires depuis Supabase ──
        rag_examples = self._fetch_rag_examples(
            incoming_message,
            contact_id=contact_id,
            limit=5
        )

        # ── 2. Contexte spécifique au contact ─────────────────
        contact_ctx = self._fetch_contact_context(contact_id, contact_name)

        # ── 3. System prompt enrichi ──────────────────────────
        system_prompt = self._build_system_prompt(
            ctx, person_type, context_note,
            rag_examples=rag_examples,
            contact_ctx=contact_ctx,
        )

        # ── 4. Messages (historique + message actuel) ─────────
        messages = self._build_messages(incoming_message, conversation_history)
        openai_messages = [{"role": "system", "content": system_prompt}] + messages

        # ── 5. Appel Groq ─────────────────────────────────────
        try:
            resp = self.client.chat.completions.create(
                model=self.model,
                messages=openai_messages,
                max_tokens=DEFAULT_MAX_TOKENS,
                temperature=DEFAULT_TEMPERATURE,
            )
            main_response = resp.choices[0].message.content.strip()

            # Validation : si trop long, tronquer naturellement
            main_response = self._validate_style(main_response, profile)

            # ── 6. Alternatives légèrement différentes ─────────
            alternatives = self._generate_alternatives(
                system_prompt, openai_messages, main_response
            )

            return {
                "response":     main_response,
                "alternatives": alternatives,
                "confidence":   self._estimate_confidence(profile, rag_examples),
                "model":        self.model,
                "person_type":  person_type,
                "rag_examples": len(rag_examples),
                "contact_ctx":  bool(contact_ctx),
            }

        except Exception as e:
            # Fallback sur modèle plus léger si quota Groq atteint
            if "rate" in str(e).lower() or "quota" in str(e).lower():
                try:
                    resp = self.client.chat.completions.create(
                        model="llama-3.1-8b-instant",
                        messages=openai_messages,
                        max_tokens=DEFAULT_MAX_TOKENS,
                        temperature=DEFAULT_TEMPERATURE,
                    )
                    return {
                        "response":     resp.choices[0].message.content.strip(),
                        "alternatives": [],
                        "confidence":   self._estimate_confidence(profile, rag_examples) * 0.7,
                        "model":        "llama-3.1-8b-instant (fallback)",
                        "person_type":  person_type,
                        "rag_examples": len(rag_examples),
                        "contact_ctx":  bool(contact_ctx),
                    }
                except Exception as e2:
                    return {"error": str(e2), "response": "", "alternatives": [], "confidence": 0.0, "model": self.model}
            return {"error": str(e), "response": "", "alternatives": [], "confidence": 0.0, "model": self.model}

    def suggest_simple(self, incoming_message: str, person_type: str = "close_friend") -> str:
        result = self.suggest(incoming_message, person_type=person_type)
        return result.get("response", "")

    # ─────────────────────────────────────────────────────────
    # RAG — Exemples réels depuis Supabase
    # ─────────────────────────────────────────────────────────

    def _fetch_rag_examples(
        self, incoming_msg: str, contact_id: str = "", limit: int = 5
    ) -> list:
        """
        Cherche dans Supabase des échanges réels similaires :
        → messages reçus similaires + la vraie réponse envoyée
        Priorité aux échanges avec ce contact, puis tous contacts.
        """
        if not self._supabase:
            return []

        # Extraire les mots-clés (longueur > 3 pour filtrer les mots vides)
        keywords = [
            w.lower() for w in re.findall(r'[a-zàâäéèêëïîôùûüç]+', incoming_msg.lower())
            if len(w) > 3
        ][:5]

        if not keywords:
            # Fallback : utiliser les premiers mots
            keywords = incoming_msg.lower().split()[:3]

        examples = []
        seen_received = set()

        def search_with_filter(extra_filter=None):
            for kw in keywords:
                if len(examples) >= limit:
                    break
                try:
                    q = (
                        self._supabase.table("whatsapp_messages")
                        .select("message_id, chat_id, body, timestamp")
                        .eq("from_me", False)
                        .ilike("body", f"%{kw}%")
                        .not_.is_("body", "null")
                        .order("timestamp", desc=True)
                        .limit(15)
                    )
                    if extra_filter:
                        q = q.eq("chat_id", extra_filter)

                    received_msgs = q.execute()

                    for msg in (received_msgs.data or []):
                        body = (msg.get("body") or "").strip()
                        if not body or body in seen_received or len(body) < 2:
                            continue
                        seen_received.add(body)

                        # Chercher ma vraie réponse juste après
                        reply_res = (
                            self._supabase.table("whatsapp_messages")
                            .select("body")
                            .eq("chat_id", msg["chat_id"])
                            .eq("from_me", True)
                            .gt("timestamp", msg["timestamp"])
                            .not_.is_("body", "null")
                            .order("timestamp")
                            .limit(1)
                            .execute()
                        )

                        if reply_res.data and reply_res.data[0].get("body", "").strip():
                            examples.append({
                                "received": body[:300],
                                "replied":  reply_res.data[0]["body"].strip()[:300],
                            })

                        if len(examples) >= limit:
                            break

                except Exception as e:
                    print(f"⚠️  RAG search error ({kw}): {e}")
                    break

        # D'abord chercher avec ce contact spécifique
        if contact_id:
            search_with_filter(contact_id)

        # Compléter avec tous les contacts si pas assez d'exemples
        if len(examples) < limit:
            search_with_filter(None)

        return examples[:limit]

    # ─────────────────────────────────────────────────────────
    # Contexte par contact
    # ─────────────────────────────────────────────────────────

    def _fetch_contact_context(self, contact_id: str, contact_name: str) -> dict:
        """
        Construit un profil de communication spécifique à ce contact
        depuis les vrais messages Supabase.
        """
        if not self._supabase or not contact_id:
            return {}
        try:
            msgs_res = (
                self._supabase.table("whatsapp_messages")
                .select("body, from_me")
                .eq("chat_id", contact_id)
                .not_.is_("body", "null")
                .order("timestamp", desc=True)
                .limit(200)
                .execute()
            )
            if not msgs_res.data:
                return {}

            my_msgs   = [m["body"] for m in msgs_res.data if m.get("from_me") and m.get("body")]
            their_msgs = [m["body"] for m in msgs_res.data if not m.get("from_me") and m.get("body")]

            if not my_msgs:
                return {}

            avg_len   = sum(len(m.split()) for m in my_msgs) / len(my_msgs)
            all_words = re.findall(r'\w+', ' '.join(my_msgs).lower())
            freq      = Counter(w for w in all_words if len(w) > 2)
            common    = [w for w, _ in freq.most_common(15)]

            return {
                "name":           contact_name or contact_id.split("@")[0],
                "total_messages": len(my_msgs),
                "avg_length":     round(avg_len, 1),
                "common_words":   common[:10],
                "recent_my_msgs": my_msgs[:4],
            }
        except Exception as e:
            print(f"⚠️  Contact context error: {e}")
            return {}

    # ─────────────────────────────────────────────────────────
    # Construction du system prompt avancé
    # ─────────────────────────────────────────────────────────

    def _build_system_prompt(
        self,
        ctx: dict,
        person_type: str,
        context_note: str,
        rag_examples: list = None,
        contact_ctx: dict = None,
    ) -> str:
        name = ctx["name"]
        rag_examples  = rag_examples or []
        contact_ctx   = contact_ctx or {}

        # Style adapté au type de relation
        if person_type in ("close_friend", "family"):
            style = ctx["close_person_style"]
        elif person_type in ("client", "unknown"):
            style = ctx["formal_style"]
        else:
            style = ctx["close_person_style"]

        # ── Section RAG few-shot examples ─────────────────────
        rag_section = ""
        if rag_examples:
            rag_section = "\n\n══════════ EXEMPLES RÉELS DE TES VRAIS ÉCHANGES ══════════\n"
            rag_section += "Voici comment tu as vraiment répondu dans le passé à des messages similaires.\n"
            rag_section += "Imite ce style EXACTEMENT (même longueur, même ton, mêmes expressions).\n\n"
            for i, ex in enumerate(rag_examples, 1):
                rag_section += f"Exemple {i}:\n"
                rag_section += f"  Reçu   : {ex['received']}\n"
                rag_section += f"  Tu as répondu : {ex['replied']}\n\n"

        # ── Section contexte contact ───────────────────────────
        contact_section = ""
        if contact_ctx:
            cname = contact_ctx.get("name", "ce contact")
            avg   = contact_ctx.get("avg_length", ctx["avg_length"])
            cwords = ", ".join(contact_ctx.get("common_words", [])[:8])
            recent = contact_ctx.get("recent_my_msgs", [])
            contact_section = f"""
══════════ TON STYLE SPÉCIFIQUE AVEC {cname.upper()} ══════════
{contact_ctx.get("total_messages", 0)} messages échangés avec {cname}.
Longueur moyenne de tes réponses avec {cname} : {avg} mots.
Mots que tu utilises souvent avec {cname} : {cwords}
Tes messages récents avec {cname} :
{chr(10).join(f'  → "{m}"' for m in recent)}
"""

        emoji_note = (
            f"Utilise des emojis dans ~{int(ctx['emoji_rate']*100)}% de tes messages."
            if ctx["emoji_rate"] > 0.05
            else "Tu utilises très rarement les emojis."
        )
        abbrev_note = "Tu abrèges souvent : 'pk', 'jsp', 'jpp', 'stp', 'mtn', 'wsh', 'tfk'." if ctx["uses_abbreviations"] else ""
        slang_note  = "Tu utilises de l'argot naturellement (wsh, cimer, ouf, frère, ya, etc.)." if ctx["uses_slang"] else ""
        context_line = f"\nContexte : {context_note}" if context_note else ""

        prompt = f"""Tu es le jumeau digital de {name}.
Tu dois répondre EXACTEMENT comme lui, en imitant son vrai style appris depuis ses conversations réelles.

══════════ PROFIL DE PERSONNALITÉ ══════════

🔤 VOCABULAIRE LES PLUS UTILISÉS :
{ctx['vocabulary']}

📏 LONGUEUR TYPIQUE : {ctx['avg_length']} mots par message
{emoji_note}
😀 EMOJIS FAVORIS : {ctx['emojis']}
🎭 TON DOMINANT : {ctx['tone']}
💬 EXPRESSIONS TYPIQUES : {ctx['expressions']}
🗣️  MOTS DE REMPLISSAGE : {ctx['filler_words']}
{slang_note}
{abbrev_note}

👤 STYLE AVEC CE TYPE D'INTERLOCUTEUR ({person_type}) :
{style}
{contact_section}{rag_section}
══════════ RÈGLES ABSOLUES ══════════

1. Réponds comme {name} — PAS comme un assistant IA générique.
2. Longueur : {ctx['avg_length']} mots environ (respecte ça strictement).
3. Utilise ses expressions, abréviations et emojis naturellement.
4. NE dis JAMAIS que tu es une IA, un jumeau ou un assistant.
5. UNE seule réponse courte, comme dans un vrai chat WhatsApp.
6. Pas de "Bonjour, comment puis-je vous aider" ni de formules.
7. Si les exemples réels montrent des réponses courtes → sois court.{context_line}
"""
        return prompt

    # ─────────────────────────────────────────────────────────
    # Gestion des messages
    # ─────────────────────────────────────────────────────────

    def _build_messages(
        self, incoming_message: str, history: Optional[List[dict]] = None
    ) -> List[dict]:
        messages = []
        if history:
            # Garder les 15 derniers échanges pour le contexte
            for h in history[-15:]:
                messages.append({
                    "role":    h.get("role", "user"),
                    "content": h.get("content", ""),
                })
        messages.append({"role": "user", "content": incoming_message})
        return messages

    def _generate_alternatives(
        self, system_prompt: str, messages: List[dict], main_response: str
    ) -> List[str]:
        """Génère 2 variantes avec Groq."""
        alts = []
        variant_prompt = (
            system_prompt
            + "\n\nGénère une COURTE variante différente de ta réponse (même sens, autre formulation)."
        )
        for _ in range(2):
            try:
                alt_msgs = [
                    {"role": "system", "content": variant_prompt},
                    *messages[1:],
                    {"role": "assistant", "content": main_response},
                    {"role": "user", "content": "Autre formulation courte :"},
                ]
                resp = self.client.chat.completions.create(
                    model=self.model,
                    messages=alt_msgs,
                    max_tokens=256,
                    temperature=DEFAULT_TEMPERATURE + 0.15,
                )
                alt = resp.choices[0].message.content.strip()
                if alt and alt != main_response:
                    alts.append(alt)
            except Exception:
                pass
        return alts

    # ─────────────────────────────────────────────────────────
    # Validation et qualité
    # ─────────────────────────────────────────────────────────

    def _validate_style(self, response: str, profile: PersonalityProfile) -> str:
        """
        Vérifie que la réponse respecte le style.
        Si trop longue, tronque à la dernière phrase naturelle.
        """
        avg = profile.avg_message_length
        words = response.split()

        # Si > 3× la longueur moyenne, tronquer
        if avg > 0 and len(words) > avg * 3:
            # Trouver la fin naturelle (., !, ?)
            truncated = ' '.join(words[:int(avg * 2)])
            for punct in ['. ', '! ', '? ', '.\n', '!\n']:
                idx = truncated.rfind(punct)
                if idx > len(truncated) // 2:
                    return truncated[:idx + 1].strip()
            return truncated.strip()

        return response

    def _estimate_confidence(self, profile: PersonalityProfile, rag_examples: list = None) -> float:
        """
        Estime la confiance basée sur :
        - Quantité de données apprises
        - Présence d'exemples RAG
        """
        n = profile.total_messages_analyzed
        if n >= 500:
            base = 0.90
        elif n >= 200:
            base = 0.75
        elif n >= 50:
            base = 0.55
        elif n >= 10:
            base = 0.35
        else:
            base = 0.15

        # Bonus RAG
        rag_bonus = min(len(rag_examples or []) * 0.02, 0.10)
        return min(base + rag_bonus, 0.99)

    def build_system_prompt_preview(self, person_type: str = "close_friend") -> str:
        ctx = self.engine.build_system_prompt_context()
        return self._build_system_prompt(ctx, person_type, "")


# ─────────────────────────────────────────────────────────────
# CLI test rapide
# ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    gen = ResponseGenerator()

    if not gen.client.api_key:
        print("⚠️  Définis GROQ_API_KEY dans .env")
        sys.exit(1)

    profile = gen.engine.get_profile()
    if profile.total_messages_analyzed == 0:
        print("⚠️  Aucun profil — importe d'abord des conversations.")
        sys.exit(1)

    print(f"\n🤖 Digital Twin v2 — {profile.name} ({DEFAULT_MODEL})")
    print(f"📊 {profile.total_messages_analyzed} messages appris")
    print(f"🔍 RAG Supabase: {'✅ actif' if gen._supabase else '❌ inactif'}\n")
    print("─" * 50)

    while True:
        try:
            msg = input("Message reçu : ").strip()
            if not msg or msg.lower() in {"quit", "exit", "q"}:
                break

            result = gen.suggest(msg)
            print(f"\n✉️  Réponse ({result['model']}) [{result['rag_examples']} exemples RAG] :")
            print(f"  {result['response']}")
            if result.get("alternatives"):
                for i, alt in enumerate(result["alternatives"], 1):
                    print(f"  Alt {i}: {alt}")
            print(f"\n📊 Confiance : {int(result['confidence']*100)}%\n{'─'*50}")

        except KeyboardInterrupt:
            break
