"""
personality_engine.py — Le cœur du Digital Twin AI
Stocke, met à jour et sérialise le profil de personnalité complet.
"""

import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple


# ─────────────────────────────────────────────────────────────
# Dataclasses
# ─────────────────────────────────────────────────────────────

@dataclass
class TimePattern:
    """Patterns de réponse selon l'heure de la journée."""
    morning: str = ""      # 06:00 – 12:00
    afternoon: str = ""    # 12:00 – 18:00
    evening: str = ""      # 18:00 – 23:00
    night: str = ""        # 23:00 – 06:00


@dataclass
class PersonStyle:
    """Style de réponse adapté à un type de personne."""
    tone: str = ""
    avg_length: float = 0.0
    common_openers: List[str] = field(default_factory=list)
    common_closers: List[str] = field(default_factory=list)
    uses_emojis: bool = True
    formality: str = "informal"   # informal | semi-formal | formal


@dataclass
class PersonalityProfile:
    """
    Profil de personnalité complet d'un utilisateur,
    appris depuis ses vraies conversations.
    """
    # Identité
    name: str = "Motaz"
    version: int = 1
    last_updated: str = ""

    # Statistiques générales
    total_messages_analyzed: int = 0
    avg_message_length: float = 0.0          # en mots
    avg_message_length_chars: float = 0.0    # en caractères
    response_delay_avg_minutes: float = 0.0

    # Vocabulaire
    top_words: List[Tuple[str, int]] = field(default_factory=list)        # [(mot, freq)]
    top_bigrams: List[Tuple[str, int]] = field(default_factory=list)
    typical_expressions: List[str] = field(default_factory=list)
    filler_words: List[str] = field(default_factory=list)

    # Emojis
    top_emojis: List[Tuple[str, int]] = field(default_factory=list)       # [(emoji, freq)]
    emoji_usage_rate: float = 0.0    # % messages contenant un emoji

    # Ton & style
    tone_scores: Dict[str, float] = field(default_factory=lambda: {
        "humor": 0.0,
        "sarcasm": 0.0,
        "warmth": 0.0,
        "directness": 0.0,
        "formality": 0.0,
    })
    dominant_tone: str = "informal"
    uses_slang: bool = False
    uses_abbreviations: bool = False
    punctuation_style: str = ""     # ex: "rarement des points, beaucoup de ..."

    # Patterns temporels
    time_patterns: TimePattern = field(default_factory=TimePattern)

    # Styles selon le type d'interlocuteur
    person_styles: Dict[str, PersonStyle] = field(default_factory=lambda: {
        "close_friend": PersonStyle(),
        "family": PersonStyle(),
        "colleague": PersonStyle(),
        "client": PersonStyle(),
        "unknown": PersonStyle(),
    })

    # Sujets fréquents
    frequent_topics: List[str] = field(default_factory=list)

    # Exemples de messages réels (anonymisés)
    sample_messages: List[str] = field(default_factory=list)

    # Métadonnées sources
    sources: List[str] = field(default_factory=list)   # ["whatsapp", "telegram", ...]

    # ─────────────────────────────────────────────────────────
    # Méthodes utilitaires
    # ─────────────────────────────────────────────────────────

    def update_timestamp(self):
        self.last_updated = datetime.now().isoformat()

    def to_dict(self) -> dict:
        d = asdict(self)
        d["time_patterns"] = asdict(self.time_patterns)
        d["person_styles"] = {k: asdict(v) for k, v in self.person_styles.items()}
        return d

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)

    @classmethod
    def from_dict(cls, data: dict) -> "PersonalityProfile":
        p = cls()
        for key, val in data.items():
            if key == "time_patterns":
                p.time_patterns = TimePattern(**val)
            elif key == "person_styles":
                p.person_styles = {k: PersonStyle(**v) for k, v in val.items()}
            elif hasattr(p, key):
                setattr(p, key, val)
        return p

    @classmethod
    def load(cls, path: Path) -> "PersonalityProfile":
        if path.exists():
            with open(path, "r", encoding="utf-8") as f:
                return cls.from_dict(json.load(f))
        return cls()

    def save(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.update_timestamp()
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, ensure_ascii=False, indent=2)

    def summary(self) -> str:
        """Résumé lisible du profil."""
        top_w = ", ".join(w for w, _ in self.top_words[:10])
        top_e = " ".join(e for e, _ in self.top_emojis[:8])
        exprs = " | ".join(self.typical_expressions[:5])
        return (
            f"👤 Profil : {self.name}  (v{self.version})\n"
            f"📊 Messages analysés : {self.total_messages_analyzed}\n"
            f"✍️  Longueur moyenne  : {self.avg_message_length:.1f} mots\n"
            f"🎭 Ton dominant      : {self.dominant_tone}\n"
            f"🔤 Mots fréquents    : {top_w}\n"
            f"😀 Emojis favoris    : {top_e}\n"
            f"💬 Expressions types : {exprs}\n"
            f"📡 Sources           : {', '.join(self.sources)}\n"
            f"🕒 Mis à jour        : {self.last_updated}"
        )


# ─────────────────────────────────────────────────────────────
# PersonalityEngine — moteur d'agrégation
# ─────────────────────────────────────────────────────────────

class PersonalityEngine:
    """
    Reçoit des listes de messages bruts et met à jour
    le PersonalityProfile de façon incrémentale.
    """

    EMOJI_PATTERN = re.compile(
        "[\U00010000-\U0010ffff"
        "\U0001F600-\U0001F64F"
        "\U0001F300-\U0001F5FF"
        "\U0001F680-\U0001F9FF"
        "\u2600-\u26FF\u2700-\u27BF]+",
        flags=re.UNICODE,
    )

    STOP_WORDS = {
        "le", "la", "les", "de", "du", "des", "un", "une",
        "et", "en", "à", "au", "aux", "je", "tu", "il", "elle",
        "on", "nous", "vous", "ils", "elles", "que", "qui",
        "est", "sont", "a", "ai", "as", "avons", "have", "the",
        "is", "in", "it", "to", "of", "and", "for", "this",
        "me", "mon", "ma", "mes", "se", "sa", "si", "ou",
        "pas", "ne", "plus", "mais", "sur", "par", "avec",
        "ce", "ça", "ca", "c'est", "j'ai", "t'as", "y",
    }

    def __init__(self, profile_path: Optional[Path] = None):
        self.profile_path = profile_path or Path(
            "data/personality_profile/profile.json"
        )
        self.profile = PersonalityProfile.load(self.profile_path)

    # ── Analyse principale ─────────────────────────────────

    def ingest(self, messages: List[dict], source: str = "unknown"):
        """
        messages : liste de dicts {"text": str, "timestamp": str}
        source   : "whatsapp" | "telegram" | "instagram"
        """
        if not messages:
            return

        texts = [m["text"] for m in messages if m.get("text")]

        self._update_counts(texts)
        self._update_vocabulary(texts)
        self._update_emojis(texts)
        self._update_tone(texts)
        self._update_time_patterns(messages)
        self._update_samples(texts)

        if source not in self.profile.sources:
            self.profile.sources.append(source)

        self.profile.version += 1
        self.profile.save(self.profile_path)
        print(f"✅ Profil mis à jour — {len(texts)} messages de {source} ingérés.")

    # ── Méthodes internes ──────────────────────────────────

    def _update_counts(self, texts: List[str]):
        p = self.profile
        new_total = p.total_messages_analyzed + len(texts)
        word_counts = [len(t.split()) for t in texts]
        char_counts = [len(t) for t in texts]

        # Moyenne glissante
        if p.total_messages_analyzed > 0:
            p.avg_message_length = (
                p.avg_message_length * p.total_messages_analyzed
                + sum(word_counts)
            ) / new_total
            p.avg_message_length_chars = (
                p.avg_message_length_chars * p.total_messages_analyzed
                + sum(char_counts)
            ) / new_total
        else:
            p.avg_message_length = sum(word_counts) / len(word_counts)
            p.avg_message_length_chars = sum(char_counts) / len(char_counts)

        p.total_messages_analyzed = new_total

    def _update_vocabulary(self, texts: List[str]):
        p = self.profile
        all_words = []
        bigrams_list = []

        for text in texts:
            clean = re.sub(r"[^\w\s']", " ", text.lower())
            words = [w for w in clean.split() if w not in self.STOP_WORDS and len(w) > 1]
            all_words.extend(words)
            bigrams_list.extend(
                f"{words[i]} {words[i+1]}" for i in range(len(words) - 1)
            )

        # Merge avec existant
        existing_words = dict(p.top_words)
        new_counts = Counter(all_words)
        for w, c in new_counts.items():
            existing_words[w] = existing_words.get(w, 0) + c
        p.top_words = Counter(existing_words).most_common(100)

        existing_bi = dict(p.top_bigrams)
        new_bi = Counter(bigrams_list)
        for b, c in new_bi.items():
            existing_bi[b] = existing_bi.get(b, 0) + c
        p.top_bigrams = Counter(existing_bi).most_common(50)

        # Expressions typiques (bigrams fréquents non-stop)
        p.typical_expressions = [b for b, _ in p.top_bigrams[:20]]

        # Abréviations & argot
        abbrevs = {"lol", "mdr", "ptdr", "wsh", "jsp", "jpp", "ofc", "tbh",
                   "ngl", "imo", "btw", "asap", "ok", "okay", "ouai", "ouais"}
        found = set(all_words) & abbrevs
        p.uses_abbreviations = len(found) > 0
        p.uses_slang = len(found) > 2

        # Mots de remplissage
        fillers = {"bah", "ben", "beh", "voilà", "voila", "quoi", "hein", "genre", "genre"}
        p.filler_words = list(set(all_words) & fillers)

    def _update_emojis(self, texts: List[str]):
        p = self.profile
        emoji_counter: Counter = Counter()
        messages_with_emoji = 0

        for text in texts:
            found = self.EMOJI_PATTERN.findall(text)
            if found:
                messages_with_emoji += 1
                for e in found:
                    emoji_counter[e] += 1

        existing = dict(p.top_emojis)
        for e, c in emoji_counter.items():
            existing[e] = existing.get(e, 0) + c
        p.top_emojis = Counter(existing).most_common(30)

        total = p.total_messages_analyzed
        p.emoji_usage_rate = messages_with_emoji / total if total else 0.0

    def _update_tone(self, texts: List[str]):
        p = self.profile
        humor_kw = {"lol", "mdr", "haha", "😂", "😄", "xd", "hahaha", "ptdr", "💀", "🤣"}
        warm_kw = {"❤️", "🥰", "😍", "bisous", "bises", "chéri", "amor", "habibi", "love"}
        formal_kw = {"cordialement", "bonjour", "madame", "monsieur", "merci beaucoup",
                     "veuillez", "je vous"}
        direct_kw = {"ok", "oui", "non", "c'est bon", "parfait", "compris", "roger"}
        sarcasm_kw = {"bien sûr", "évidemment", "comme par hasard", "no way", "sérieusement"}

        counts = defaultdict(int)
        total = len(texts)
        for text in texts:
            t = text.lower()
            for kw in humor_kw:
                if kw in t:
                    counts["humor"] += 1
            for kw in warm_kw:
                if kw in t:
                    counts["warmth"] += 1
            for kw in formal_kw:
                if kw in t:
                    counts["formality"] += 1
            for kw in direct_kw:
                if kw in t:
                    counts["directness"] += 1
            for kw in sarcasm_kw:
                if kw in t:
                    counts["sarcasm"] += 1

        if total > 0:
            for tone in p.tone_scores:
                p.tone_scores[tone] = round(counts[tone] / total, 3)

        # Ton dominant
        p.dominant_tone = max(p.tone_scores, key=p.tone_scores.get)
        if p.tone_scores["formality"] < 0.05:
            p.dominant_tone = "informel"

    def _update_time_patterns(self, messages: List[dict]):
        tp = self.profile.time_patterns
        hour_counts = defaultdict(int)

        for m in messages:
            ts = m.get("timestamp", "")
            if not ts:
                continue
            try:
                dt = datetime.fromisoformat(ts)
                hour_counts[dt.hour] += 1
            except Exception:
                pass

        if not hour_counts:
            return

        morning = sum(hour_counts[h] for h in range(6, 12))
        afternoon = sum(hour_counts[h] for h in range(12, 18))
        evening = sum(hour_counts[h] for h in range(18, 23))
        night = sum(hour_counts[h] for h in range(23, 24)) + sum(hour_counts[h] for h in range(0, 6))

        peak = max([("matin", morning), ("après-midi", afternoon),
                    ("soir", evening), ("nuit", night)], key=lambda x: x[1])

        tp.morning = f"{morning} messages"
        tp.afternoon = f"{afternoon} messages"
        tp.evening = f"{evening} messages"
        tp.night = f"{night} messages"

        self.profile.time_patterns = tp

    def _update_samples(self, texts: List[str], max_samples: int = 50):
        """Garde des exemples représentatifs (longueur proche de la moyenne)."""
        avg = self.profile.avg_message_length
        scored = sorted(texts, key=lambda t: abs(len(t.split()) - avg))
        self.profile.sample_messages = list(
            dict.fromkeys(self.profile.sample_messages + scored[:10])
        )[:max_samples]

    # ── API publique ───────────────────────────────────────

    def get_profile(self) -> PersonalityProfile:
        return self.profile

    def build_system_prompt_context(self) -> dict:
        """Retourne les variables utilisées dans le system prompt dynamique."""
        p = self.profile
        return {
            "name": p.name,
            "vocabulary": ", ".join(w for w, _ in p.top_words[:20]),
            "avg_length": round(p.avg_message_length, 1),
            "tone": p.dominant_tone,
            "emojis": " ".join(e for e, _ in p.top_emojis[:10]),
            "expressions": " | ".join(p.typical_expressions[:10]),
            "uses_slang": p.uses_slang,
            "uses_abbreviations": p.uses_abbreviations,
            "emoji_rate": p.emoji_usage_rate,
            "close_person_style": self._style_summary("close_friend"),
            "formal_style": self._style_summary("client"),
            "sample_messages": "\n".join(f'  • "{s}"' for s in p.sample_messages[:5]),
            "filler_words": ", ".join(p.filler_words),
        }

    def _style_summary(self, style_key: str) -> str:
        s = self.profile.person_styles.get(style_key, PersonStyle())
        return (
            f"ton={s.tone or 'naturel'}, "
            f"longueur≈{s.avg_length or self.profile.avg_message_length:.0f} mots, "
            f"émojis={'oui' if s.uses_emojis else 'non'}"
        )

    def reset(self):
        """Remet le profil à zéro (utile pour les tests)."""
        self.profile = PersonalityProfile()
        self.profile.save(self.profile_path)
        print("🔄 Profil réinitialisé.")
