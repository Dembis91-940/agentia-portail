"""
AvisBoost — adaptateurs fournisseurs (WhatsApp / SMS / Google / IA).

Règle d'or (garde-fou produit) : MODE TEST PAR DÉFAUT.
  - Sans credentials (env) : aucune requête externe, JAMAIS de faux envoi.
    Chaque tentative est JOURNALISÉE RÉELLEMENT (fichier avisboost-test-journal*.log,
    horodatée, avec le message exact qui serait parti) et renvoyée au portail
    qui l'affiche à l'utilisateur.
  - Avec credentials (env) : envoi/appel réel via l'API du fournisseur.

Chaque adaptateur expose une fonction simple `..._adapter.xxx(...) -> dict` :
  {"ok": bool, "mode": "test"|"reel", "detail": str}
"""
