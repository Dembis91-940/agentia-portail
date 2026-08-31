"""
Adaptateur SMS France — fournisseur au choix via env `SMS_PROVIDER`.

Mode réel (env requis) :
  SMS_PROVIDER = twilio | brevo | ovh
  Twilio : SMS_TWILIO_SID + SMS_TWILIO_TOKEN + SMS_TWILIO_FROM
  Brevo  : SMS_BREVO_KEY + SMS_BREVO_SENDER
  OVH    : SMS_OVH_APP_KEY + SMS_OVH_APP_SECRET + SMS_OVH_CONSUMER_KEY + SMS_OVH_SERVICE + SMS_OVH_SENDER

Sans `SMS_PROVIDER` : MODE TEST — journalisation réelle uniquement.
Conformité France (documentée, à appliquer au contenu réel) : mention STOP,
consentement client, expéditeur identifié.
"""
import base64
import hashlib
import json
import os
import time
import urllib.parse
import urllib.request
import urllib.error

from .journal import journal

OVH_API = "https://eu.api.ovh.com/1.0"


def _sms_provider() -> str:
    return os.environ.get("SMS_PROVIDER", "").strip().lower()


def _send_twilio(to: str, message: str) -> dict:
    sid = os.environ.get("SMS_TWILIO_SID", "").strip()
    token = os.environ.get("SMS_TWILIO_TOKEN", "").strip()
    frm = os.environ.get("SMS_TWILIO_FROM", "").strip()
    if not (sid and token and frm):
        line = journal("sms", to, message, adapter="SMS-TWILIO",
                       extra="mode test (SMS_TWILIO_* incomplets)")
        return {"ok": True, "mode": "test", "detail": line}
    auth = base64.b64encode(f"{sid}:{token}".encode()).decode()
    body = urllib.parse.urlencode({"From": frm, "To": to, "Body": message}).encode()
    req = urllib.request.Request(
        f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json",
        data=body, method="POST",
        headers={"Authorization": f"Basic {auth}", "Content-Type": "application/x-www-form-urlencoded"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            resp = json.loads(r.read())
        return {"ok": True, "mode": "reel",
                "detail": f"Twilio SMS envoyé à {to} — sid {resp.get('sid', '?')} statut {resp.get('status', '?')}"}
    except urllib.error.HTTPError as e:
        return {"ok": False, "mode": "reel", "detail": f"HTTP {e.code} : {e.read().decode(errors='replace')[:300]}"}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "mode": "reel", "detail": f"Erreur réseau : {e}"}


def _send_brevo(to: str, message: str) -> dict:
    key = os.environ.get("SMS_BREVO_KEY", "").strip()
    sender = os.environ.get("SMS_BREVO_SENDER", "").strip()
    if not (key and sender):
        line = journal("sms", to, message, adapter="SMS-BREVO",
                       extra="mode test (SMS_BREVO_* incomplets)")
        return {"ok": True, "mode": "test", "detail": line}
    payload = json.dumps({"type": "transactional", "sender": sender,
                          "recipient": to, "content": message}).encode()
    req = urllib.request.Request(
        "https://api.brevo.com/v3/transactionalSMS/sms", data=payload, method="POST",
        headers={"api-key": key, "Content-Type": "application/json", "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            resp = json.loads(r.read())
        return {"ok": True, "mode": "reel",
                "detail": f"Brevo SMS envoyé à {to} — id {resp.get('messageId', '?')}"}
    except urllib.error.HTTPError as e:
        return {"ok": False, "mode": "reel", "detail": f"HTTP {e.code} : {e.read().decode(errors='replace')[:300]}"}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "mode": "reel", "detail": f"Erreur réseau : {e}"}


def _ovh_sign(method: str, url: str, body: str):
    """Signature OVH : SHA1('{AS}+{APP}+{TS}+{SECRET}+{METHOD}+{URL}+{BODY}')."""
    app_secret = os.environ.get("SMS_OVH_APP_SECRET", "")
    timestamp = str(int(time.time()))
    to_hash = f"{os.environ.get('SMS_OVH_APP_KEY', '')}+{app_secret}+{timestamp}+{method}+{url}+{body}"
    return "$1$" + hashlib.sha1(to_hash.encode()).hexdigest(), timestamp


def _send_ovh(to: str, message: str) -> dict:
    app_key = os.environ.get("SMS_OVH_APP_KEY", "").strip()
    consumer = os.environ.get("SMS_OVH_CONSUMER_KEY", "").strip()
    service = os.environ.get("SMS_OVH_SERVICE", "").strip()
    sender = os.environ.get("SMS_OVH_SENDER", "").strip()
    if not (app_key and consumer and service and sender):
        line = journal("sms", to, message, adapter="SMS-OVH",
                       extra="mode test (SMS_OVH_* incomplets)")
        return {"ok": True, "mode": "test", "detail": line}
    url = f"{OVH_API}/sms/{service}/jobs"
    body = json.dumps({"receivers": [to], "message": message, "sender": sender,
                       "priority": "high", "noStopClause": False})
    signature, timestamp = _ovh_sign("POST", url, body)
    req = urllib.request.Request(url, data=body.encode(), method="POST", headers={
        "X-Ovh-Application": app_key,
        "X-Ovh-Consumer": consumer,
        "X-Ovh-Timestamp": timestamp,
        "X-Ovh-Signature": signature,
        "Content-Type": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            resp = json.loads(r.read())
        return {"ok": True, "mode": "reel",
                "detail": f"OVH SMS envoyé à {to} — ids {resp.get('ids', [])}"}
    except urllib.error.HTTPError as e:
        return {"ok": False, "mode": "reel", "detail": f"HTTP {e.code} : {e.read().decode(errors='replace')[:300]}"}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "mode": "reel", "detail": f"Erreur réseau : {e}"}


def send_sms(to: str, message: str) -> dict:
    """Envoie un SMS via le fournisseur configuré (sinon mode test journalisé)."""
    provider = _sms_provider()
    if provider == "twilio":
        return _send_twilio(to, message)
    if provider == "brevo":
        return _send_brevo(to, message)
    if provider == "ovh":
        return _send_ovh(to, message)
    line = journal("sms", to, message, adapter="SMS",
                   extra="mode test (SMS_PROVIDER absent ou inconnu — twilio|brevo|ovh attendu)")
    return {"ok": True, "mode": "test", "detail": line}
