"""
Adaptateur WhatsApp — Meta Cloud API (graph.facebook.com).

Mode réel (env requis) :
  META_PHONE_ID : identifiant du numéro de téléphone API (WhatsApp Business)
  META_TOKEN    : jeton d'accès système (Meta Business)

Sans ces deux variables : MODE TEST — journalisation réelle uniquement
(voir adapters/journal.py), aucune requête vers Meta.
"""
import json
import os
import urllib.request
import urllib.error

from .journal import journal

GRAPH_VERSION = "v20.0"


def _creds() -> tuple:
    return os.environ.get("META_PHONE_ID", "").strip(), os.environ.get("META_TOKEN", "").strip()


def send_whatsapp(to: str, message: str) -> dict:
    """Envoie un message WhatsApp (mode réel si credentials, sinon mode test journalisé)."""
    phone_id, token = _creds()
    if not phone_id or not token:
        line = journal("whatsapp", to, message, adapter="WHATSAPP",
                       extra="mode test (META_PHONE_ID/META_TOKEN absents)")
        return {"ok": True, "mode": "test", "detail": line}

    url = f"https://graph.facebook.com/{GRAPH_VERSION}/{phone_id}/messages"
    payload = json.dumps({
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": message},
    }).encode()
    req = urllib.request.Request(url, data=payload, method="POST", headers={
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            body = json.loads(r.read())
        line = f"[{GRAPH_VERSION}] WhatsApp envoyé à {to} — message id {body.get('messages', [{}])[0].get('id', '?')}"
        return {"ok": True, "mode": "reel", "detail": line}
    except urllib.error.HTTPError as e:
        detail = f"HTTP {e.code} : {e.read().decode(errors='replace')[:300]}"
        return {"ok": False, "mode": "reel", "detail": detail}
    except Exception as e:  # noqa: BLE001 — réseau
        return {"ok": False, "mode": "reel", "detail": f"Erreur réseau : {e}"}
