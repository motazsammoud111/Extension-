"""
response_generator.py — Génère des réponses dans ton style exact
via l'API Groq (modèle libre rapide) + profil de personnalité dynamique.
Pour revenir à Claude plus tard, il suffit de changer l'import et le client.
"""

import os
from typing import List, Optional
from pathlib import Path

from openai import OpenAI   # ← plus anthropic

from personality_engine import PersonalityEngine, PersonalityProfile


# ─────────────────────────────────────────────────────────────
# Constantes
# ─────────────────────────────────────────────────────────────

DEFAULT_MODEL = "llama-3.1-8b-instant"   # rapide et gratuit sur Groq
DEFAULT_MAX_TOKENS = 1024
DEFAULT_TEMPERATURE = 0.9   # un peu de créativité


# ─────────────────────────────────────────────────────────────
# ResponseGenerator
# ─────────────────────────────────────────────────────────────

class ResponseGenerator:
    """
    Utilise le profil de personnalité pour construire un system prompt
    dynamique et appeler Groq (via OpenAI SDK) pour générer une réponse
    qui imite ton style.
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

    # ─────────────────────────────────────────────────────
    # API principale
    # ─────────────────────────────────────────────────────

    def suggest(
        self,
        incoming_message: str,
        conversation_history: Optional[List[dict]] = None,
        person_type: str = "close_friend",
        context_note: str = "",
    ) -> dict:
        """
        Génère une réponse dans ton style.

        Paramètres :
          incoming_message     : le message reçu auquel tu dois répondre
          conversation_history : liste de dicts {"role": "user"|"assistant", "content": str}
          person_type          : "close_friend" | "family" | "colleague" | "client" | "unknown"
          context_note         : note optionnelle pour guider la réponse

        Retourne :
          {
            "response": str,
            "alternatives": [str, str],
            "confidence": float,
            "model": str,
          }
        """
        profile = self.engine.get_profile()
        ctx = self.engine.build_system_prompt_context()

        system_prompt = self._build_system_prompt(ctx, person_type, context_note)
        messages = self._build_messages(incoming_message, conversation_history)

        # Insère le system prompt en tête (format OpenAI)
        openai_messages = [{"role": "system", "content": system_prompt}] + messages

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=openai_messages,
                max_tokens=DEFAULT_MAX_TOKENS,
                temperature=DEFAULT_TEMPERATURE,
            )
            main_response = response.choices[0].message.content.strip()

            # Générer 2 alternatives légèrement différentes
            alternatives = self._generate_alternatives(
                system_prompt, openai_messages, main_response
            )

            return {
                "response": main_response,
                "alternatives": alternatives,
                "confidence": self._estimate_confidence(profile),
                "model": self.model,
                "person_type": person_type,
            }

        except Exception as e:   # OpenAI / Groq lèvent des exceptions standard
            return {
                "error": str(e),
                "response": "",
                "alternatives": [],
                "confidence": 0.0,
                "model": self.model,
            }

    def suggest_simple(self, incoming_message: str, person_type: str = "close_friend") -> str:
        """Version simplifiée — retourne juste le texte de la réponse."""
        result = self.suggest(incoming_message, person_type=person_type)
        return result.get("response", "")

    # ─────────────────────────────────────────────────────
    # Construction du system prompt dynamique
    # ─────────────────────────────────────────────────────

    def _build_system_prompt(self, ctx: dict, person_type: str, context_note: str) -> str:
        name = ctx["name"]
        close_style = ctx["close_person_style"]
        formal_style = ctx["formal_style"]

        # Style adapté au type d'interlocuteur
        if person_type in ("close_friend", "family"):
            adapted_style = close_style
        elif person_type in ("client", "unknown"):
            adapted_style = formal_style
        else:
            adapted_style = close_style

        slang_note = "Il utilise souvent de l'argot et des abréviations." if ctx["uses_slang"] else ""
        abbrev_note = "Il abrège souvent : 'pk', 'jsp', 'jpp', 'stp', 'mtn', 'wsh'." if ctx["uses_abbreviations"] else ""
        emoji_note = (
            f"Il utilise des emojis dans ~{int(ctx['emoji_rate']*100)}% de ses messages."
            if ctx["emoji_rate"] > 0.1 else "Il utilise rarement les emojis."
        )

        context_line = f"\nContexte supplémentaire : {context_note}" if context_note else ""

        prompt = f"""Tu es le jumeau digital de {name}.
Tu dois répondre EXACTEMENT comme lui, en imitant son style de communication appris depuis ses vraies conversations.

══════════════ PROFIL DE PERSONNALITÉ ══════════════

🔤 VOCABULAIRE FRÉQUENT :
{ctx['vocabulary']}

📏 LONGUEUR DES MESSAGES :
Ses messages font en moyenne {ctx['avg_length']} mots.
Respecte cette longueur — ni trop court, ni trop long.

🎭 TON DOMINANT : {ctx['tone']}

😀 EMOJIS FAVORIS : {ctx['emojis']}
{emoji_note}

💬 EXPRESSIONS TYPIQUES :
{ctx['expressions']}

🗣️ MOTS DE REMPLISSAGE : {ctx['filler_words']}
{slang_note}
{abbrev_note}

👤 STYLE SELON L'INTERLOCUTEUR :
- Ami proche / famille : {close_style}
- Client / inconnu : {formal_style}
- Style actuel ({person_type}) : {adapted_style}

📝 EXEMPLES DE SES VRAIS MESSAGES :
{ctx['sample_messages']}
{context_line}

══════════════ RÈGLES ABSOLUES ══════════════

1. Réponds EXACTEMENT dans le style de {name} — pas de style générique.
2. Respecte sa longueur moyenne de message ({ctx['avg_length']} mots).
3. Utilise ses emojis habituels si le contexte s'y prête.
4. Utilise ses expressions et mots typiques naturellement.
5. NE dis jamais que tu es une IA ou un jumeau digital.
6. UNE seule réponse, comme dans un vrai chat.
7. Pas de formules de politesse artificielles.
8. Adopte son niveau de langage : {'familier/argotique' if ctx['uses_slang'] else 'naturel'}.
"""
        return prompt

    # ─────────────────────────────────────────────────────
    # Gestion des messages
    # ─────────────────────────────────────────────────────

    def _build_messages(
        self,
        incoming_message: str,
        history: Optional[List[dict]] = None,
    ) -> List[dict]:
        messages = []

        if history:
            # Inclure les N derniers échanges pour le contexte
            for h in history[-10:]:
                messages.append({
                    "role": h.get("role", "user"),
                    "content": h.get("content", ""),
                })

        messages.append({
            "role": "user",
            "content": incoming_message,
        })

        return messages

    def _generate_alternatives(
        self,
        system_prompt: str,
        messages: List[dict],   # déjà avec system prompt en tête
        main_response: str,
    ) -> List[str]:
        """Génère 2 variantes alternatives en utilisant Groq."""
        alternatives = []
        variant_prompt = (
            system_prompt
            + "\n\nGénère une variante légèrement différente de ta réponse précédente "
            + "(même style, formulé autrement)."
        )

        for _ in range(2):
            try:
                # Construire l'historique complet + la demande de variante
                alt_messages = [
                    {"role": "system", "content": variant_prompt},
                    *messages[1:],   # garde les messages user/assistant sans le system original
                    {"role": "assistant", "content": main_response},
                    {"role": "user", "content": "Donne une autre formulation de ta réponse (même sens, style identique)."},
                ]
                resp = self.client.chat.completions.create(
                    model=self.model,
                    messages=alt_messages,
                    max_tokens=512,
                    temperature=DEFAULT_TEMPERATURE + 0.1,
                )
                alternatives.append(resp.choices[0].message.content.strip())
            except Exception:
                pass

        return alternatives

    # ─────────────────────────────────────────────────────
    # Utilitaires
    # ─────────────────────────────────────────────────────

    def _estimate_confidence(self, profile: PersonalityProfile) -> float:
        """
        Estime la confiance en la qualité de la réponse
        basé sur la quantité de données apprises.
        """
        n = profile.total_messages_analyzed
        if n >= 500:
            return 0.95
        elif n >= 200:
            return 0.80
        elif n >= 50:
            return 0.60
        elif n >= 10:
            return 0.40
        return 0.20

    def build_system_prompt_preview(self, person_type: str = "close_friend") -> str:
        """Retourne le system prompt tel qu'il sera envoyé à Groq (pour debug)."""
        ctx = self.engine.build_system_prompt_context()
        return self._build_system_prompt(ctx, person_type, "")


# ─────────────────────────────────────────────────────────────
# CLI pour tester rapidement
# ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    gen = ResponseGenerator()

    if not gen.client.api_key:
        print("⚠️  Définis GROQ_API_KEY dans .env avant de tester.")
        sys.exit(1)

    profile = gen.engine.get_profile()
    if profile.total_messages_analyzed == 0:
        print("⚠️  Aucun profil chargé — importe d'abord des conversations.")
        print("   python conversation_analyzer.py data/raw_conversations/")
        sys.exit(1)

    print(f"\n🤖 Digital Twin de {profile.name} — Prêt à répondre (via Groq) !\n")
    print("─" * 50)

    while True:
        try:
            msg = input("Message reçu : ").strip()
            if not msg:
                continue
            if msg.lower() in {"quit", "exit", "q"}:
                break

            result = gen.suggest(msg)
            print(f"\n✉️  Réponse principale :\n  {result['response']}")
            if result.get("alternatives"):
                print("\n📋 Alternatives :")
                for i, alt in enumerate(result["alternatives"], 1):
                    print(f"  {i}. {alt}")
            print(f"\n📊 Confiance : {int(result['confidence']*100)}%\n{'─'*50}")

        except KeyboardInterrupt:
            print("\n👋 Au revoir !")
            break