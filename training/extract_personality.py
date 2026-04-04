"""
extract_personality.py — Extraction avancée de personnalité
Analyse approfondie du profil depuis les messages déjà importés.
Usage : python extract_personality.py [--output <path>]
"""

import json
import os
import sys
import re
from collections import Counter
from pathlib import Path
from typing import List, Dict

sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from personality_engine import PersonalityEngine, PersonalityProfile
from memory_store import MemoryStore


class PersonalityExtractor:
    """
    Extraction avancée de traits de personnalité
    depuis les messages stockés en DB ou en profil.
    """

    def __init__(self, engine: PersonalityEngine, store: MemoryStore):
        self.engine = engine
        self.store = store

    def extract_all(self) -> dict:
        """Extraction complète — retourne un rapport enrichi."""
        msgs = self.store.get_my_messages(limit=10000)
        texts = [m["text"] for m in msgs if m.get("text")]

        if not texts:
            return {"error": "Aucun message trouvé. Importe d'abord des conversations."}

        print(f"🔍 Analyse de {len(texts)} messages...")

        report = {
            "message_count": len(texts),
            "style_markers": self._extract_style_markers(texts),
            "response_patterns": self._extract_response_patterns(msgs),
            "conversation_rhythms": self._extract_rhythms(texts),
            "emotional_signature": self._extract_emotional_signature(texts),
            "topic_clusters": self._extract_topics(texts),
            "language_profile": self._extract_language_profile(texts),
        }

        return report

    def _extract_style_markers(self, texts: List[str]) -> dict:
        """Marqueurs de style linguistique."""
        caps_count = sum(1 for t in texts if t == t.upper() and len(t) > 1)
        exclamation = sum(t.count("!") for t in texts)
        question = sum(t.count("?") for t in texts)
        ellipsis = sum(t.count("...") + t.count("…") for t in texts)

        # Messages très courts (< 3 mots)
        short_msgs = [t for t in texts if len(t.split()) < 3]
        # Messages longs (> 30 mots)
        long_msgs = [t for t in texts if len(t.split()) > 30]

        total = len(texts)
        return {
            "uses_caps_for_emphasis": caps_count / total > 0.05,
            "exclamation_rate": round(exclamation / total, 2),
            "question_rate": round(question / total, 2),
            "ellipsis_rate": round(ellipsis / total, 2),
            "short_message_rate": round(len(short_msgs) / total, 2),
            "long_message_rate": round(len(long_msgs) / total, 2),
            "short_message_examples": short_msgs[:10],
            "long_message_examples": long_msgs[:5],
            "punctuation_style": self._describe_punctuation(
                exclamation, question, ellipsis, total
            ),
        }

    def _describe_punctuation(self, exc, q, ell, total) -> str:
        parts = []
        if exc / total > 0.3:
            parts.append("très expressif avec '!'")
        elif exc / total > 0.1:
            parts.append("utilise '!' modérément")
        if q / total > 0.2:
            parts.append("pose souvent des questions")
        if ell / total > 0.2:
            parts.append("utilise souvent '...' pour suspendre")
        if not parts:
            parts = ["style ponctuation sobre"]
        return ", ".join(parts)

    def _extract_response_patterns(self, msgs: List[dict]) -> dict:
        """Patterns de réponse selon l'heure."""
        from datetime import datetime
        from collections import defaultdict

        hour_dist = defaultdict(int)
        for m in msgs:
            ts = m.get("timestamp", "")
            try:
                h = datetime.fromisoformat(ts).hour
                hour_dist[h] += 1
            except Exception:
                pass

        if not hour_dist:
            return {"note": "Pas de données temporelles disponibles"}

        total = sum(hour_dist.values())
        peak_hours = sorted(hour_dist.items(), key=lambda x: -x[1])[:3]

        return {
            "peak_hours": [{"hour": h, "messages": c, "pct": round(c/total*100, 1)}
                           for h, c in peak_hours],
            "morning_activity": round(sum(hour_dist[h] for h in range(6, 12)) / total * 100, 1),
            "afternoon_activity": round(sum(hour_dist[h] for h in range(12, 18)) / total * 100, 1),
            "evening_activity": round(sum(hour_dist[h] for h in range(18, 23)) / total * 100, 1),
            "night_activity": round((sum(hour_dist[h] for h in range(23, 24)) +
                                    sum(hour_dist[h] for h in range(0, 6))) / total * 100, 1),
        }

    def _extract_rhythms(self, texts: List[str]) -> dict:
        """Rythme d'écriture."""
        lengths = [len(t.split()) for t in texts]
        return {
            "avg_words": round(sum(lengths) / len(lengths), 1),
            "median_words": sorted(lengths)[len(lengths) // 2],
            "min_words": min(lengths),
            "max_words": max(lengths),
            "distribution": {
                "1-3 mots": sum(1 for l in lengths if l <= 3),
                "4-10 mots": sum(1 for l in lengths if 4 <= l <= 10),
                "11-30 mots": sum(1 for l in lengths if 11 <= l <= 30),
                "30+ mots": sum(1 for l in lengths if l > 30),
            },
        }

    def _extract_emotional_signature(self, texts: List[str]) -> dict:
        """Signature émotionnelle."""
        emotions = {
            "joy": ["😂", "😄", "🎉", "haha", "lol", "mdr", "génial", "super", "top", "cool", "❤️"],
            "affection": ["❤️", "🥰", "😍", "bisous", "love", "habibi", "mon ami", "frère", "fréro"],
            "frustration": ["😤", "🙄", "sérieusement", "franchement", "vraiment", "mais", "pourquoi"],
            "excitement": ["!!", "!!!","🔥","🚀","wow","incroyable","trop bien","énorme"],
            "sadness": ["😢", "😞", "dommage", "snif", "triste", "hélas", "malheureusement"],
        }

        results = {}
        total = len(texts)
        joined = " ".join(texts).lower()

        for emotion, markers in emotions.items():
            count = sum(joined.count(m.lower()) for m in markers)
            results[emotion] = round(count / total, 3)

        dominant = max(results, key=results.get)
        return {
            "scores": results,
            "dominant_emotion": dominant,
        }

    def _extract_topics(self, texts: List[str]) -> dict:
        """Clusters de sujets fréquents."""
        topic_keywords = {
            "tech": ["code", "python", "api", "dev", "app", "bug", "server", "git", "ia", "ai", "tech"],
            "food": ["manger", "restaurant", "café", "pizza", "dîner", "déjeuner", "faim", "mange"],
            "travel": ["voyage", "avion", "hôtel", "partir", "vacances", "destination", "trip"],
            "work": ["boulot", "travail", "boss", "client", "réunion", "deadline", "projet", "taff"],
            "sports": ["foot", "match", "sport", "gym", "running", "entraînement", "football"],
            "humor": ["haha", "mdr", "lol", "blague", "rigolo", "marrant", "drôle", "ptdr"],
            "family": ["famille", "parents", "frère", "sœur", "maman", "papa", "maison"],
            "friends": ["ami", "pote", "sortir", "soirée", "fête", "ensemble", "rencontrer"],
        }

        joined = " ".join(texts).lower()
        scores = {}
        for topic, keywords in topic_keywords.items():
            score = sum(joined.count(kw) for kw in keywords)
            if score > 0:
                scores[topic] = score

        ranked = sorted(scores.items(), key=lambda x: -x[1])
        return {
            "top_topics": ranked[:5],
            "topic_scores": scores,
        }

    def _extract_language_profile(self, texts: List[str]) -> dict:
        """Profil linguistique."""
        # Détection langue dominante (heuristique simple)
        fr_words = ["je", "tu", "il", "nous", "vous", "est", "les", "des", "pas", "mais"]
        en_words = ["the", "is", "you", "we", "are", "this", "that", "for", "not", "but"]
        ar_pattern = re.compile(r"[\u0600-\u06FF]")

        joined = " ".join(texts).lower()
        words = joined.split()

        fr_count = sum(1 for w in words if w in fr_words)
        en_count = sum(1 for w in words if w in en_words)
        ar_count = len(ar_pattern.findall(joined))

        if ar_count > 100:
            dominant_lang = "arabe/darija"
        elif fr_count > en_count:
            dominant_lang = "français"
        else:
            dominant_lang = "anglais"

        # Mix de langues ?
        is_mixed = (fr_count > 5 and en_count > 5) or ar_count > 50

        return {
            "dominant_language": dominant_lang,
            "is_multilingual": is_mixed,
            "french_markers": fr_count,
            "english_markers": en_count,
            "arabic_chars": ar_count,
        }


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Extraction avancée de personnalité")
    parser.add_argument("--output", "-o", default=None, help="Fichier de sortie JSON")
    args = parser.parse_args()

    base_dir = Path(__file__).parent.parent
    prof_path = base_dir / "data" / "personality_profile" / "profile.json"
    db_path = base_dir / "data" / "memory.db"

    engine = PersonalityEngine(profile_path=prof_path)
    store = MemoryStore(db_path=str(db_path))

    extractor = PersonalityExtractor(engine, store)
    report = extractor.extract_all()

    if "error" in report:
        print(f"❌ {report['error']}")
        sys.exit(1)

    print("\n" + "=" * 60)
    print("🧠 RAPPORT D'EXTRACTION DE PERSONNALITÉ")
    print("=" * 60)
    print(json.dumps(report, ensure_ascii=False, indent=2))

    if args.output:
        out = Path(args.output)
        with open(out, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        print(f"\n💾 Rapport sauvegardé : {out}")


if __name__ == "__main__":
    main()
