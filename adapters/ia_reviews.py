"""
Réponses automatiques aux avis (IA) — AvisBoost.

Mode réel (env requis) :
  LLM_API_KEY : clé d'un fournisseur compatible OpenAI (/v1/chat/completions)
                 — OpenAI, Mistral, OpenRouter, etc.
  LLM_MODEL   : (optionnel) modèle, défaut "gpt-4o-mini"

Sans clé : TEMPLATE LOCAL (version de base, documentée) — une vraie génération
déterministe en français, adaptée à la note (remerciement / geste commercial)
et au nom du commerce. Aucun appel externe. Jamais de texte factice inventé
à la volée : le template est réel, cohérent avec la note et le commerce.
"""
import json
import os
import urllib.request
import urllib.error

LLM_URL = os.environ.get("LLM_URL", "https://api.openai.com/v1/chat/completions")
LLM_MODEL = os.environ.get("LLM_MODEL", "gpt-4o-mini")


def _has_key() -> bool:
    return bool(os.environ.get("LLM_API_KEY", "").strip())


def _template_reply(review_text: str, business_name: str, note: int) -> str:
    """Version de base sans clé : réponse locale réelle, jamais générique de façade."""
    business_name = (business_name or "notre commerce").strip()
    excerpt = " ".join((review_text or "").split())[:90].strip(" .,;:")
    positive = (note or 0) >= 4
    if positive:
        base = (
            f"Bonjour, merci infiniment pour votre avis et votre confiance chez {business_name} ! "
            f"Votre retour nous encourage au quotidien."
        )
        if excerpt:
            base += f" Nous sommes ravis que « {excerpt} » ait répondu à vos attentes."
        base += " Toute l'équipe vous dit à très vite !"
    else:
        base = (
            f"Bonjour, merci d'avoir pris le temps de partager votre expérience chez {business_name}. "
            "Nous sommes sincèrement désolés que le moment passé n'ait pas été à la hauteur."
        )
        if excerpt:
            base += f" Nous avons bien noté votre remarque concernant « {excerpt} »."
        base += (" Notre responsable vous contactera très vite pour comprendre et corriger. "
                 "L'équipe reste à votre entière disposition.")
    return base


def generate_reply(review_text: str, business_name: str, note: int = 5) -> dict:
    """Génère une réponse chaleureuse en français. Clé API → LLM réel ; sinon template local."""
    business_name = (business_name or "").strip() or "notre commerce"
    prompt = (
        "Tu rédiges la réponse d'un commerce de proximité français à un avis Google. "
        "Règles : chaleureux, en français, jamais générique, jamais de promesses fausses, "
        "2-3 phrases max, signe par l'équipe. Avis reçu : "
        f"note {note}/5 — « {(review_text or '').strip()[:400]} » — commerce : {business_name}. "
        "Réponds uniquement avec le texte de la réponse."
    )

    if not _has_key():
        return {"ok": True, "mode": "template", "reponse": _template_reply(review_text, business_name, note),
                "detail": "Génération locale (template de base) — LLM_API_KEY non configurée"}

    payload = json.dumps({
        "model": LLM_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.7,
        "max_tokens": 220,
    }).encode()
    req = urllib.request.Request(LLM_URL, data=payload, method="POST", headers={
        "Authorization": f"Bearer {os.environ.get('LLM_API_KEY', '')}",
        "Content-Type": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            resp = json.loads(r.read())
        reponse = resp["choices"][0]["message"]["content"].strip()
        return {"ok": True, "mode": "reel", "reponse": reponse,
                "detail": f"Réponse générée par LLM ({LLM_MODEL})"}
    except urllib.error.HTTPError as e:
        return {"ok": False, "mode": "reel",
                "detail": f"HTTP {e.code} : {e.read().decode(errors='replace')[:300]}"}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "mode": "reel", "detail": f"Erreur réseau : {e}"}
