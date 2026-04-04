"""
fine_tune.py — Pipeline d'entraînement continu
Réentraîne le profil à chaque nouveaux messages, suit la progression.
Usage : python fine_tune.py [--watch] [--interval 60]
"""

import json
import os
import sys
import time
import hashlib
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from personality_engine import PersonalityEngine
from conversation_analyzer import ConversationAnalyzer
from memory_store import MemoryStore


class FineTuningPipeline:
    """
    Pipeline d'entraînement continu.
    Surveille les nouveaux fichiers dans raw_conversations/
    et met à jour le profil automatiquement.
    """

    def __init__(self, my_name: str, base_dir: Path):
        self.my_name = my_name
        self.base_dir = base_dir
        self.raw_dir = base_dir / "data" / "raw_conversations"
        self.proc_dir = base_dir / "data" / "processed"
        self.prof_path = base_dir / "data" / "personality_profile" / "profile.json"
        self.db_path = base_dir / "data" / "memory.db"
        self.state_path = base_dir / "data" / "processed" / ".processed_files.json"

        self.proc_dir.mkdir(parents=True, exist_ok=True)

        self.engine = PersonalityEngine(profile_path=self.prof_path)
        self.analyzer = ConversationAnalyzer(my_name=my_name, engine=self.engine)
        self.store = MemoryStore(db_path=str(self.db_path))

        self._processed: dict = self._load_state()

    # ── État ───────────────────────────────────────────────

    def _load_state(self) -> dict:
        if self.state_path.exists():
            with open(self.state_path, "r") as f:
                return json.load(f)
        return {}

    def _save_state(self):
        with open(self.state_path, "w") as f:
            json.dump(self._processed, f, indent=2)

    def _file_hash(self, path: Path) -> str:
        with open(path, "rb") as f:
            return hashlib.md5(f.read()).hexdigest()

    def _is_new_or_modified(self, path: Path) -> bool:
        current_hash = self._file_hash(path)
        return self._processed.get(str(path)) != current_hash

    # ── Pipeline principal ─────────────────────────────────

    def run_once(self) -> dict:
        """Analyse tous les fichiers nouveaux/modifiés."""
        files = list(self.raw_dir.glob("*.txt")) + list(self.raw_dir.glob("*.json"))
        new_files = [f for f in files if self._is_new_or_modified(f)]

        if not new_files:
            print(f"✅ Profil à jour — aucun nouveau fichier.")
            return {"new_files": 0, "total_files": len(files)}

        print(f"\n🔄 {len(new_files)} nouveau(x) fichier(s) détecté(s)")
        before = self.engine.get_profile().total_messages_analyzed
        before_version = self.engine.get_profile().version

        processed_count = 0
        for f in new_files:
            try:
                print(f"  → Traitement : {f.name}")
                report = self.analyzer.analyze_file(f)
                if "error" not in report:
                    # Marquer comme traité
                    self._processed[str(f)] = self._file_hash(f)
                    processed_count += 1
                    self.store.log_event("auto_train", {
                        "file": f.name,
                        "my_messages": report.get("my_messages", 0),
                    })
            except Exception as e:
                print(f"  ❌ Erreur sur {f.name}: {e}")

        self._save_state()

        after = self.engine.get_profile().total_messages_analyzed
        after_version = self.engine.get_profile().version

        # Snapshot de profil
        self.store.save_personality_snapshot(
            self.engine.get_profile().to_dict(),
            after_version,
        )

        result = {
            "new_files": processed_count,
            "total_files": len(files),
            "messages_before": before,
            "messages_after": after,
            "messages_added": after - before,
            "version_before": before_version,
            "version_after": after_version,
            "timestamp": datetime.now().isoformat(),
        }
        self._print_run_report(result)
        return result

    def watch(self, interval_seconds: int = 60):
        """Mode surveillance — vérifie en continu les nouveaux fichiers."""
        print(f"\n👁️  Mode surveillance activé (intervalle: {interval_seconds}s)")
        print(f"📂 Dossier surveillé : {self.raw_dir}")
        print("   Ctrl+C pour arrêter\n")

        run_count = 0
        try:
            while True:
                run_count += 1
                print(f"[{datetime.now().strftime('%H:%M:%S')}] Run #{run_count}")
                self.run_once()
                time.sleep(interval_seconds)
        except KeyboardInterrupt:
            print(f"\n🛑 Surveillance arrêtée après {run_count} runs.")
            print(self.engine.get_profile().summary())

    def generate_training_report(self, output_path: Path):
        """Génère un rapport complet d'entraînement."""
        profile = self.engine.get_profile()
        stats = self.store.get_stats()

        report = {
            "generated_at": datetime.now().isoformat(),
            "profile": profile.to_dict(),
            "stats": stats,
            "processed_files": list(self._processed.keys()),
            "training_quality": self._assess_quality(profile),
        }

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)

        print(f"📊 Rapport d'entraînement : {output_path}")
        return report

    def _assess_quality(self, profile) -> dict:
        """Évalue la qualité du profil d'entraînement."""
        n = profile.total_messages_analyzed
        quality_score = min(100, int(n / 5))   # 100% à 500+ messages

        if n < 10:
            level = "insufficient"
            advice = "Importe plus de conversations. Minimum 50 messages recommandé."
        elif n < 50:
            level = "beginner"
            advice = "Bon début ! Le profil s'améliore avec plus de données."
        elif n < 200:
            level = "good"
            advice = "Profil correct. 200+ messages pour un style très précis."
        elif n < 500:
            level = "great"
            advice = "Excellent profil ! Le twin est très représentatif."
        else:
            level = "expert"
            advice = "Profil expert — le twin imite ton style avec haute fidélité."

        return {
            "level": level,
            "score": quality_score,
            "messages_analyzed": n,
            "advice": advice,
            "has_emojis": len(profile.top_emojis) > 0,
            "has_expressions": len(profile.typical_expressions) > 0,
            "sources_count": len(profile.sources),
        }

    def _print_run_report(self, report: dict):
        print(f"  ✅ +{report['messages_added']} messages")
        print(f"  📊 Total : {report['messages_after']} messages")
        print(f"  🔖 Version profil : v{report['version_after']}")


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Pipeline d'entraînement continu")
    parser.add_argument("--watch", "-w", action="store_true",
                        help="Mode surveillance continue")
    parser.add_argument("--interval", "-i", type=int, default=60,
                        help="Intervalle de surveillance en secondes (défaut: 60)")
    parser.add_argument("--name", "-n", default=os.getenv("MY_NAME", "Motaz"),
                        help="Ton nom dans les exports")
    parser.add_argument("--report", "-r", default=None,
                        help="Générer un rapport d'entraînement")
    args = parser.parse_args()

    base_dir = Path(__file__).parent.parent
    pipeline = FineTuningPipeline(my_name=args.name, base_dir=base_dir)

    if args.watch:
        pipeline.watch(interval_seconds=args.interval)
    else:
        pipeline.run_once()

    if args.report:
        pipeline.generate_training_report(Path(args.report))


if __name__ == "__main__":
    main()
