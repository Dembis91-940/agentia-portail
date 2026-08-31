# Agentia — Portail Client V6 (graphiques + sécurité prod)

Portail client multi-business (Agentia, SkillVault, **ProdIA**, **AvisBoost**, + futurs) **prêt à la vente** :
le client voit la valeur du Concierge IA en chiffres — heures récupérées, € économisés,
ROI, statuts — avec des graphiques alimentés par les **vraies données** de la base
(zéro simulateur).

- Backend : FastAPI + SQLite (auth JWT, argon2, anti brute-force)
- Frontend : une seule page HTML (style V5 : grain, halos, curseur) + Chart.js
- Sécurité : `SECRET_KEY` en variable d'env, CORS restreint, rate-limit login, headers

---

## Démarrage (local, 1 serveur = 1 URL)

```bash
cd ~/Documents/livrables/agentia-ia/portail
.venv/bin/python main.py          # → http://127.0.0.1:8000  (frontend + API + assets)
```

Au premier lancement :
1. les tables sont créées (`portail_multi.db`) ;
2. le client démo Agentia est seedé (6 automatisations + 10 semaines d'événements) ;
3. un `.env` est généré avec un `PORTAIL_JWT_SECRET` aléatoire (jamais en dur).

Le `.env` et la base `*.db` sont dans `.gitignore` — **aucun secret ni donnée dans le repo**.

### Comptes démo (local uniquement — à supprimer/renommer en production)

| Rôle | Email | Mot de passe |
|---|---|---|
| Client démo Agentia (graphiques) | `client@boulangerie-martin.fr` | `client1234` |
| Admin Agentia | `demba@agentia.admin` | `Demba2026!` |
| Client SkillVault (packs) | `karim@menuiserie-diallo.fr` | `motdepasse123` |
| Client démo ProdIA (audits) | `sophie@atelier-dupont.fr` | `client1234` |
| Client démo AvisBoost (avis) | `claire@salon-lumiere.fr` | `client1234` |

> ⚠️ Comptes de démonstration : changez-les (ou `PORTAIL_SEED_DEMO=0`) avant toute mise en production.
> Le mot de passe démo du seed est configurable via `PORTAIL_DEMO_PASSWORD`.

---

## Données & graphiques (V6)

### Modèle étendu
- `automations` : + `date_livraison`, `heures_gagnees_mensuelles` — statuts `active | maintenance | pause`
- `automation_events` : historique **hebdomadaire** (date, heures_gagnees) → source des courbes
- `businesses` : + `taux_horaire` (défaut 35 €/h, configurable par business)

### API `GET /api/dashboard` → `charts`
| Champ | Description |
|---|---|
| `hours_by_week[]` | heures gagnées par semaine (10 dernières semaines) |
| `hours_cumulative[]` | cumul (la courbe qui monte) |
| `hours_total` | total sur la fenêtre |
| `euros_saved` / `euros_saved_month` | heures × taux horaire (total / mois courant) |
| `roi` | € économisés mensuels ÷ `client_profiles.montant_mensuel` |
| `pct_temps_gagne` | heures mensuelles ÷ ~160 h travaillées |
| `automation_status_counts` | active / maintenance / pause |

### Frontend
- **Aire** : heures récupérées cumulées (argument de vente n°1)
- **Barres** : heures par semaine
- **KPI animés** : € économisés/mois · ROI × · heures récupérées · % temps gagné
- **Donut** : statut des automatisations
- Filtre de période **7 j / 30 j / 90 j** (recoupe les semaines chargées depuis l'API)
- Chart.js est **vendu localement** (`assets/chart.umd.min.js`) → zéro dépendance CDN, fonctionne hors-ligne

---

## Sécurité (durcie — prêt prod)

| Mesure | Détail |
|---|---|
| `SECRET_KEY` | `PORTAIL_JWT_SECRET` via env ou `.env` auto-généré au 1er lancement. Jamais en dur. |
| Mots de passe | argon2 (`pwdlib`) |
| CORS | `PORTAIL_ALLOW_ORIGINS` (défaut `http://127.0.0.1:8000,http://localhost:8000`) |
| Anti brute-force | 5 échecs / 15 min par IP+email → HTTP 429 |
| Headers | `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy` |
| Secrets | `.env`, `*.db` dans `.gitignore` — aucun secret dans le code ni le repo |

> Note : le rate-limit est en mémoire (valable pour 1 process). En multi-worker,
> remplacez `LOGIN_FAILURES` par Redis (ou le store de votre plateforme).

### HTTPS & déploiement

**HTTPS est obligatoire dès qu'il y a un domaine public.** Les cookies/JWT transitent
sinon en clair.

- **Railway / Render (recommandé pour démarrer)**
  1. `git push` du repo `agentia-portail`
  2. Build : `pip install -r requirements.txt` ; Start : `uvicorn main:app --host 0.0.0.0 --port $PORT`
  3. Variables d'env : `PORTAIL_JWT_SECRET=<valeur aléatoire forte>`, `PORTAIL_ALLOW_ORIGINS=https://votre-domaine.fr`, `PORTAIL_SEED_DEMO=0`
  4. HTTPS : activé automatiquement par la plateforme (certificat Let's Encrypt géré)
- **VPS (Nginx + Caddy)**
  - Caddy (automatique) : `votre-domaine.fr { reverse_proxy 127.0.0.1:8000 }`
  - Nginx + certbot : proxy_pass vers `127.0.0.1:8000`, puis `certbot --nginx`
  - Ne jamais exposer le port 8000 directement sur Internet (reverse proxy uniquement)

**Fichier `requirements.txt`** (à installer dans le venv) :

```
fastapi
uvicorn
sqlalchemy
python-jose
pwdlib[argon2]
python-multipart
python-dotenv
email-validator
```

---

## Publication

Le portail vit dans son **repo dédié `agentia-portail`** (choix : le repo `agentia`
contient le site vitrine avec des changements en cours ; isoler le portail évite tout
risque de casser le site et donne un cycle de vie propre au produit).

- Repo : `https://github.com/Dembis91-940/agentia-portail`
- Capture dashboard (pour la vente) : `screenshots/dashboard-v6.png`
- Capture ProdIA (pour la vente) : `screenshots/evolution-score.png`

---

## ProdIA — suivi mensuel du score / gains / ROI (module `audits`)

ProdIA est un **3ᵉ business du portail** (couleur or `#d4a017`, module `audits`) :
le client remplit l'audit (outil connecté), enregistre sa snapshot, et le portail
lui affiche sa **courbe d'évolution réelle** — le suivi mensuel promis par l'offre Pro.

### Modèle
- `audit_snapshots` : `user_id, site_name (multi-sites), date, score_global, score_axes (JSON),
  gains_annuels_euros, cout_outils_annuel, roi, plan_action (JSON 30-60-90), formule`
- Table créée automatiquement au lancement (`Base.metadata.create_all`).

### API
| Endpoint | Description |
|---|---|
| `POST /api/audits` | Enregistre un audit (body : `site_name, date?, score_global, score_axes, gains_annuels_euros, cout_outils_annuel, roi, plan_action, formule`) — réservé aux espaces avec le module `audits` (403 sinon) |
| `GET /api/audits` | Liste des audits du client (du plus récent au plus ancien) |
| `GET /api/audits/history?site=` | Séries temporelles pour les graphiques : labels, scores, gains, rois, deltas, sites distincts, dernier/précédent |
| `GET /api/dashboard` | Renvoie aussi `audits` + `audits_history` quand le business a le module `audits` |

### Outil d'audit connecté
- `prodia/outil-audit.html` (copie connectée de l'outil ProdIA) servi sur **`/audit`**,
  assets sur `/audit-assets` — **même origine que le portail** : le token JWT
  (`localStorage.portail_token`) est partagé, zéro CORS.
- Si un token est présent, l'outil affiche **« Enregistrer dans mon espace »** après le score
  (sinon, formulaire EmailJS inchangé pour les visiteurs).
- `POST /api/audits` reçoit le score, les axes, les gains, le coût, le ROI et le plan 30-60-90
  réellement calculés par l'outil → la courbe du portail est mise à jour.

### Multi-sites (Business 69 €)
- Chaque audit a un `site_name` ; `GET /api/audits/history?site=X` filtre par site.
- Le portail affiche un **sélecteur de site** (Tous les sites / site A / site B) qui
  recharge les séries depuis l'API (données réelles, pas de filtre côté client).

### Offres 19 / 39 / 69 €
- Bloc d'offres affiché dans l'espace ProdIA (Starter 19 € · Pro 39 € ⭐ · Business 69 €,
  essai 14 jours) — **prêt pour Stripe Billing** mais **pas activé** (feu vert requis).
- Le bouton « Choisir » ouvre un rappel de contact (`prodia.audit@gmail.com`) — aucun paiement
  en ligne tant que le feu vert Stripe n'est pas donné.

---

## AvisBoost — relances SMS/WhatsApp + avis Google (module `avis`)

AvisBoost est un **4ᵉ business du portail** (couleur lagune `#22d3ee`, module `avis`) :
le client gère ses **avis Google**, ses **relances automatiques J+2 / J+5 / J+9**
(SMS/WhatsApp) et ses **réponses IA** — tout le backend réel, avec les fournisseurs
externes en **mode test journalisé** tant que les credentials ne sont pas fournis.

### Modèle (tables créées au lancement)
| Table | Rôle |
|---|---|
| `locations` | Emplacements du commerce (nom, adresse, google_place_id, qr_url) |
| `visits` | Visite client (location, nom, téléphone, date, canal) → déclenche les relances |
| `reminders` | Relance planifiée (visit, canal sms/whatsapp, J+2/J+5/J+9, statut, envoyee_le, log) |
| `reviews` | Avis (location, note 1-5, texte, date, repondu_le, reponse) |

### API
| Endpoint | Description |
|---|---|
| `GET/POST /api/avisboost/locations` · `DELETE …/{id}` | CRUD emplacements |
| `GET/POST /api/avisboost/visits` · `DELETE …/{id}` | CRUD visites — **la création planifie automatiquement J+2/J+5/J+9** |
| `GET/POST /api/avisboost/reviews` · `DELETE …/{id}` | CRUD avis |
| `POST /api/avisboost/reviews/{id}/respond` | Marque l'avis répondu (réponse réelle en base) |
| `POST /api/avisboost/reviews/{id}/suggest-reply` | Suggère une réponse : LLM réel si `LLM_API_KEY`, sinon template local |
| `POST /api/avisboost/reminders/plan` | (Re)planifie J+2/J+5/J+9 d'une visite |
| `GET /api/avisboost/reminders/due` | Relances dues (planifiée et date ≤ aujourd'hui) |
| `POST /api/avisboost/reminders/process` | Traite les dues via les adaptateurs (mode test = journalisation réelle) |
| `GET /api/avisboost/stats` | Taux de réponse, note moyenne, avis/mois, relances par statut |
| `GET /api/dashboard` | Renvoie aussi `avisboost` quand le business a le module `avis` |

Tous les endpoints sont **protégés par module** : un client sans le module `avis` reçoit 403.

### Adaptateurs fournisseurs (`adapters/`) — mode test par défaut
| Adaptateur | Mode réel (env) | Mode test (sans credentials) |
|---|---|---|
| `whatsapp_adapter.py` | Meta Cloud API (`META_PHONE_ID`, `META_TOKEN`) → `graph.facebook.com/v20.0` | journalisation réelle dans `avisboost-test-journal.log` |
| `sms_adapter.py` | `SMS_PROVIDER=twilio\|brevo\|ovh` + variables `SMS_*` | idem |
| `google_reviews_adapter.py` | Google Business Profile (`GOOGLE_ACCESS_TOKEN`, `GOOGLE_LOCATION_ID`) | idem |
| `ia_reviews.py` | LLM compatible OpenAI (`LLM_API_KEY`, option `LLM_MODEL`) | template local réel (version de base documentée) |

> **Garde-fou zéro simulateur** : le mode test **n'envoie jamais rien** — chaque tentative
> est journalisée (fichier horodaté, gitignoré, contient les numéros = PII locale) et
> affichée dans l'onglet Relances. Le statut passe à « Envoyée (test journalisé) ».

### Dashboard (3 onglets)
- **Mes avis** : liste des avis (étoiles, emplacement, badge Répondu/En attente), bouton
  « Répondre » avec suggestion IA, taux de réponse.
- **Relances** : timeline par client J+2/J+5/J+9 avec statuts (Planifiée / Envoyée test / Échouée)
  + bouton « ✈ Envoyer les relances dues » (process mode test).
- **Statistiques** : barres avis/mois, donut notes, donut statut relances, indicateurs
  (Chart.js local, zéro CDN).

### Offres 29 / 49 / 149 €
- Starter 29 €/mois · Pro 49 €/mois ⭐ (formule actuelle du client démo) · Setup unique 149 €.
- Bloc affiché dans l'espace AvisBoost — **prêt pour Stripe Billing** mais **pas activé**
  (feu vert requis). Bouton « Choisir » → rappel contact (`agentiadeploiement@gmail.com`).

### Procédure d'activation des fournisseurs (actions humaines — mode réel)
1. **WhatsApp (Meta Cloud API)** : créer un compte **Meta WhatsApp Business**, obtenir un
   numéro de téléphone API (validation Meta : nom d'affichage, cas d'usage, politique de
   confidentialité), générer un **jeton d'accès système** → poser `META_PHONE_ID` et
   `META_TOKEN` dans l'env du serveur.
2. **SMS France (Twilio/Brevo/OVH)** : s'abonner chez le fournisseur (conformité : mention
   STOP, consentement client, expéditeur identifié) → poser `SMS_PROVIDER` + `SMS_*` dans l'env.
3. **Google Business Profile** : créer un **projet Google Cloud**, activer l'API Business
   Profile, obtenir les identifiants OAuth 2.0 + consentement du propriétaire de la fiche
   (vérification Google) → poser `GOOGLE_ACCESS_TOKEN` / `GOOGLE_LOCATION_ID` dans l'env.
4. **Réponses IA** : clé d'un LLM compatible OpenAI (OpenAI/Mistral/OpenRouter…) → poser
   `LLM_API_KEY` (option `LLM_MODEL`). Sans clé : template local de base, documenté.
5. **Paiement** : activer Stripe Billing uniquement après feu vert utilisateur (mission dédiée).

### Captures (vente)
- `screenshots/avisboost-avis.png` — onglet Mes avis (KPI + avis + offres)
- `screenshots/avisboost-relances.png` — timeline des relances J+2/J+5/J+9
- `screenshots/avisboost-stats.png` — courbe avis/mois + donuts + indicateurs

## Tests

```bash
.venv/bin/python tests/test_api_v6.py          # login démo + dashboard + croisement SQLite (Agentia)
.venv/bin/python tests/test_api_audits.py      # ProdIA : audits, history, POST réel, sécurité 403, non-régression
.venv/bin/python tests/test_api_avisboost.py   # AvisBoost : visites → relances J+2/J+5/J+9 → process mode test (journal réel) → avis → stats
```

Vérifié en conditions réelles (navigateur) : login démo, 4 graphiques rendus avec les
données de la base, filtre 7/30/90 j, 0 erreur console, rate-limit 5→429,
non-régression SkillVault + ProdIA. Pour ProdIA : outil connecté → 15 questions →
« Enregistrer dans mon espace » → POST réel → courbe d'évolution mise à jour
(vérifié en navigateur, données croisées avec SQLite). Pour AvisBoost : login démo
Claire, 3 onglets (Mes avis / Relances / Statistiques) alimentés par la base,
création de visite → planification J+2/J+5/J+9 réelle → process mode test → journal
`avisboost-test-journal.log` alimenté, réponse IA (template local) enregistrée en base,
taux de réponse recalculé, 0 erreur console.
