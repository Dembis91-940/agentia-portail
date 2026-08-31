"""Journal réel du mode test AvisBoost.

Le mode test n'envoie RIEN à l'extérieur : il écrit dans un fichier horodaté
(avisboost-test-journal*.log, gitignoré — contient des numéros de téléphone)
la ligne EXACTE qui serait partie en mode réel. Journalisation réelle,
zéro faux envoi, zéro simulacre.
"""
import os
from datetime import datetime, timezone

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JOURNAL_PATH = os.path.join(BASE_DIR, "avisboost-test-journal.log")


def journal(canal: str, to: str, message: str, adapter: str = "", extra: str = "") -> str:
    """Écrit une ligne de journal réelle et la renvoie (affichée au portail)."""
    line = (
        f"[{datetime.now(timezone.utc).isoformat(timespec='seconds')}] "
        f"[TEST-{adapter or canal.upper()}] {canal} -> {to} "
        f"| {extra} | message: {message}"
    )
    try:
        with open(JOURNAL_PATH, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass  # le portail reçoit quand même la ligne dans reminder.log
    return line
