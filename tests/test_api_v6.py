"""Test réel API V6 : login démo → /api/dashboard → vérification des graphiques
contre les valeurs directement calculées depuis la base SQLite."""
import json, sqlite3, os, urllib.request, urllib.parse

BASE = "http://127.0.0.1:8000"
DB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "portail_multi.db")

def post(path, data_urlencoded):
    req = urllib.request.Request(BASE + path, data=data_urlencoded.encode(),
                                 headers={"Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())

def get(path, token):
    req = urllib.request.Request(BASE + path, headers={"Authorization": "Bearer " + token})
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())

tok = post("/api/auth/login", urllib.parse.urlencode(
    {"username": "client@boulangerie-martin.fr", "password": "client1234"}))["access_token"]
d = get("/api/dashboard", tok)
ch = d["charts"]

print("== charts renvoyés ==")
print("hours_total:", ch["hours_total"])
print("hours_by_week:", [(h["label"], h["heures"]) for h in ch["hours_by_week"]])
print("hours_cumulative:", ch["hours_cumulative"])
print("euros_saved:", ch["euros_saved"], "| euros_saved_month:", ch["euros_saved_month"])
print("roi:", ch["roi"], "| pct_temps_gagne:", ch["pct_temps_gagne"], "| taux:", ch["taux_horaire"])
print("status_counts:", ch["automation_status_counts"])
print("nb automations:", len(d["automations"]), "| modules:", d["business"]["modules"])

# Vérification croisée : recalcul depuis SQLite
con = sqlite3.connect(DB)
cur = con.cursor()
db_sum = cur.execute("SELECT SUM(heures_gagnees) FROM automation_events WHERE user_id=4").fetchone()[0]
db_weeks = cur.execute("SELECT COUNT(DISTINCT date) FROM automation_events WHERE user_id=4").fetchone()[0]
db_status = dict(cur.execute("SELECT statut, COUNT(*) FROM automations WHERE user_id=4 GROUP BY statut").fetchall())
con.close()

assert abs(db_sum - ch["hours_total"]) < 0.01, f"total incohérent: db={db_sum} api={ch['hours_total']}"
assert db_weeks == 10, f"attendu 10 semaines, db={db_weeks}"
expected_status = {k: db_status.get(k, 0) for k in ("active", "maintenance", "pause")}
assert ch["automation_status_counts"] == expected_status, f"statuts incohérents: {ch['automation_status_counts']} vs {expected_status}"
print("\n✅ Vérifications croisées OK : graphiques = vraies données base (zéro simulateur)")
