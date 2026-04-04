"""
import_conversations.py — Script d'importation en batch
Usage : python import_conversations.py [--folder <path>] [--file <path>] [--name <ton_nom>]
"""

import argparse
import json
import os
import sys
from pathlib import Path

# Ajouter le backend au path
sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from conversation_analyzer import ConversationAnalyzer
from memory_store import MemoryStore
from personality_engine import PersonalityEngine


def parse_args():
    parser = argparse.ArgumentParser(
        description="Importe et analyse tes conversations exportées."
    )
    parser.add_argument(
        "--folder", "-f",
        default="data/raw_conversations",
        help="Dossier contenant les fichiers exportés (défaut: data/raw_conversations)",
    )
    parser.add_argument(
        "--file", "-F",
        default=None,
        help="Fichier unique à importer",
    )
    parser.add_argument(
        "--name", "-n",
        default=os.getenv("MY_NAME", "Motaz"),
        help="Ton nom exact dans les exports (défaut: variable MY_NAME ou 'Motaz')",
    )
    parser.add_argument(
        "--source", "-s",
        default=None,
        choices=["whatsapp", "telegram", "instagram"],
        help="Forcer le type de source (auto-détecté par défaut)",
    )
    parser.add_argument(
        "--save-db", action="store_true",
        help="Sauvegarder les messages en base SQLite",
    )
    parser.add_argument(
        "--report", "-r",
        default=None,
        help="Sauvegarder le rapport JSON dans ce fichier",
    )
    return parser.parse_args()


def main():
    args = parse_args()

    print("=" * 60)
    print(f"🤖 Digital Twin AI — Importation de conversations")
    print(f"👤 Nom : {args.name}")
    print("=" * 60)

    base_dir = Path(__file__).parent.parent
    prof_path = base_dir / "data" / "personality_profile" / "profile.json"

    engine = PersonalityEngine(profile_path=prof_path)
    analyzer = ConversationAnalyzer(my_name=args.name, engine=engine)

    store = None
    if args.save_db:
        db_path = base_dir / "data" / "memory.db"
        store = MemoryStore(db_path=str(db_path))

    reports = []

    if args.file:
        path = Path(args.file)
        if not path.exists():
            print(f"❌ Fichier introuvable : {path}")
            sys.exit(1)
        report = analyzer.analyze_file(path)
        reports.append(report)
    else:
        folder = Path(args.folder)
        if not folder.exists():
            print(f"❌ Dossier introuvable : {folder}")
            print(f"   Crée-le et place-y tes exports.")
            sys.exit(1)

        files = list(folder.glob("*.txt")) + list(folder.glob("*.json"))
        if not files:
            print(f"⚠️  Aucun fichier .txt ou .json dans {folder}")
            print("   → Exporte tes conversations et place-les dans ce dossier.")
            _print_export_guide()
            sys.exit(0)

        print(f"\n📁 {len(files)} fichier(s) trouvé(s) dans {folder}\n")
        for f in files:
            report = analyzer.analyze_file(f)
            reports.append(report)

    # Résumé final
    print("\n" + "=" * 60)
    print("📊 RÉSUMÉ FINAL")
    print("=" * 60)
    print(engine.get_profile().summary())

    # Rapport JSON
    if args.report:
        report_path = Path(args.report)
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(reports, f, ensure_ascii=False, indent=2)
        print(f"\n📄 Rapport sauvegardé : {report_path}")

    print("\n✅ Import terminé !")
    print("→ Lance maintenant le backend : python backend/main.py")


def _print_export_guide():
    print("""
╔══════════════════════════════════════════════════════════╗
║            GUIDE D'EXPORT DES CONVERSATIONS              ║
╠══════════════════════════════════════════════════════════╣
║  WHATSAPP                                                ║
║  1. Ouvre une conversation                               ║
║  2. ⋮ Menu → Plus → Exporter la discussion               ║
║  3. Choisir "Sans médias"                                ║
║  4. Envoie-toi le fichier .txt                           ║
║  5. Place-le dans data/raw_conversations/                ║
╠══════════════════════════════════════════════════════════╣
║  TELEGRAM                                                ║
║  1. Paramètres → Avancés → Exporter les données          ║
║  2. Sélectionne "Messages" en JSON                        ║
║  3. Place result.json dans data/raw_conversations/       ║
╠══════════════════════════════════════════════════════════╣
║  INSTAGRAM                                               ║
║  1. Paramètres → Sécurité → Données & accès              ║
║  2. Télécharger tes données → Messages → JSON             ║
║  3. Place messages/inbox/*/message_1.json dans           ║
║     data/raw_conversations/                              ║
╚══════════════════════════════════════════════════════════╝
""")


if __name__ == "__main__":
    main()
