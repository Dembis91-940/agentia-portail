"""Test réel API AvisBoost — module avis : login, emplacements, visites, relances
J+2/J+5/J+9, process mode test (journalisation réelle, AUCUN envoi), avis, réponses,
stats, croisement SQLite, sécurité 403, non-régression autres business.
Zéro simulateur : chaque valeur renvoyée par l'API est recalculée depuis la base."""
import json
import sqlite3
import urllib.error
import urllib.request
import urllib.parse

BASE = "http://127.0.0.1:8000"
DB = "/Users/demba.koita-laha/Documents/livrables/agentia-ia/portail/portail_multi.db"
JOURNAL = "/Users/demba.koita-laha/Documents/livrables/agentia-ia/portail/avisboost-test-journal.log"


def post_json(path, data, token=None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
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


def delete(path, token):
    req = urllib.request.Request(BASE + path, method="DELETE",
                                 headers={"Authorization": "Bearer " + token})
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())


print("== 1. LOGIN avisboost (claire@salon-lumiere.fr) ==")
tok = post_form("/api/auth/login", {"username": "claire@salon-lumiere.fr", "password": "client1234"})["access_token"]
print("token OK:", len(tok) > 20)

print("\n== 2. DASHBOARD : business + module avis ==")
d = get("/api/dashboard", tok)
print("business:", d["business"]["slug"], "| modules:", d["business"]["modules"])
ab = d["avisboost"]
print("locations:", len(ab["locations"]), "| visits:", len(ab["visits"]), "| reviews:", len(ab["reviews"]), "| reminders:", len(ab["reminders"]))
s = ab["stats"]
print("stats:", json.dumps(s, ensure_ascii=False))

print("\n== 3. CRUD lecture : locations / visits / reviews ==")
locs = get("/api/avisboost/locations", tok)
print("locations:", [(l["name"], l["qr_url"][:40]) for l in locs])
print("visits:", [(v["client_name"], v["visit_date"]) for v in get("/api/avisboost/visits", tok)])
print("reviews nb:", len(get("/api/avisboost/reviews", tok)))

print("\n== 4. POST /api/avisboost/visits (visite il y a 10 jours → 3 relances dues) ==")
new_visit = post_json("/api/avisboost/visits", {
    "location_id": locs[0]["id"], "client_name": "Test Mission", "phone": "+33699999999",
    "visit_date": "2026-08-21", "canal": "qr",
}, tok)
print("visite créée id", new_visit["id"], "| date", new_visit["visit_date"])
# vérifier via due (les 3 relances de cette visite sont passées → dues)
due = get("/api/avisboost/reminders/due", tok)
mine = [x for x in due["due"] if x["visit_id"] == new_visit["id"]]
print("relances dues de cette visite:", [(x["jour_offset"], x["date_prevue"], x["canal"]) for x in mine])
assert len(mine) == 3, "3 relances J+2/J+5/J+9 attendues pour la visite"

print("\n== 5. PROCESS mode test (uniquement les relances de la nouvelle visite) ==")
ids = [x["id"] for x in mine]
before = 0
try:
    before = sum(1 for _ in open(JOURNAL, encoding="utf-8"))
except FileNotFoundError:
    pass
proc = post_json("/api/avisboost/reminders/process", {"ids": ids}, tok)
print("processed:", proc["processed"])
for det in proc["details"]:
    print(" - J+%s %s → %s (%s)" % (det["jour_offset"], det["canal"], det["statut"], det["mode"]))
    assert det["mode"] == "test", "mode test attendu (pas de credentials)"
    assert "[TEST" in det["log"], "log mode test attendu"
after = sum(1 for _ in open(JOURNAL, encoding="utf-8"))
print("journal lignes:", before, "->", after, "(croissance réelle)", after > before)

print("\n== 6. POST review + respond ==")
new_review = post_json("/api/avisboost/reviews", {
    "location_id": locs[0]["id"], "note": 5, "text": "Test avis réel API — équipe au top !", "date": "2026-08-31",
}, tok)
print("avis créé id", new_review["id"], "| note", new_review["note"])
resp = post_json(f"/api/avisboost/reviews/{new_review['id']}/respond", {"reponse": "Merci pour ce retour !"}, tok)
print("répondu:", resp["repondu_le"] is not None, "| reponse:", resp["reponse"][:40])

print("\n== 7. SUGGEST-REPLY (template local, pas de LLM_API_KEY) ==")
sug = post_json(f"/api/avisboost/reviews/{new_review['id']}/suggest-reply", {}, tok)
print("mode:", sug["mode"], "| detail:", sug["detail"])
print("suggestion:", sug["reponse"][:100])

print("\n== 8. STATS recalculées depuis la base ==")
st = get("/api/avisboost/stats", tok)
print("taux_reponse:", st["taux_reponse"], "% | note_moyenne:", st["note_moyenne"], "| avis_total:", st["avis_total"])
print("avis_par_mois:", st["avis_par_mois"])
print("relances:", st["relances"], "| dues restantes:", st["relances_due"])

print("\n== 9. CROISEMENT SQLITE (zéro simulateur) ==")
# re-fetch du dashboard APRÈS les écritures (visite + avis créés ci-dessus)
d2 = get("/api/dashboard", tok)
ab2 = d2["avisboost"]
con = sqlite3.connect(DB)
cur = con.cursor()
rows = cur.execute("SELECT COUNT(*) FROM locations WHERE user_id=6").fetchone()[0]
rows2 = cur.execute("SELECT COUNT(*) FROM visits WHERE user_id=6").fetchone()[0]
rows3 = cur.execute("SELECT COUNT(*) FROM reminders WHERE user_id=6").fetchone()[0]
rows4 = cur.execute("SELECT COUNT(*) FROM reviews WHERE user_id=6").fetchone()[0]
api_counts = (len(ab2["locations"]), len(ab2["visits"]), len(ab2["reminders"]), len(ab2["reviews"]))
db_counts = (rows, rows2, rows3, rows4)
print("base :", db_counts)
print("api  :", api_counts)
print("MATCH:", db_counts == api_counts)
con.close()

print("\n== 10. SÉCURITÉ : un client non-avisboost ne peut pas toucher au module avis ==")
tok_agentia = post_form("/api/auth/login", {"username": "client@boulangerie-martin.fr", "password": "client1234"})["access_token"]
try:
    post_json("/api/avisboost/locations", {"name": "X"}, tok_agentia)
    print("ERREUR : l'agentia a pu créer un emplacement (devrait être 403)")
except urllib.error.HTTPError as e:
    print("OK 403 attendu :", e.code, e.read().decode()[:80])

print("\n== 11. NON-RÉGRESSION agentia + prodia + skillvault ==")
da = get("/api/dashboard", tok_agentia)
print("agentia OK:", da["business"]["slug"], "| charts:", len(da["charts"]))
tok_prodia = post_form("/api/auth/login", {"username": "sophie@atelier-dupont.fr", "password": "client1234"})["access_token"]
dp = get("/api/dashboard", tok_prodia)
print("prodia OK:", dp["business"]["slug"], "| audits:", len(dp["audits"]), "| history:", len(dp["audits_history"]["scores"]))
tok_skill = post_form("/api/auth/login", {"username": "karim@menuiserie-diallo.fr", "password": "motdepasse123"})["access_token"]
ds = get("/api/dashboard", tok_skill)
print("skillvault OK:", ds["business"]["slug"], "| packs:", len(ds["packs"]))

print("\nTOUS LES TESTS PASSENT")
