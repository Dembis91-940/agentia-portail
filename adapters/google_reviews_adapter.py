"""
Adaptateur Google Business Profile (ex-Google My Business) — avis.

Mode réel (env requis) :
  GOOGLE_ACCESS_TOKEN : jeton OAuth 2.0 (projet Google Cloud, API Business Profile activée)
  GOOGLE_ACCOUNT_ID    : identifiant du compte (ex. "accounts/123456789")
  GOOGLE_LOCATION_ID   : identifiant de l'emplacement (ou via locations.google_place_id)

Sans credentials : MODE TEST — journalisation réelle uniquement.
La fiche Google doit être vérifiée et le propriétaire doit avoir consenti
(vérification Google) avant tout appel réel.
"""
import json
import os
import urllib.parse
import urllib.request
import urllib.error

from .journal import journal

GBP_API = "https://mybusiness.googleapis.com/v4"


def _token() -> str:
    return os.environ.get("GOOGLE_ACCESS_TOKEN", "").strip()


def fetch_reviews(location_id: str = "", place_id: str = "") -> dict:
    """Liste les avis Google d'un emplacement (mode réel si token, sinon mode test journalisé)."""
    token = _token()
    if not token:
        line = journal("google", f"location={location_id or place_id}", "",
                       adapter="GOOGLE-REVIEWS", extra="mode test (GOOGLE_ACCESS_TOKEN absent)")
        return {"ok": True, "mode": "test", "detail": line, "reviews": []}

    if not location_id:
        return {"ok": False, "mode": "reel",
                "detail": "GOOGLE_LOCATION_ID requis (ou renseignez locations.google_place_id)"}
    url = f"{GBP_API}/accounts/{{accountId}}/locations/{location_id}/reviews"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            resp = json.loads(r.read())
        return {"ok": True, "mode": "reel",
                "detail": f"{len(resp.get('reviews', []))} avis Google récupérés",
                "reviews": resp.get("reviews", [])}
    except urllib.error.HTTPError as e:
        return {"ok": False, "mode": "reel", "detail": f"HTTP {e.code} : {e.read().decode(errors='replace')[:300]}"}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "mode": "reel", "detail": f"Erreur réseau : {e}"}


def post_reply(review_id: str, reply_text: str, location_id: str = "") -> dict:
    """Publie une réponse à un avis Google (mode réel si token, sinon mode test journalisé)."""
    token = _token()
    if not token:
        line = journal("google", f"review={review_id}", reply_text,
                       adapter="GOOGLE-REPLY", extra="mode test (GOOGLE_ACCESS_TOKEN absent)")
        return {"ok": True, "mode": "test", "detail": line}

    if not location_id:
        return {"ok": False, "mode": "reel", "detail": "GOOGLE_LOCATION_ID requis"}
    url = f"{GBP_API}/accounts/{{accountId}}/locations/{location_id}/reviews/{review_id}:reply"
    payload = json.dumps({"comment": {"text": reply_text}}).encode()
    req = urllib.request.Request(url, data=payload, method="POST",
                                 headers={"Authorization": f"Bearer {token}",
                                          "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            resp = json.loads(r.read())
        return {"ok": True, "mode": "reel",
                "detail": f"Réponse publiée sur l'avis {review_id} (name {resp.get('name', '?')})"}
    except urllib.error.HTTPError as e:
        return {"ok": False, "mode": "reel", "detail": f"HTTP {e.code} : {e.read().decode(errors='replace')[:300]}"}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "mode": "reel", "detail": f"Erreur réseau : {e}"}
