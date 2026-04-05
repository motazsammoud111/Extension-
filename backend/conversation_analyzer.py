"""
conversation_analyzer.py — Parseur multi-sources de conversations
Supporte : WhatsApp (.txt), Telegram (JSON), Instagram (JSON), Messenger (JSON)
Retourne désormais aussi les messages bruts pour stockage en base.
"""

import json
import re
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict, Tuple

from personality_engine import PersonalityEngine


# ─────────────────────────────────────────────────────────────
# Structures de données
# ─────────────────────────────────────────────────────────────

class Message:
    def __init__(self, sender: str, text: str, timestamp: str, source: str):
        self.sender = sender
        self.text = text
        self.timestamp = timestamp   # ISO 8601
        self.source = source

    def to_dict(self) -> dict:
        return {
            "sender": self.sender,
            "text": self.text,
            "timestamp": self.timestamp,
            "source": self.source,
        }

    def __repr__(self):
        return f"[{self.timestamp[:16]}] {self.sender}: {self.text[:60]}"


# ─────────────────────────────────────────────────────────────
# Parseurs
# ─────────────────────────────────────────────────────────────

class WhatsAppParser:
    PATTERNS = [
        re.compile(r"^\[(\d{1,2}[/\-\.]\d{1,2}[/\-\.]\d{2,4}),?\s+(\d{1,2}:\d{2}(?::\d{2})?(?:\s?[AP]M)?)\]\s+([^:]+):\s(.+)$"),
        re.compile(r"^(\d{1,2}[/\-\.]\d{1,2}[/\-\.]\d{2,4}),\s+(\d{1,2}:\d{2}(?::\d{2})?(?:\s?[AP]M)?)\s+-\s+([^:]+):\s(.+)$"),
    ]
    SYSTEM_MESSAGES = {
        "messages and calls are end-to-end encrypted", "this message was deleted",
        "image omitted", "video omitted", "audio omitted", "document omitted",
        "sticker omitted", "gif omitted", "<media omitted>",
        "vous avez été ajouté", "a rejoint le groupe", "a quitté le groupe",
        "a modifié l'icône", "a changé",
    }

    def parse(self, file_path: Path, my_name: str) -> Tuple[List[Message], List[Message]]:
        all_msgs = []
        my_msgs = []
        with open(file_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        current_msg = None
        for line in lines:
            line = line.rstrip("\n")
            matched = False
            for pattern in self.PATTERNS:
                m = pattern.match(line)
                if m:
                    if current_msg:
                        msg = self._finalize(current_msg, my_name)
                        if msg:
                            all_msgs.append(msg)
                            if msg.sender.lower() == my_name.lower():
                                my_msgs.append(msg)
                    date_str, time_str, sender, text = m.groups()
                    current_msg = {"date": date_str, "time": time_str, "sender": sender.strip(), "text": text.strip()}
                    matched = True
                    break
            if not matched and current_msg:
                current_msg["text"] += "\n" + line.strip()
        if current_msg:
            msg = self._finalize(current_msg, my_name)
            if msg:
                all_msgs.append(msg)
                if msg.sender.lower() == my_name.lower():
                    my_msgs.append(msg)
        return my_msgs, all_msgs

    def _finalize(self, raw: dict, my_name: str) -> Optional[Message]:
        text = raw["text"].strip()
        if any(s in text.lower() for s in self.SYSTEM_MESSAGES) or not text:
            return None
        ts = self._parse_timestamp(raw["date"], raw["time"])
        return Message(sender=raw["sender"], text=text, timestamp=ts, source="whatsapp")

    @staticmethod
    def _parse_timestamp(date_str: str, time_str: str) -> str:
        date_str = re.sub(r"[.\-]", "/", date_str)
        time_str = time_str.strip()
        formats = ["%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M", "%d/%m/%y %H:%M:%S", "%d/%m/%y %H:%M",
                   "%m/%d/%Y %I:%M:%S %p", "%m/%d/%Y %I:%M %p", "%m/%d/%y %I:%M:%S %p", "%m/%d/%y %I:%M %p"]
        combined = f"{date_str} {time_str}"
        for fmt in formats:
            try:
                return datetime.strptime(combined, fmt).isoformat()
            except ValueError:
                continue
        return datetime.now().isoformat()


class TelegramParser:
    def parse(self, file_path: Path, my_name: str) -> Tuple[List[Message], List[Message]]:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        messages = data.get("messages", [])
        all_msgs = []
        my_msgs = []
        for m in messages:
            if m.get("type") != "message":
                continue
            sender = m.get("from", "") or m.get("actor", "")
            date = m.get("date", "")
            text_raw = m.get("text", "")
            if isinstance(text_raw, list):
                text = "".join(seg if isinstance(seg, str) else seg.get("text", "") for seg in text_raw)
            else:
                text = str(text_raw)
            text = text.strip()
            if not text:
                continue
            msg = Message(sender=sender, text=text, timestamp=date, source="telegram")
            all_msgs.append(msg)
            if sender.lower() == my_name.lower():
                my_msgs.append(msg)
        return my_msgs, all_msgs


class InstagramParser:
    def parse(self, file_path: Path, my_name: str) -> Tuple[List[Message], List[Message]]:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        messages = data.get("messages", [])
        all_msgs = []
        my_msgs = []
        for m in messages:
            sender = m.get("sender_name", "")
            content = m.get("content", "").strip()
            ts_ms = m.get("timestamp_ms", 0)
            if not content:
                continue
            if content in {"Vous avez envoyé une photo.", "You sent a photo.",
                           "Vous avez envoyé une vidéo.", "You sent a video."}:
                continue
            ts = datetime.fromtimestamp(ts_ms / 1000).isoformat() if ts_ms else ""
            try:
                sender = sender.encode("latin1").decode("utf-8")
                content = content.encode("latin1").decode("utf-8")
            except Exception:
                pass
            msg = Message(sender=sender, text=content, timestamp=ts, source="instagram")
            all_msgs.append(msg)
            if sender.lower() == my_name.lower():
                my_msgs.append(msg)
        return my_msgs, all_msgs


class MessengerParser:
    """Parse les exports Facebook Messenger (message_1.json)."""
    def parse(self, file_path: Path, my_name: str) -> Tuple[List[Message], List[Message]]:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        all_msgs = []
        my_msgs = []
        for m in data.get("messages", []):
            sender = m.get("sender_name", "")
            if not sender or "Messages" in m.get("content", ""):
                continue
            content = m.get("content", "").strip()
            if not content:
                continue
            ts_ms = m.get("timestamp_ms", 0)
            ts = datetime.fromtimestamp(ts_ms / 1000).isoformat() if ts_ms else ""
            msg = Message(sender=sender, text=content, timestamp=ts, source="messenger")
            all_msgs.append(msg)
            if sender.lower() == my_name.lower():
                my_msgs.append(msg)
        return my_msgs, all_msgs


# ─────────────────────────────────────────────────────────────
# ConversationAnalyzer — orchestrateur principal
# ─────────────────────────────────────────────────────────────

class ConversationAnalyzer:
    def __init__(self, my_name: str, engine: Optional[PersonalityEngine] = None):
        self.my_name = my_name
        self.engine = engine or PersonalityEngine()
        self.wa_parser = WhatsAppParser()
        self.tg_parser = TelegramParser()
        self.ig_parser = InstagramParser()
        self.messenger_parser = MessengerParser()

    def analyze_file(self, file_path: Path) -> Tuple[dict, List[dict], List[dict]]:
        """
        Analyse un fichier de conversation.
        Retourne (rapport, tous_les_messages_dict, mes_messages_dict)
        """
        file_path = Path(file_path)
        source = self._detect_source(file_path)
        print(f"\n📂 Analyse : {file_path.name}  [{source}]")
        my_msgs, all_msgs = self._parse(file_path, source)
        if not my_msgs:
            return {"error": f"Aucun message de '{self.my_name}' trouvé dans {file_path.name}"}, [], []
        # Mettre à jour le moteur de personnalité
        msgs_for_engine = [m.to_dict() for m in my_msgs]
        self.engine.ingest(msgs_for_engine, source=source)
        report = self._build_report(my_msgs, all_msgs, source, file_path)
        self._print_report(report)
        # Retourner les messages bruts pour stockage
        all_dicts = [m.to_dict() for m in all_msgs]
        my_dicts = [m.to_dict() for m in my_msgs]
        return report, all_dicts, my_dicts

    def analyze_folder(self, folder_path: Path) -> List[dict]:
        folder_path = Path(folder_path)
        reports = []
        for f in sorted(folder_path.iterdir()):
            if f.suffix.lower() in (".txt", ".json") and f.is_file():
                try:
                    report, _, _ = self.analyze_file(f)
                    reports.append(report)
                except Exception as e:
                    print(f"  ❌ Erreur sur {f.name}: {e}")
        return reports

    def _detect_source(self, file_path: Path) -> str:
        name = file_path.stem.lower()
        if "telegram" in name or "result" in name:
            return "telegram"
        if "instagram" in name:
            return "instagram"
        if "message_1" in name:
            return "messenger"
        return "whatsapp"

    def _parse(self, file_path: Path, source: str) -> Tuple[List[Message], List[Message]]:
        if source == "telegram":
            return self.tg_parser.parse(file_path, self.my_name)
        if source == "instagram":
            return self.ig_parser.parse(file_path, self.my_name)
        if source == "messenger":
            return self.messenger_parser.parse(file_path, self.my_name)
        return self.wa_parser.parse(file_path, self.my_name)

    def _build_report(self, my_msgs: List[Message], all_msgs: List[Message],
                      source: str, file_path: Path) -> dict:
        my_texts = [m.text for m in my_msgs]
        avg_len = sum(len(t.split()) for t in my_texts) / len(my_texts)
        interlocutors = list({m.sender for m in all_msgs if m.sender.lower() != self.my_name.lower()})
        hour_dist = {}
        for m in my_msgs:
            try:
                h = datetime.fromisoformat(m.timestamp).hour
                hour_dist[h] = hour_dist.get(h, 0) + 1
            except Exception:
                pass
        peak_hour = max(hour_dist, key=hour_dist.get) if hour_dist else None
        return {
            "file": file_path.name,
            "source": source,
            "total_messages": len(all_msgs),
            "my_messages": len(my_msgs),
            "participation_rate": round(len(my_msgs) / max(len(all_msgs), 1) * 100, 1),
            "avg_message_length_words": round(avg_len, 1),
            "interlocutors": interlocutors,
            "peak_hour": peak_hour,
            "date_range": {
                "from": min((m.timestamp for m in all_msgs if m.timestamp), default=""),
                "to": max((m.timestamp for m in all_msgs if m.timestamp), default=""),
            },
        }

    def _print_report(self, report: dict):
        if "error" in report:
            print(f"  ⚠️  {report['error']}")
            return
        print(f"  ✅ {report['my_messages']} / {report['total_messages']} messages "
              f"({report['participation_rate']}%)\n"
              f"  📏 Longueur moy : {report['avg_message_length_words']} mots\n"
              f"  👥 Interlocuteurs : {', '.join(report['interlocutors'][:5])}\n"
              f"  🕐 Heure de pointe : {report.get('peak_hour', '?')}h")


if __name__ == "__main__":
    import sys, os
    MY_NAME = os.getenv("MY_NAME", "Motaz")
    analyzer = ConversationAnalyzer(my_name=MY_NAME)
    if len(sys.argv) > 1:
        path = Path(sys.argv[1])
        if path.is_dir():
            analyzer.analyze_folder(path)
        else:
            analyzer.analyze_file(path)
    else:
        print("🔍 Aucun fichier fourni — mode démo")
        print("Usage : python conversation_analyzer.py <fichier_ou_dossier>")
    print("\n" + analyzer.engine.get_profile().summary())