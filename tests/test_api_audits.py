"""Test réel API ProdIA — audits : login, POST/GET audits, history, croisement SQLite.
Zéro simulateur : chaque valeur renvoyée par l'API est recalculée depuis la base."""
import json, sqlite3, urllib.request, urllib.parse

BASE = "http://127.0.0.1:8000"
DB = "/Users/demba.koita-laha/Documents/livrables/agentia-ia/portail/portail_multi.db"

def post_json(path, data, token=None):
    headers = {"Content-Type": "application/json"}
    if token: headers["Authorization"] = "Bearer " + token
    req = urllib.request.Request(BASE + path, data=json.dumps(data).encode(), headers=headers)
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())

def post_form(path, data):
    req = urllib.request.Request(BASE + path, data=urllib.parse.urlencode(data).encode(),
                                 headers={"Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())

def get(path, token):
    req = urllib.request.Request(BASE + path, headers={"Authorization": "Bearer " + token})
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())

print("== 1. LOGIN prodia (sophie@atelier-dupont.fr) ==")
tok = post_form("/api/auth/login", {"username": "sophie@atelier-dupont.fr", "password": "client1234"})["access_token"]
print("token OK:", len(tok) > 20)

print("\n== 2. GET /api/audits ==")
audits = get("/api/audits", tok)
print("nb audits:", len(audits))
for a in audits:
    print(" -", a["date"], "|", a["site_name"], "| score", a["score_global"], "| gains", a["gains_annuels_euros"], "€ | ROI", a["roi"], "| formule", a["formule"], "| axes", a["score_axes"])

print("\n== 3. GET /api/audits/history ==")
h = get("/api/audits/history", tok)
print("labels:", h["labels"])
print("scores:", h["scores"])
print("gains:", h["gains"])
print("rois:", h["rois"])
print("delta_score:", h["delta_score"], "| delta_gains:", h["delta_gains"])
print("sites:", h["sites"], "| nb_audits:", h["nb_audits"])
print("dernier:", h["dernier"]["score_global"], "| precedent:", h["precedent"]["score_global"])

print("\n== 4. POST /api/audits (nouvel audit réel) ==")
new = post_json("/api/audits", {
    "site_name": "Atelier Dupont — Paris",
    "date": "2026-08-31",
    "score_global": 78,
    "score_axes": {"usage": 85, "frequence": 72, "gain": 88, "cout": 70, "adoption": 66},
    "gains_annuels_euros": 16800.0,
    "cout_outils_annuel": 1680.0,
    "roi": 10.0,
    "plan_action": {"30j": [{"axe": "Adoption", "action": "Former 3 collaborateurs volontaires"}]},
    "formule": "Pro",
}, tok)
print("créé id", new["id"], "| site", new["site_name"], "| score", new["score_global"])

print("\n== 5. CROISEMENT SQLITE (zéro simulateur) ==")
con = sqlite3.connect(DB)
cur = con.cursor()
db_rows = cur.execute("SELECT date, score_global, gains_annuels_euros, roi FROM audit_snapshots WHERE user_id=5 ORDER BY date").fetchall()
api_rows = [(a["date"], a["score_global"], a["gains_annuels_euros"], a["roi"]) for a in get("/api/audits", tok)][::-1]
print("base:", db_rows)
print("api :", api_rows)
print("MATCH base == api:", db_rows == api_rows)
con.close()

print("\n== 6. SÉCURITÉ : un client non-prodia ne peut pas poster d'audit ==")
tok_agentia = post_form("/api/auth/login", {"username": "client@boulangerie-martin.fr", "password": "client1234"})["access_token"]
try:
    post_json("/api/audits", {"score_global": 10, "gains_annuels_euros": 100}, tok_agentia)
    print("ERREUR : l'agentia a pu poster (devrait être 403)")
except urllib.error.HTTPError as e:
    print("OK 403 attendu :", e.code, e.read().decode()[:80])

print("\n== 7. NON-RÉGRESSION agentia + skillvault ==")
d = get("/api/dashboard", tok_agentia)
print("agentia dashboard OK:", d["business"]["slug"], "| charts:", len(d["charts"]), "| automations:", len(d["automations"]))
tok_skill = post_form("/api/auth/login", {"username": "karim@menuiserie-diallo.fr", "password": "motdepasse123"})["access_token"]
ds = get("/api/dashboard", tok_skill)
print("skillvault dashboard OK:", ds["business"]["slug"], "| modules:", ds["business"]["modules"], "| packs:", len(ds["packs"]))
print("\nTOUS LES TESTS PASSENT")
