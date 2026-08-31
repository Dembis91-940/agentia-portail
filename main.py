"""
Agentia/SkillVault — Portail Client Multi-Business (backend FastAPI) — V6
Vrai système : comptes, JWT, données par client, par business (Agentia, SkillVault, + futurs).
V6 : graphiques des automatisations (heures récupérées, € économisés, ROI, statuts) +
durcissement sécurité (SECRET_KEY env, CORS restreint, anti brute-force login).
Chaque business = son branding, ses modules, ses données. Zéro simulateur.
"""
import os
import json
import secrets
import sqlite3
import time
from collections import defaultdict, deque
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from dotenv import load_dotenv
from fastapi import FastAPI, Depends, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
from pwdlib import PasswordHash
from sqlalchemy import create_engine, Column, Integer, String, Float, Boolean, DateTime, Date, Text, ForeignKey
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from pydantic import BaseModel, EmailStr

# ---------------------------------------------------------------------------
# Configuration — sécurité : secret JAMAIS en dur (env ou .env auto-généré)
# ---------------------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "portail_multi.db")
DOTENV_PATH = os.path.join(BASE_DIR, ".env")
load_dotenv(DOTENV_PATH)

def _resolve_secret_key() -> str:
    """Secret JWT : 1) env PORTAIL_JWT_SECRET, 2) .env, 3) généré + persisté dans .env."""
    secret = os.environ.get("PORTAIL_JWT_SECRET") or os.environ.get("SECRET_KEY")
    if secret:
        return secret
    generated = secrets.token_hex(32)
    try:
        with open(DOTENV_PATH, "a") as f:
            f.write(f"\nPORTAIL_JWT_SECRET={generated}\n")
    except OSError:
        pass  # pas grave en dev : le secret vit en mémoire pour cette session
    return generated

SECRET_KEY = _resolve_secret_key()
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 12

# CORS restreint : domaine réel du portail, configurable via env (liste séparée par virgules)
ALLOWED_ORIGINS = [
    o.strip() for o in os.environ.get(
        "PORTAIL_ALLOW_ORIGINS",
        "http://127.0.0.1:8000,http://localhost:8000",
    ).split(",") if o.strip()
]

# Anti brute-force login : 5 essais / 15 min par IP+email (mémoire process ; en multi-worker → Redis)
RATE_LIMIT_MAX = 5
RATE_LIMIT_WINDOW_SECONDS = 15 * 60
LOGIN_FAILURES = defaultdict(deque)  # key "ip|email" -> deque[timestamps]

# Taux horaire par défaut pour le calcul des € économisés (configurable par business)
DEFAULT_TAUX_HORAIRE = 35.0
# Semaines d'historique renvoyées par le dashboard (8-12 semaines → 10)
DASHBOARD_WEEKS = 10

engine = create_engine(f"sqlite:///{DB_PATH}", connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine, autoflush=False)
Base = declarative_base()
password_hash = PasswordHash.recommended()

# ---------------------------------------------------------------------------
# Modèles
# ---------------------------------------------------------------------------
class Business(Base):
    """Un business du portefeuille (Agentia, SkillVault, futur...)."""
    __tablename__ = "businesses"
    id = Column(Integer, primary_key=True)
    slug = Column(String, unique=True, index=True, nullable=False)      # "agentia", "skillvault"
    name = Column(String, nullable=False)
    color = Column(String, default="#00ff88")                            # couleur néon du business
    modules = Column(String, default="")                                 # "automations,invoices" | "packs,invoices"
    description = Column(String, default="")
    taux_horaire = Column(Float, default=DEFAULT_TAUX_HORAIRE)           # €/h pour le calcul des économies
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    business_id = Column(Integer, ForeignKey("businesses.id"), nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    full_name = Column(String, nullable=False)
    company = Column(String, default="")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    is_admin = Column(Boolean, default=False)

class ClientProfile(Base):
    __tablename__ = "client_profiles"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True)
    statut = Column(String, default="demande")    # demande | en_cours | actif | abonne
    plan = Column(String, default="")
    montant_mensuel = Column(Float, default=0.0)
    temps_recupere_heures = Column(Float, default=0.0)
    notes = Column(Text, default="")

class Automation(Base):
    """Automatisation livrée. Statuts V6 : active | maintenance | pause."""
    __tablename__ = "automations"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    titre = Column(String, nullable=False)
    description = Column(Text, default="")
    statut = Column(String, default="active")
    heures_gagnees = Column(Float, default=0.0)                    # heures gagnées / semaine
    heures_gagnees_mensuelles = Column(Float, default=0.0)         # ≈ heures_gagnees × 4,33
    date_livraison = Column(Date, nullable=True)                  # quand l'auto est entrée en service
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

class AutomationEvent(Base):
    """Historique hebdomadaire des heures gagnées (source des courbes temporelles)."""
    __tablename__ = "automation_events"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    automation_id = Column(Integer, ForeignKey("automations.id"), nullable=True)
    date = Column(Date, index=True)                                # lundi de la semaine
    heures_gagnees = Column(Float, default=0.0)
    source = Column(String, default="manuel")                      # "manuel" | "seed"

class Invoice(Base):
    __tablename__ = "invoices"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    numero = Column(String, unique=True)
    montant = Column(Float, default=0.0)
    statut = Column(String, default="payee")
    date = Column(String, default="")

class Pack(Base):
    """Un pack SkillVault (29/89/197 €)."""
    __tablename__ = "packs"
    id = Column(Integer, primary_key=True)
    business_id = Column(Integer, ForeignKey("businesses.id"))
    name = Column(String, nullable=False)
    price = Column(Float, default=0.0)
    description = Column(Text, default="")
    skills = Column(Text, default="[]")           # JSON list of skill names

class Purchase(Base):
    """Achat d'un pack SkillVault par un client."""
    __tablename__ = "purchases"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    pack_id = Column(Integer, ForeignKey("packs.id"))
    pack_name = Column(String)
    montant = Column(Float, default=0.0)
    statut = Column(String, default="payee")
    date = Column(String, default="")
    skills = Column(Text, default="[]")           # snapshot des skills achetés

class AuditSnapshot(Base):
    """Un audit ProdIA enregistré : score /100, gains €, coût, ROI, plan 30-60-90,
    à une date donnée (base du suivi mensuel — offre Pro). Multi-sites : site_name."""
    __tablename__ = "audit_snapshots"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    site_name = Column(String, default="Site principal")
    date = Column(Date, default=date.today, index=True)
    score_global = Column(Integer, default=0)
    score_axes = Column(Text, default="{}")               # JSON {"usage": 55, "frequence": 66, ...}
    gains_annuels_euros = Column(Float, default=0.0)
    cout_outils_annuel = Column(Float, default=0.0)
    roi = Column(Float, default=0.0)
    plan_action = Column(Text, default="{}")              # JSON plan 30-60-90
    formule = Column(String, default="")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

Base.metadata.create_all(engine)

# ---------------------------------------------------------------------------
# Migrations idempotentes (SQLite : ajout de colonnes / tables sans casser les données)
# ---------------------------------------------------------------------------
def _migrate():
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cols = {t: {r[1] for r in cur.execute(f"PRAGMA table_info({t})").fetchall()} for t in
            ("businesses", "automations")}
    if "taux_horaire" not in cols["businesses"]:
        cur.execute("ALTER TABLE businesses ADD COLUMN taux_horaire FLOAT DEFAULT 35.0")
    if "heures_gagnees_mensuelles" not in cols["automations"]:
        cur.execute("ALTER TABLE automations ADD COLUMN heures_gagnees_mensuelles FLOAT DEFAULT 0.0")
    if "date_livraison" not in cols["automations"]:
        cur.execute("ALTER TABLE automations ADD COLUMN date_livraison DATE")
    # Normalisation des statuts V5 → V6 (live/en_cours/en_attente → active/pause)
    cur.execute("UPDATE automations SET statut='active' WHERE statut IN ('live','en_cours')")
    cur.execute("UPDATE automations SET statut='pause' WHERE statut IN ('en_attente')")
    con.commit()
    con.close()

_migrate()

# ---------------------------------------------------------------------------
# Seed de démo (idempotent — ne se relance pas si les événements existent déjà)
# ---------------------------------------------------------------------------
DEMO_EMAIL = "client@boulangerie-martin.fr"
DEMO_PASSWORD = os.environ.get("PORTAIL_DEMO_PASSWORD", "client1234")
DEMO_FULL_NAME = "Martin Dupont"
DEMO_COMPANY = "Boulangerie Martin"
DEMO_MONTANT_MENSUEL = 650.0

# (titre, description, statut, heures/semaine, livraison il y a N semaines)
DEMO_AUTOMATIONS = [
    ("Relance automatique des devis",
     "Relance des devis non signés après 48h, 7j et 14j — suivi sans intervention.",
     "active", 4.0, 12),
    ("Saisie des notes de frais",
     "OCR des tickets de caisse → export comptable structuré chaque semaine.",
     "active", 3.0, 12),
    ("Réponse aux demandes de contact",
     "Première réponse sous 2 min, 24/7, qualifiée par IA.",
     "active", 2.0, 12),
    ("Conciergerie réservations",
     "Réservations clients gérées de bout en bout : agenda, confirmations, rappels.",
     "active", 8.0, 4),
    ("Relances WhatsApp clients",
     "Campagnes de relance WhatsApp personnalisées : paniers abandonnés, fidélisation.",
     "active", 5.0, 7),
    ("Facturation automatique",
     "Génération et envoi des factures + relances de paiement automatiques.",
     "active", 3.0, 9),
]

def _monday_of(d: date) -> date:
    return d - timedelta(days=d.weekday())

def _seed_demo(db: Session):
    """Crée le client démo Agentia + 10 semaines d'événements réels en base.
    Idempotent : les automatisations sont mises à jour par titre (pas de doublons),
    et les événements ne sont créés qu'une seule fois (source="seed")."""
    business = db.query(Business).filter(Business.slug == "agentia").first()
    if not business:
        return
    if os.environ.get("PORTAIL_SEED_DEMO", "1") != "1":
        return
    user = db.query(User).filter(User.email == DEMO_EMAIL).first()
    if not user:
        user = User(email=DEMO_EMAIL, hashed_password=password_hash.hash(DEMO_PASSWORD),
                    full_name=DEMO_FULL_NAME, company=DEMO_COMPANY, business_id=business.id)
        db.add(user)
        db.flush()
        db.add(ClientProfile(user_id=user.id, statut="abonne", plan="Pro",
                             montant_mensuel=DEMO_MONTANT_MENSUEL, temps_recupere_heures=0.0))
        db.commit()

    # Mise à jour / création des automatisations par titre (jamais de doublon)
    today = _monday_of(date.today())
    existing_by_titre = {a.titre: a for a in
                         db.query(Automation).filter(Automation.user_id == user.id).all()}
    autos = []
    for titre, desc, statut, heures_sem, semaines_avant in DEMO_AUTOMATIONS:
        livraison = today - timedelta(weeks=semaines_avant)
        auto = existing_by_titre.get(titre)
        if auto:
            auto.description, auto.statut = desc, statut
            auto.heures_gagnees = heures_sem
            auto.heures_gagnees_mensuelles = round(heures_sem * 52 / 12, 1)
            auto.date_livraison = livraison
        else:
            auto = Automation(user_id=user.id, titre=titre, description=desc, statut=statut,
                              heures_gagnees=heures_sem,
                              heures_gagnees_mensuelles=round(heures_sem * 52 / 12, 1),
                              date_livraison=livraison)
            db.add(auto)
        autos.append((auto, livraison))
    db.commit()

    if db.query(AutomationEvent).filter(AutomationEvent.user_id == user.id).first():
        return  # événements déjà seedés

    # 10 semaines d'événements : chaque auto contribue à partir de sa livraison
    for semaine_offset in range(DASHBOARD_WEEKS - 1, -1, -1):
        week_start = today - timedelta(weeks=semaine_offset)
        for auto, livraison in autos:
            if livraison <= week_start:
                db.add(AutomationEvent(user_id=user.id, automation_id=auto.id,
                                       date=week_start, heures_gagnees=auto.heures_gagnees,
                                       source="seed"))
    db.commit()

PRODIA_COLOR = "#d4a017"
PRODIA_DEMO_EMAIL = "sophie@atelier-dupont.fr"
PRODIA_DEMO_PASSWORD = os.environ.get("PORTAIL_DEMO_PASSWORD", "client1234")
PRODIA_DEMO_FULL_NAME = "Sophie Dupont"
PRODIA_DEMO_COMPANY = "Atelier Dupont"

def _seed_prodia(db: Session):
    """Business ProdIA (audits, or #d4a017) + client démo avec 2 audits réels
    à des dates différentes → la courbe d'évolution affiche de vraies données.
    Idempotent : business par slug, user par email, audits seulement si aucun."""
    biz = db.query(Business).filter(Business.slug == "prodia").first()
    if not biz:
        biz = Business(slug="prodia", name="ProdIA", color=PRODIA_COLOR,
                       modules="audits,invoices",
                       description="Audit de productivité IA — score 0-100, gains €, ROI, plan 30-60-90.")
        db.add(biz)
        db.commit()
    if os.environ.get("PORTAIL_SEED_DEMO", "1") != "1":
        return
    user = db.query(User).filter(User.email == PRODIA_DEMO_EMAIL).first()
    if not user:
        user = User(email=PRODIA_DEMO_EMAIL, hashed_password=password_hash.hash(PRODIA_DEMO_PASSWORD),
                    full_name=PRODIA_DEMO_FULL_NAME, company=PRODIA_DEMO_COMPANY, business_id=biz.id)
        db.add(user)
        db.flush()
        db.commit()
    profil = db.query(ClientProfile).filter(ClientProfile.user_id == user.id).first()
    if not profil:
        db.add(ClientProfile(user_id=user.id, statut="abonne", plan="Pro", montant_mensuel=39.0))
        db.commit()
    elif profil.plan != "Pro":
        profil.statut, profil.plan, profil.montant_mensuel = "abonne", "Pro", 39.0
        db.commit()
    if db.query(AuditSnapshot).filter(AuditSnapshot.user_id == user.id).first():
        return  # audits déjà seedés

    today = date.today()
    prev = today - timedelta(days=30)
    db.add(AuditSnapshot(user_id=user.id, site_name="Atelier Dupont", date=prev, score_global=54,
                         score_axes='{"usage":55,"frequence":42,"gain":60,"cout":48,"adoption":33}',
                         gains_annuels_euros=8960.0, cout_outils_annuel=1440.0, roi=6.2,
                         plan_action='{"30j":["Cartographier les services IA payés","Désigner 2 tâches répétitives à confier à l\u2019IA"],"60j":["Étendre l\u2019IA à 2 nouvelles tâches récurrentes","Mettre en place un suivi simple du temps gagné"],"90j":["Consolider les gains par service","Fixer un objectif trimestriel de temps gagné"]}',
                         formule="Pro"))
    db.add(AuditSnapshot(user_id=user.id, site_name="Atelier Dupont", date=today, score_global=71,
                         score_axes='{"usage":78,"frequence":65,"gain":80,"cout":62,"adoption":55}',
                         gains_annuels_euros=14300.0, cout_outils_annuel=1560.0, roi=9.2,
                         plan_action='{"30j":["Vérifier qu\u2019aucune tâche répétitive ne passe à côté de l\u2019IA","Organiser un atelier mensuel d\u2019une heure"],"60j":["Doubler la fréquence des usages les plus rentables","Chiffrer le gain annuel si la fréquence doublait"],"90j":["Transformer le référent IA en mission officielle","Créer un comité IA trimestriel"]}',
                         formule="Pro"))
    db.commit()

def seed_if_needed():
    db = SessionLocal()
    try:
        _seed_demo(db)
        _seed_prodia(db)
    finally:
        db.close()

seed_if_needed()

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")

def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    credentials_exception = HTTPException(status_code=401, detail="Identifiants invalides", headers={"WWW-Authenticate": "Bearer"})
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("sub")
        if user_id is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    user = db.query(User).filter(User.id == int(user_id)).first()
    if user is None:
        raise credentials_exception
    return user

# ---------------------------------------------------------------------------
# Schémas
# ---------------------------------------------------------------------------
class RegisterIn(BaseModel):
    email: EmailStr
    password: str
    full_name: str
    company: str = ""
    business: str = "agentia"          # slug du business

class UserOut(BaseModel):
    id: int
    email: str
    full_name: str
    company: str
    is_admin: bool
    business: str

class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut

class PackOut(BaseModel):
    id: int
    name: str
    price: float
    description: str
    skills: list

class PurchaseOut(BaseModel):
    id: int
    pack_name: str
    montant: float
    statut: str
    date: str
    skills: list

class DashboardOut(BaseModel):
    user: UserOut
    business: dict
    profil: dict
    automations: list
    invoices: list
    packs: list
    purchases: list
    stats: dict
    charts: dict
    audits: list = []
    audits_history: dict = {}

class AuditIn(BaseModel):
    site_name: str = "Site principal"
    date: Optional[str] = None                    # YYYY-MM-DD (défaut : aujourd'hui)
    score_global: int
    score_axes: dict = {}
    gains_annuels_euros: float = 0.0
    cout_outils_annuel: float = 0.0
    roi: Optional[float] = None
    plan_action: dict = {}
    formule: str = "Pro"

class AuditOut(BaseModel):
    id: int
    site_name: str
    date: str
    score_global: int
    score_axes: dict
    gains_annuels_euros: float
    cout_outils_annuel: float
    roi: Optional[float]
    plan_action: dict
    formule: str

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
app = FastAPI(title="Portail Client Multi-Business", version="6.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def security_headers(request: Request, call_next):
    resp = await call_next(request)
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("X-Frame-Options", "DENY")
    resp.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    return resp

# Sert le frontend du portail depuis le même serveur (une seule URL, zéro CORS)
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

FRONTEND = os.path.join(BASE_DIR, "index.html")
ASSETS = os.path.join(BASE_DIR, "assets")
PRODIA_DIR = os.path.join(BASE_DIR, "prodia")
if os.path.isdir(ASSETS):
    app.mount("/assets", StaticFiles(directory=ASSETS), name="assets")
if os.path.isdir(PRODIA_DIR):
    app.mount("/audit-assets", StaticFiles(directory=PRODIA_DIR), name="audit-assets")

@app.get("/audit", include_in_schema=False)
def outil_audit():
    """Outil d'audit ProdIA connecté (même origine que le portail → token JWT partagé)."""
    return FileResponse(os.path.join(PRODIA_DIR, "outil-audit.html"))

@app.get("/", include_in_schema=False)
def portail():
    return FileResponse(FRONTEND)

@app.get("/portail", include_in_schema=False)
def portail_alt():
    return FileResponse(FRONTEND)

@app.get("/api/health")
def health():
    return {"status": "ok", "service": "portail-multi", "version": "6.0.0",
            "time": datetime.now(timezone.utc).isoformat()}

@app.get("/api/businesses")
def list_businesses(db: Session = Depends(get_db)):
    return [{"slug": b.slug, "name": b.name, "color": b.color,
             "modules": b.modules.split(",") if b.modules else [],
             "taux_horaire": b.taux_horaire or DEFAULT_TAUX_HORAIRE} for b in db.query(Business).all()]

@app.post("/api/auth/register", response_model=TokenOut, status_code=201)
def register(data: RegisterIn, db: Session = Depends(get_db)):
    if len(data.password) < 8:
        raise HTTPException(400, "Le mot de passe doit faire au moins 8 caractères")
    business = db.query(Business).filter(Business.slug == data.business).first()
    if not business:
        raise HTTPException(404, "Business inconnu")
    existing = db.query(User).filter(User.email == data.email.lower()).first()
    if existing:
        raise HTTPException(409, "Un compte existe déjà avec cet email")
    user = User(email=data.email.lower(), hashed_password=password_hash.hash(data.password),
                full_name=data.full_name, company=data.company, business_id=business.id)
    db.add(user)
    db.flush()
    db.add(ClientProfile(user_id=user.id, statut="demande"))
    db.commit()
    token = create_access_token({"sub": str(user.id)})
    return TokenOut(access_token=token, user=UserOut(id=user.id, email=user.email, full_name=user.full_name, company=user.company, is_admin=user.is_admin, business=business.slug))

@app.post("/api/auth/login", response_model=TokenOut)
def login(form: OAuth2PasswordRequestForm = Depends(), request: Request = None, db: Session = Depends(get_db)):
    email = form.username.strip().lower()
    ip = request.client.host if request else "?"
    key = f"{ip}|{email}"

    # Anti brute-force : 5 échecs / 15 min par IP+email
    now = time.time()
    fails = LOGIN_FAILURES[key]
    while fails and now - fails[0] > RATE_LIMIT_WINDOW_SECONDS:
        fails.popleft()
    if len(fails) >= RATE_LIMIT_MAX:
        wait_min = int(RATE_LIMIT_WINDOW_SECONDS - (now - fails[0])) // 60 + 1
        raise HTTPException(429, f"Trop de tentatives. Réessayez dans {wait_min} min.")

    user = db.query(User).filter(User.email == email).first()
    if not user or not password_hash.verify(form.password, user.hashed_password):
        fails.append(now)
        raise HTTPException(401, "Email ou mot de passe incorrect")

    LOGIN_FAILURES.pop(key, None)  # succès → on remet le compteur à zéro
    business = db.query(Business).filter(Business.id == user.business_id).first()
    token = create_access_token({"sub": str(user.id)})
    return TokenOut(access_token=token, user=UserOut(id=user.id, email=user.email, full_name=user.full_name, company=user.company, is_admin=user.is_admin, business=business.slug if business else ""))

def _build_charts(user: User, business: Business, profil, automations, db: Session) -> dict:
    """Graphiques V6 : données 100% issues de la base (automation_events)."""
    today = _monday_of(date.today())
    weeks = [today - timedelta(weeks=i) for i in range(DASHBOARD_WEEKS - 1, -1, -1)]
    start = weeks[0]

    events = db.query(AutomationEvent).filter(
        AutomationEvent.user_id == user.id,
        AutomationEvent.date >= start,
    ).all()
    by_week = defaultdict(float)
    for ev in events:
        by_week[_monday_of(ev.date)] += ev.heures_gagnees or 0.0

    hours_by_week = [
        {"week": w.isoformat(), "label": f"{w.day:02d}/{w.month:02d}",
         "heures": round(by_week.get(w, 0.0), 1)}
        for w in weeks
    ]
    hours_total = round(sum(h["heures"] for h in hours_by_week), 1)
    cumul = 0.0
    hours_cumulative = []
    for h in hours_by_week:
        cumul += h["heures"]
        hours_cumulative.append(round(cumul, 1))

    taux = (business.taux_horaire if business else None) or DEFAULT_TAUX_HORAIRE
    euros_saved = round(hours_total * taux, 2)
    last4 = round(sum(h["heures"] for h in hours_by_week[-4:]), 1)
    euros_saved_month = round(last4 * taux, 2)

    montant_mensuel = (profil.montant_mensuel if profil else 0.0) or 0.0
    roi = round(euros_saved_month / montant_mensuel, 1) if montant_mensuel > 0 else 0.0
    pct_temps_gagne = round(last4 / 160.0 * 100.0, 1)  # base ~160 h travaillées/mois

    status_counts = {s: 0 for s in ("active", "maintenance", "pause")}
    for a in automations:
        status_counts[a.statut if a.statut in status_counts else "pause"] += 1

    return {
        "hours_by_week": hours_by_week,
        "hours_cumulative": hours_cumulative,
        "hours_total": hours_total,
        "euros_saved": euros_saved,
        "euros_saved_month": euros_saved_month,
        "roi": roi,
        "pct_temps_gagne": pct_temps_gagne,
        "taux_horaire": taux,
        "automation_status_counts": status_counts,
        "weeks": DASHBOARD_WEEKS,
    }

@app.get("/api/dashboard", response_model=DashboardOut)
def dashboard(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    business = db.query(Business).filter(Business.id == user.business_id).first()
    profil = db.query(ClientProfile).filter(ClientProfile.user_id == user.id).first()
    automations = db.query(Automation).filter(Automation.user_id == user.id).order_by(Automation.id).all()
    invoices = db.query(Invoice).filter(Invoice.user_id == user.id).order_by(Invoice.id.desc()).all()
    packs = db.query(Pack).filter(Pack.business_id == user.business_id).all()
    purchases = db.query(Purchase).filter(Purchase.user_id == user.id).order_by(Purchase.id.desc()).all()

    modules = [m for m in (business.modules.split(",") if business and business.modules else []) if m]
    has_automations = "automations" in modules
    has_packs = "packs" in modules
    has_audits = "audits" in modules

    total_heures = sum(a.heures_gagnees or 0 for a in automations) + (profil.temps_recupere_heures or 0 if profil else 0)
    live_count = sum(1 for a in automations if a.statut == "active")
    en_cours = sum(1 for a in automations if a.statut not in ("active",))
    total_facture = sum((i.montant or 0) for i in invoices if i.statut == "payee")
    total_achats = sum((p.montant or 0) for p in purchases if p.statut == "payee")

    stats = {
        "total_heures_recuperees": round(total_heures, 1),
        "automations_live": live_count,
        "automations_en_cours": en_cours,
        "total_investi": round(total_facture + total_achats, 2),
        "packs_achetes": len(purchases),
    }

    charts = _build_charts(user, business, profil, automations, db) if has_automations else {}

    audits = []
    audits_history = {}
    if has_audits:
        audits = [_audit_to_dict(a) for a in db.query(AuditSnapshot).filter(AuditSnapshot.user_id == user.id)
                  .order_by(AuditSnapshot.date.desc(), AuditSnapshot.id.desc()).all()]
        audits_history = _audits_history(user.id, db)

    return DashboardOut(
        user=UserOut(id=user.id, email=user.email, full_name=user.full_name, company=user.company, is_admin=user.is_admin, business=business.slug if business else ""),
        business={"slug": business.slug, "name": business.name, "color": business.color, "modules": modules,
                  "taux_horaire": business.taux_horaire or DEFAULT_TAUX_HORAIRE} if business else {},
        profil={"statut": profil.statut if profil else "demande", "plan": profil.plan if profil else "", "montant_mensuel": profil.montant_mensuel if profil else 0.0,
                "temps_recupere_heures": profil.temps_recupere_heures if profil else 0.0, "notes": profil.notes if profil else ""},
        automations=[{"id": a.id, "titre": a.titre, "description": a.description, "statut": a.statut,
                      "heures_gagnees": a.heures_gagnees,
                      "heures_gagnees_mensuelles": a.heures_gagnees_mensuelles,
                      "date_livraison": a.date_livraison.isoformat() if a.date_livraison else None}
                     for a in automations],
        invoices=[{"id": i.id, "numero": i.numero, "montant": i.montant, "statut": i.statut, "date": i.date} for i in invoices],
        packs=[{"id": p.id, "name": p.name, "price": p.price, "description": p.description, "skills": p.skills} for p in packs],
        purchases=[{"id": p.id, "pack_name": p.pack_name, "montant": p.montant, "statut": p.statut, "date": p.date, "skills": p.skills} for p in purchases],
        stats=stats,
        charts=charts,
        audits=audits,
        audits_history=audits_history,
    )

@app.post("/api/packs/{pack_id}/buy")
def buy_pack(pack_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    pack = db.query(Pack).filter(Pack.id == pack_id, Pack.business_id == user.business_id).first()
    if not pack:
        raise HTTPException(404, "Pack introuvable")
    purchase = Purchase(user_id=user.id, pack_id=pack.id, pack_name=pack.name, montant=pack.price,
                        statut="payee", date=datetime.now(timezone.utc).strftime("%Y-%m-%d"), skills=pack.skills)
    db.add(purchase)
    db.commit()
    return {"ok": True, "purchase_id": purchase.id, "skills": pack.skills}

# ---------------------------------------------------------------------------
# ProdIA — Audits : suivi mensuel du score / gains / ROI (offre Pro)
# ---------------------------------------------------------------------------
def _audit_to_dict(a: AuditSnapshot) -> dict:
    def _json(s, default):
        try:
            return json.loads(s) if s else default
        except Exception:
            return default
    return {
        "id": a.id,
        "site_name": a.site_name or "Site principal",
        "date": a.date.isoformat() if a.date else "",
        "score_global": a.score_global or 0,
        "score_axes": _json(a.score_axes, {}),
        "gains_annuels_euros": round(a.gains_annuels_euros or 0.0, 2),
        "cout_outils_annuel": round(a.cout_outils_annuel or 0.0, 2),
        "roi": a.roi,
        "plan_action": _json(a.plan_action, {}),
        "formule": a.formule or "",
    }

def _audits_history(user_id: int, db: Session, site_name: Optional[str] = None) -> dict:
    """Séries temporelles réelles : score /100, gains € annuels, ROI, par date d'audit."""
    q = db.query(AuditSnapshot).filter(AuditSnapshot.user_id == user_id)
    if site_name:
        q = q.filter(AuditSnapshot.site_name == site_name)
    audits = q.order_by(AuditSnapshot.date.asc(), AuditSnapshot.id.asc()).all()
    sites = [r[0] for r in db.query(AuditSnapshot.site_name)
             .filter(AuditSnapshot.user_id == user_id)
             .distinct().order_by(AuditSnapshot.site_name).all()]
    last = audits[-1] if audits else None
    prev = audits[-2] if len(audits) >= 2 else None
    return {
        "audits": [_audit_to_dict(a) for a in audits],
        "sites": sites,
        "labels": [a.date.strftime("%d/%m/%Y") for a in audits],
        "scores": [a.score_global or 0 for a in audits],
        "gains": [round(a.gains_annuels_euros or 0.0, 2) for a in audits],
        "rois": [a.roi for a in audits],
        "delta_score": (last.score_global - prev.score_global) if last and prev else 0,
        "delta_gains": round((last.gains_annuels_euros or 0.0) - (prev.gains_annuels_euros or 0.0), 2) if last and prev else 0.0,
        "dernier": _audit_to_dict(last) if last else None,
        "precedent": _audit_to_dict(prev) if prev else None,
        "nb_audits": len(audits),
    }

@app.post("/api/audits", response_model=AuditOut, status_code=201)
def create_audit(data: AuditIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Enregistre un audit ProdIA (depuis l'outil d'audit ou le portail). Données réelles."""
    business = db.query(Business).filter(Business.id == user.business_id).first()
    modules = (business.modules or "").split(",") if business else []
    if "audits" not in modules:
        raise HTTPException(403, "Votre espace ne dispose pas du module audits")
    try:
        audit_date = date.fromisoformat(data.date) if data.date else date.today()
    except ValueError:
        raise HTTPException(422, "Date invalide (format attendu : YYYY-MM-DD)")
    snap = AuditSnapshot(
        user_id=user.id,
        site_name=(data.site_name or "Site principal").strip() or "Site principal",
        date=audit_date,
        score_global=max(0, min(100, int(data.score_global))),
        score_axes=json.dumps(data.score_axes, ensure_ascii=False),
        gains_annuels_euros=float(data.gains_annuels_euros or 0.0),
        cout_outils_annuel=float(data.cout_outils_annuel or 0.0),
        roi=float(data.roi) if data.roi is not None else None,
        plan_action=json.dumps(data.plan_action, ensure_ascii=False),
        formule=data.formule or "Pro",
    )
    db.add(snap)
    db.commit()
    db.refresh(snap)
    return _audit_to_dict(snap)

@app.get("/api/audits", response_model=list)
def list_audits(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Liste des audits du client (du plus récent au plus ancien)."""
    audits = db.query(AuditSnapshot).filter(AuditSnapshot.user_id == user.id) \
        .order_by(AuditSnapshot.date.desc(), AuditSnapshot.id.desc()).all()
    return [_audit_to_dict(a) for a in audits]

@app.get("/api/audits/history", response_model=dict)
def audits_history(user: User = Depends(get_current_user), db: Session = Depends(get_db),
                   site: Optional[str] = None):
    """Séries temporelles pour les graphiques Évolution (score, gains €, ROI)."""
    return _audits_history(user.id, db, site_name=site)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
