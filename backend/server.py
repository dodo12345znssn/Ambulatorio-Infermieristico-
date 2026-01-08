from fastapi import FastAPI, APIRouter, HTTPException, Depends, status, UploadFile, File, Form, Response
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.responses import StreamingResponse
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
from pathlib import Path
from pydantic import BaseModel, Field, ConfigDict, field_validator
from typing import List, Optional, Dict, Any
import uuid
from datetime import datetime, timezone, date, timedelta
import jwt
import bcrypt
from enum import Enum
import base64
import io
import zipfile
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image as RLImage
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# MongoDB connection
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

# JWT Settings
JWT_SECRET = os.environ.get('JWT_SECRET', 'ambulatorio-infermieristico-secret-key-2024')
JWT_ALGORITHM = "HS256"
JWT_EXPIRATION_HOURS = 24

security = HTTPBearer()

# Create the main app
app = FastAPI(title="Ambulatorio Infermieristico API")

# Create a router with the /api prefix
api_router = APIRouter(prefix="/api")

# ============== ENUMS ==============
class PatientType(str, Enum):
    PICC = "PICC"
    MED = "MED"
    PICC_MED = "PICC_MED"

class PatientStatus(str, Enum):
    IN_CURA = "in_cura"
    DIMESSO = "dimesso"
    SOSPESO = "sospeso"

class DischargeReason(str, Enum):
    GUARITO = "guarito"
    ADI = "adi"
    ALTRO = "altro"

class Ambulatorio(str, Enum):
    PTA_CENTRO = "pta_centro"
    VILLA_GINESTRE = "villa_ginestre"

# ============== MODELS ==============
class UserLogin(BaseModel):
    username: str
    password: str

class UserResponse(BaseModel):
    id: str
    username: str
    ambulatori: List[str]

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse

class PatientCreate(BaseModel):
    nome: str
    cognome: str
    tipo: PatientType
    ambulatorio: Ambulatorio
    data_nascita: Optional[str] = None
    codice_fiscale: Optional[str] = None
    telefono: Optional[str] = None
    email: Optional[str] = None
    medico_base: Optional[str] = None
    anamnesi: Optional[str] = None
    terapia_in_atto: Optional[str] = None
    allergie: Optional[str] = None

class PatientUpdate(BaseModel):
    nome: Optional[str] = None
    cognome: Optional[str] = None
    tipo: Optional[PatientType] = None
    data_nascita: Optional[str] = None
    codice_fiscale: Optional[str] = None
    telefono: Optional[str] = None
    email: Optional[str] = None
    medico_base: Optional[str] = None
    anamnesi: Optional[str] = None
    terapia_in_atto: Optional[str] = None
    allergie: Optional[str] = None
    status: Optional[PatientStatus] = None
    discharge_reason: Optional[str] = None
    discharge_notes: Optional[str] = None
    suspend_notes: Optional[str] = None
    lesion_markers: Optional[List[Dict[str, Any]]] = None

# Helper function to generate unique patient code
def generate_patient_code(nome: str, cognome: str) -> str:
    """Generate unique patient code like 'm234h' based on name"""
    import random
    import string
    # Take first letter of cognome lowercase
    prefix = cognome[0].lower() if cognome else 'x'
    # Generate 3 random digits
    digits = ''.join(random.choices(string.digits, k=3))
    # Add 1 random letter
    suffix = random.choice(string.ascii_lowercase)
    return f"{prefix}{digits}{suffix}"

class Patient(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    codice_paziente: str = ""  # Codice univoco paziente (es. m234h)
    nome: str
    cognome: str
    tipo: PatientType
    ambulatorio: Ambulatorio
    status: PatientStatus = PatientStatus.IN_CURA
    data_nascita: Optional[str] = None
    codice_fiscale: Optional[str] = None
    telefono: Optional[str] = None
    email: Optional[str] = None
    medico_base: Optional[str] = None
    anamnesi: Optional[str] = None
    terapia_in_atto: Optional[str] = None
    allergie: Optional[str] = None
    lesion_markers: List[Dict[str, Any]] = []
    discharge_reason: Optional[str] = None
    discharge_notes: Optional[str] = None
    suspend_notes: Optional[str] = None
    scheda_med_counter: int = 0  # Counter for MED schede
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

# Prestazioni
class PrestazionePICC(str, Enum):
    MEDICAZIONE_SEMPLICE = "medicazione_semplice"
    IRRIGAZIONE_CATETERE = "irrigazione_catetere"

class PrestazioneMED(str, Enum):
    MEDICAZIONE_SEMPLICE = "medicazione_semplice"
    FASCIATURA_SEMPLICE = "fasciatura_semplice"
    INIEZIONE_TERAPEUTICA = "iniezione_terapeutica"
    CATETERE_VESCICALE = "catetere_vescicale"

class AppointmentCreate(BaseModel):
    patient_id: str
    ambulatorio: Ambulatorio
    data: str  # YYYY-MM-DD
    ora: str   # HH:MM
    tipo: str  # PICC or MED
    prestazioni: List[str]
    note: Optional[str] = None
    stato: Optional[str] = "da_fare"  # da_fare, effettuato, non_presentato

class Appointment(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    patient_id: str
    patient_nome: Optional[str] = None
    patient_cognome: Optional[str] = None
    ambulatorio: Ambulatorio
    data: str
    ora: str
    tipo: str
    prestazioni: List[str]
    note: Optional[str] = None
    stato: str = "da_fare"  # da_fare, effettuato, non_presentato
    completed: bool = False  # kept for backward compatibility
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

# Scheda Medicazione MED
class SchedaMedicazioneMEDCreate(BaseModel):
    patient_id: str
    ambulatorio: Ambulatorio
    data_compilazione: str
    fondo: List[str] = []  # granuleggiante, fibrinoso, necrotico, infetto, biofilmato
    margini: List[str] = []  # attivi, piantati, in_estensione, a_scogliera
    cute_perilesionale: List[str] = []  # integra, secca, arrossata, macerata, ipercheratosica
    essudato_quantita: Optional[str] = None  # assente, moderato, abbondante
    essudato_tipo: List[str] = []  # sieroso, ematico, infetto
    medicazione: str = "La lesione è stata trattata seguendo le 4 fasi del Wound Hygiene:\nDetersione con Prontosan\nDebridement e Riattivazione dei margini\nMedicazione: "
    prossimo_cambio: Optional[str] = None
    firma: Optional[str] = None
    foto_ids: List[str] = []

# Helper to generate unique scheda code
def generate_scheda_code(data_compilazione: str) -> str:
    """Generate unique code for scheda: MED-DDMMYY-XXXX"""
    try:
        dt = datetime.strptime(data_compilazione, "%Y-%m-%d")
        date_part = dt.strftime("%d%m%y")
    except:
        date_part = datetime.now().strftime("%d%m%y")
    random_part = uuid.uuid4().hex[:4].upper()
    return f"MED-{date_part}-{random_part}"

class SchedaMedicazioneMED(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    codice: str = Field(default="")  # Codice identificativo univoco
    patient_id: str
    ambulatorio: Ambulatorio
    data_compilazione: str
    fondo: List[str] = []
    margini: List[str] = []
    cute_perilesionale: List[str] = []
    essudato_quantita: Optional[str] = None
    essudato_tipo: List[str] = []
    medicazione: str
    prossimo_cambio: Optional[str] = None
    firma: Optional[str] = None
    foto_ids: List[str] = []
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

# Scheda Impianto PICC - Nuova struttura completa
class SchedaImpiantoPICCCreate(BaseModel):
    patient_id: str
    ambulatorio: Ambulatorio
    scheda_type: str = "semplificata"  # semplificata o completa
    # Header
    presidio_ospedaliero: Optional[str] = None
    codice: Optional[str] = None
    unita_operativa: Optional[str] = None
    data_presa_carico: Optional[str] = None
    cartella_clinica: Optional[str] = None
    # Sezione Catetere Già Presente
    catetere_presente: bool = False
    catetere_presente_tipo: Optional[str] = None
    catetere_presente_struttura: Optional[str] = None
    catetere_presente_data: Optional[str] = None
    catetere_presente_ora: Optional[str] = None
    catetere_presente_modalita: Optional[str] = None
    catetere_presente_rx: Optional[bool] = None
    catetere_da_sostituire: Optional[bool] = None
    # Sezione Impianto Catetere
    tipo_catetere: Optional[str] = None
    posizionamento_cvc: Optional[str] = None
    posizionamento_cvc_altro: Optional[str] = None
    braccio: Optional[str] = None
    vena: Optional[str] = None
    exit_site_cm: Optional[str] = None
    tunnelizzazione: Optional[bool] = False
    tunnelizzazione_note: Optional[str] = None
    valutazione_sito: Optional[bool] = None
    ecoguidato: Optional[bool] = None
    igiene_mani: Optional[bool] = None
    precauzioni_barriera: Optional[bool] = None
    disinfezione: Optional[List[str]] = []
    sutureless_device: Optional[bool] = None
    medicazione_trasparente: Optional[bool] = None
    medicazione_occlusiva: Optional[bool] = None
    controllo_rx: Optional[bool] = None
    controllo_ecg: Optional[bool] = None
    modalita: Optional[str] = None
    motivazione: List[str] = []
    motivazione_altro: Optional[str] = None
    data_posizionamento: Optional[str] = None
    operatore: Optional[str] = None
    allegati: List[str] = []
    # Legacy fields for backward compatibility
    data_impianto: Optional[str] = None
    sede: Optional[str] = None
    disinfettante: Optional[str] = None
    note: Optional[str] = None

class SchedaImpiantoPICC(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    patient_id: str
    ambulatorio: Ambulatorio
    scheda_type: str = "semplificata"  # semplificata o completa
    # Header
    presidio_ospedaliero: Optional[str] = None
    codice: Optional[str] = None
    unita_operativa: Optional[str] = None
    data_presa_carico: Optional[str] = None
    cartella_clinica: Optional[str] = None
    # Sezione Catetere Già Presente
    catetere_presente: bool = False
    catetere_presente_tipo: Optional[str] = None
    catetere_presente_struttura: Optional[str] = None
    catetere_presente_data: Optional[str] = None
    catetere_presente_ora: Optional[str] = None
    catetere_presente_modalita: Optional[str] = None
    catetere_presente_rx: Optional[bool] = None
    catetere_da_sostituire: Optional[bool] = None
    # Sezione Impianto Catetere
    tipo_catetere: Optional[str] = None
    posizionamento_cvc: Optional[str] = None
    posizionamento_cvc_altro: Optional[str] = None
    braccio: Optional[str] = None
    vena: Optional[str] = None
    exit_site_cm: Optional[str] = None
    tunnelizzazione: Optional[bool] = False
    tunnelizzazione_note: Optional[str] = None
    valutazione_sito: Optional[bool] = None
    ecoguidato: Optional[bool] = None
    igiene_mani: Optional[bool] = None
    precauzioni_barriera: Optional[bool] = None
    disinfezione: Optional[List[str]] = []
    sutureless_device: Optional[bool] = None
    medicazione_trasparente: Optional[bool] = None
    medicazione_occlusiva: Optional[bool] = None
    controllo_rx: Optional[bool] = None
    controllo_ecg: Optional[bool] = None
    modalita: Optional[str] = None
    motivazione: Optional[List[str]] = []
    motivazione_altro: Optional[str] = None
    data_posizionamento: Optional[str] = None
    operatore: Optional[str] = None
    allegati: Optional[List[str]] = []
    # Legacy fields
    data_impianto: Optional[str] = None
    sede: Optional[str] = None
    disinfettante: Optional[str] = None
    note: Optional[str] = None
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    
    @field_validator('motivazione', 'disinfezione', 'allegati', mode='before')
    @classmethod
    def convert_none_to_list(cls, v):
        return v if v is not None else []

# Scheda Gestione Mensile PICC
class SchedaGestionePICCCreate(BaseModel):
    patient_id: str
    ambulatorio: Ambulatorio
    mese: str  # YYYY-MM
    giorni: Dict[str, Dict[str, Any]] = {}  # {1: {lavaggio_mani: true, ...}, 2: {...}}
    note: Optional[str] = None

class SchedaGestionePICC(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    patient_id: str
    ambulatorio: Ambulatorio
    mese: str
    giorni: Dict[str, Dict[str, Any]] = {}
    note: Optional[str] = None
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

# Photo / Attachment
class PhotoCreate(BaseModel):
    patient_id: str
    ambulatorio: Ambulatorio
    tipo: str  # MED, PICC, MED_SCHEDA
    descrizione: Optional[str] = None
    data: str
    file_type: Optional[str] = "image"  # image, pdf, word, excel
    original_name: Optional[str] = None
    scheda_med_id: Optional[str] = None  # Link to specific scheda MED

class Photo(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    patient_id: str
    ambulatorio: Ambulatorio
    tipo: str
    descrizione: Optional[str] = None
    data: str
    image_data: str  # Base64
    file_type: Optional[str] = "image"  # image, pdf, word, excel
    original_name: Optional[str] = None
    mime_type: Optional[str] = None
    scheda_med_id: Optional[str] = None
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

# Document Templates
class DocumentTemplate(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    nome: str
    categoria: str  # PICC or MED
    tipo_file: str  # pdf, word
    url: str

# Statistics
class StatisticsQuery(BaseModel):
    ambulatorio: Ambulatorio
    tipo: Optional[str] = None  # PICC, MED or None for all
    anno: int
    mese: Optional[int] = None

# ============== USERS DATA ==============
USERS = {
    "Domenico": {
        "password": "infermiere",
        "ambulatori": ["pta_centro", "villa_ginestre"]
    },
    "Antonella": {
        "password": "infermiere",
        "ambulatori": ["pta_centro", "villa_ginestre"]
    },
    "Giovanna": {
        "password": "infermiere",
        "ambulatori": ["pta_centro"]
    },
    "Oriana": {
        "password": "infermiere",
        "ambulatori": ["pta_centro"]
    },
    "G.Domenico": {
        "password": "infermiere",
        "ambulatori": ["pta_centro"]
    }
}

# Document templates
DOCUMENT_TEMPLATES = [
    # MED Documents
    {"id": "consent_med", "nome": "Consenso Informato MED", "categoria": "MED", "tipo_file": "pdf", "url": "https://customer-assets.emergentagent.com/job_f548c735-b113-437f-82ec-c0afbf122c8d/artifacts/k3jcaxa4_CONSENSO_INFORMATO.pdf"},
    {"id": "scheda_mmg", "nome": "Scheda MMG", "categoria": "MED", "tipo_file": "pdf", "url": "https://customer-assets.emergentagent.com/job_f548c735-b113-437f-82ec-c0afbf122c8d/artifacts/8bonfflf_SCHEDA_MMG.pdf"},
    {"id": "anagrafica_med", "nome": "Anagrafica/Anamnesi MED", "categoria": "MED", "tipo_file": "pdf", "url": "https://customer-assets.emergentagent.com/job_f548c735-b113-437f-82ec-c0afbf122c8d/artifacts/txx60tb0_anagrafica%20med.jpg"},
    {"id": "scheda_medicazione_med", "nome": "Scheda Medicazione MED", "categoria": "MED", "tipo_file": "pdf", "url": "https://customer-assets.emergentagent.com/job_f548c735-b113-437f-82ec-c0afbf122c8d/artifacts/nzkb51vc_medicazione%20med.jpg"},
    # PICC Documents
    {"id": "consent_picc_1", "nome": "Consenso Generico Processi Clinico-Assistenziali", "categoria": "PICC", "tipo_file": "pdf", "url": "https://customer-assets.emergentagent.com/job_medhub-38/artifacts/ysusww7f_CONSENSO%20GENERICO%20AI%20PROCESSI%20CLINICO.ASSISTENZIALI%20ORDINARI%201.pdf"},
    {"id": "consent_picc_2", "nome": "Consenso Informato PICC e Midline", "categoria": "PICC", "tipo_file": "pdf", "url": "https://customer-assets.emergentagent.com/job_medhub-38/artifacts/siz46bgw_CONSENSO%20INFORMATO%20PICC%20E%20MIDLINE.pdf"},
    {"id": "brochure_picc_port", "nome": "Brochure PICC Port", "categoria": "PICC", "tipo_file": "pdf", "url": "https://customer-assets.emergentagent.com/job_medhub-38/artifacts/cein282q_Picc%20Port.pdf"},
    {"id": "brochure_picc", "nome": "Brochure PICC", "categoria": "PICC", "tipo_file": "pdf", "url": "https://customer-assets.emergentagent.com/job_medhub-38/artifacts/kk882djy_Picc.pdf"},
    {"id": "scheda_impianto_picc", "nome": "Scheda Impianto e Gestione AV", "categoria": "PICC", "tipo_file": "pdf", "url": "https://customer-assets.emergentagent.com/job_medhub-38/artifacts/sbw1iws9_Sch%20Impianto%20Gestione%20AV%20NEW.pdf"},
    {"id": "scheda_impianto_pdf", "nome": "Scheda Impianto", "categoria": "PICC", "tipo_file": "pdf", "url": "https://customer-assets.emergentagent.com/job_docucare-6/artifacts/3c52ewuw_Scheda%20Impianto.pdf"},
]

# Italian holidays for Palermo
def get_holidays(year: int) -> List[str]:
    holidays = [
        f"{year}-01-01",  # Capodanno
        f"{year}-01-06",  # Epifania
        f"{year}-04-25",  # Liberazione
        f"{year}-05-01",  # Festa del Lavoro
        f"{year}-06-02",  # Festa della Repubblica
        f"{year}-07-15",  # Santa Rosalia (Palermo)
        f"{year}-08-15",  # Ferragosto
        f"{year}-11-01",  # Ognissanti
        f"{year}-12-08",  # Immacolata
        f"{year}-12-25",  # Natale
        f"{year}-12-26",  # Santo Stefano
    ]
    # Easter calculation (simplified - would need proper algorithm for accuracy)
    # Adding approximate Easter dates for 2026-2030
    easter_dates = {
        2026: "2026-04-05",
        2027: "2027-03-28",
        2028: "2028-04-16",
        2029: "2029-04-01",
        2030: "2030-04-21",
    }
    if year in easter_dates:
        easter = easter_dates[year]
        holidays.append(easter)
        # Pasquetta (Easter Monday)
        easter_date = datetime.strptime(easter, "%Y-%m-%d")
        pasquetta = easter_date + timedelta(days=1)
        holidays.append(pasquetta.strftime("%Y-%m-%d"))
    return holidays

# ============== AUTH HELPERS ==============
def create_token(username: str, ambulatori: List[str]) -> str:
    payload = {
        "sub": username,
        "ambulatori": ambulatori,
        "exp": datetime.now(timezone.utc) + timedelta(hours=JWT_EXPIRATION_HOURS)
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)) -> dict:
    try:
        payload = jwt.decode(credentials.credentials, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token scaduto")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Token non valido")

# ============== AUTH ROUTES ==============
@api_router.post("/auth/login", response_model=TokenResponse)
async def login(data: UserLogin):
    user = USERS.get(data.username)
    if not user or user["password"] != data.password:
        raise HTTPException(status_code=401, detail="Credenziali non valide")
    
    token = create_token(data.username, user["ambulatori"])
    return TokenResponse(
        access_token=token,
        user=UserResponse(
            id=data.username.lower().replace(".", "_"),
            username=data.username,
            ambulatori=user["ambulatori"]
        )
    )

@api_router.get("/auth/me", response_model=UserResponse)
async def get_current_user(payload: dict = Depends(verify_token)):
    username = payload["sub"]
    user = USERS.get(username)
    if not user:
        raise HTTPException(status_code=404, detail="Utente non trovato")
    return UserResponse(
        id=username.lower().replace(".", "_"),
        username=username,
        ambulatori=user["ambulatori"]
    )

# ============== PATIENTS ROUTES ==============
@api_router.post("/patients", response_model=Patient, status_code=201)
async def create_patient(data: PatientCreate, payload: dict = Depends(verify_token)):
    # Check ambulatorio access
    if data.ambulatorio.value not in payload["ambulatori"]:
        raise HTTPException(status_code=403, detail="Non hai accesso a questo ambulatorio")
    
    # Villa Ginestre only allows PICC
    if data.ambulatorio == Ambulatorio.VILLA_GINESTRE and data.tipo != PatientType.PICC:
        raise HTTPException(status_code=400, detail="Villa delle Ginestre gestisce solo pazienti PICC")
    
    # Generate unique patient code
    codice_paziente = generate_patient_code(data.nome, data.cognome)
    # Ensure uniqueness
    while await db.patients.find_one({"codice_paziente": codice_paziente}):
        codice_paziente = generate_patient_code(data.nome, data.cognome)
    
    patient_data = data.model_dump()
    patient_data["codice_paziente"] = codice_paziente
    patient_data["scheda_med_counter"] = 0
    patient = Patient(**patient_data)
    doc = patient.model_dump()
    await db.patients.insert_one(doc)
    return patient

@api_router.get("/patients", response_model=List[Patient])
async def get_patients(
    ambulatorio: Ambulatorio,
    status: Optional[PatientStatus] = None,
    tipo: Optional[PatientType] = None,
    search: Optional[str] = None,
    payload: dict = Depends(verify_token)
):
    if ambulatorio.value not in payload["ambulatori"]:
        raise HTTPException(status_code=403, detail="Non hai accesso a questo ambulatorio")
    
    query = {"ambulatorio": ambulatorio.value}
    if status:
        query["status"] = status.value
    if tipo:
        query["tipo"] = tipo.value
    if search:
        query["$or"] = [
            {"nome": {"$regex": search, "$options": "i"}},
            {"cognome": {"$regex": search, "$options": "i"}}
        ]
    
    patients = await db.patients.find(query, {"_id": 0}).sort("cognome", 1).to_list(1000)
    return patients

@api_router.get("/patients/{patient_id}", response_model=Patient)
async def get_patient(patient_id: str, payload: dict = Depends(verify_token)):
    patient = await db.patients.find_one({"id": patient_id}, {"_id": 0})
    if not patient:
        raise HTTPException(status_code=404, detail="Paziente non trovato")
    if patient["ambulatorio"] not in payload["ambulatori"]:
        raise HTTPException(status_code=403, detail="Non hai accesso a questo ambulatorio")
    return patient

@api_router.put("/patients/{patient_id}", response_model=Patient)
async def update_patient(patient_id: str, data: PatientUpdate, payload: dict = Depends(verify_token)):
    patient = await db.patients.find_one({"id": patient_id}, {"_id": 0})
    if not patient:
        raise HTTPException(status_code=404, detail="Paziente non trovato")
    if patient["ambulatorio"] not in payload["ambulatori"]:
        raise HTTPException(status_code=403, detail="Non hai accesso a questo ambulatorio")
    
    update_data = {k: v for k, v in data.model_dump().items() if v is not None}
    update_data["updated_at"] = datetime.now(timezone.utc).isoformat()
    
    await db.patients.update_one({"id": patient_id}, {"$set": update_data})
    updated = await db.patients.find_one({"id": patient_id}, {"_id": 0})
    return updated

@api_router.delete("/patients/{patient_id}")
async def delete_patient(patient_id: str, payload: dict = Depends(verify_token)):
    patient = await db.patients.find_one({"id": patient_id}, {"_id": 0})
    if not patient:
        raise HTTPException(status_code=404, detail="Paziente non trovato")
    if patient["ambulatorio"] not in payload["ambulatori"]:
        raise HTTPException(status_code=403, detail="Non hai accesso a questo ambulatorio")
    
    # Delete patient
    await db.patients.delete_one({"id": patient_id})
    
    # Delete all related records
    await db.schede_impianto_picc.delete_many({"patient_id": patient_id})
    await db.schede_gestione_picc.delete_many({"patient_id": patient_id})
    await db.schede_medicazione_med.delete_many({"patient_id": patient_id})
    await db.appointments.delete_many({"patient_id": patient_id})
    await db.prescrizioni.delete_many({"patient_id": patient_id})
    await db.photos.delete_many({"patient_id": patient_id})
    
    return {"message": "Paziente e tutte le schede correlate eliminati"}

# ============== APPOINTMENTS ROUTES ==============
@api_router.post("/appointments", response_model=Appointment)
async def create_appointment(data: AppointmentCreate, payload: dict = Depends(verify_token)):
    if data.ambulatorio.value not in payload["ambulatori"]:
        raise HTTPException(status_code=403, detail="Non hai accesso a questo ambulatorio")
    
    # Get patient info
    patient = await db.patients.find_one({"id": data.patient_id}, {"_id": 0})
    if not patient:
        raise HTTPException(status_code=404, detail="Paziente non trovato")
    
    # Check slot availability (max 2 per type per slot)
    existing = await db.appointments.count_documents({
        "ambulatorio": data.ambulatorio.value,
        "data": data.data,
        "ora": data.ora,
        "tipo": data.tipo
    })
    if existing >= 2:
        raise HTTPException(status_code=400, detail="Slot pieno (max 2 pazienti)")
    
    appointment = Appointment(
        **data.model_dump(),
        patient_nome=patient["nome"],
        patient_cognome=patient["cognome"]
    )
    doc = appointment.model_dump()
    await db.appointments.insert_one(doc)
    return appointment

@api_router.get("/appointments", response_model=List[Appointment])
async def get_appointments(
    ambulatorio: Ambulatorio,
    data: Optional[str] = None,
    data_from: Optional[str] = None,
    data_to: Optional[str] = None,
    tipo: Optional[str] = None,
    payload: dict = Depends(verify_token)
):
    if ambulatorio.value not in payload["ambulatori"]:
        raise HTTPException(status_code=403, detail="Non hai accesso a questo ambulatorio")
    
    query = {"ambulatorio": ambulatorio.value}
    if data:
        query["data"] = data
    elif data_from and data_to:
        query["data"] = {"$gte": data_from, "$lte": data_to}
    if tipo:
        query["tipo"] = tipo
    
    appointments = await db.appointments.find(query, {"_id": 0}).sort([("data", 1), ("ora", 1)]).to_list(1000)
    return appointments

@api_router.put("/appointments/{appointment_id}", response_model=Appointment)
async def update_appointment(appointment_id: str, data: dict, payload: dict = Depends(verify_token)):
    appointment = await db.appointments.find_one({"id": appointment_id}, {"_id": 0})
    if not appointment:
        raise HTTPException(status_code=404, detail="Appuntamento non trovato")
    if appointment["ambulatorio"] not in payload["ambulatori"]:
        raise HTTPException(status_code=403, detail="Non hai accesso a questo ambulatorio")
    
    await db.appointments.update_one({"id": appointment_id}, {"$set": data})
    updated = await db.appointments.find_one({"id": appointment_id}, {"_id": 0})
    return updated

@api_router.delete("/appointments/{appointment_id}")
async def delete_appointment(appointment_id: str, payload: dict = Depends(verify_token)):
    appointment = await db.appointments.find_one({"id": appointment_id}, {"_id": 0})
    if not appointment:
        raise HTTPException(status_code=404, detail="Appuntamento non trovato")
    if appointment["ambulatorio"] not in payload["ambulatori"]:
        raise HTTPException(status_code=403, detail="Non hai accesso a questo ambulatorio")
    
    await db.appointments.delete_one({"id": appointment_id})
    return {"message": "Appuntamento eliminato"}

# ============== SCHEDE MEDICAZIONE MED ==============
@api_router.post("/schede-medicazione-med", response_model=SchedaMedicazioneMED)
async def create_scheda_medicazione_med(data: SchedaMedicazioneMEDCreate, payload: dict = Depends(verify_token)):
    if data.ambulatorio.value not in payload["ambulatori"]:
        raise HTTPException(status_code=403, detail="Non hai accesso a questo ambulatorio")
    
    # Get patient to use their code
    patient = await db.patients.find_one({"id": data.patient_id}, {"_id": 0})
    if not patient:
        raise HTTPException(status_code=404, detail="Paziente non trovato")
    
    # Get or generate patient code
    codice_paziente = patient.get("codice_paziente")
    if not codice_paziente:
        # Generate code for existing patient without one
        codice_paziente = generate_patient_code(patient.get("nome", ""), patient.get("cognome", ""))
        while await db.patients.find_one({"codice_paziente": codice_paziente, "id": {"$ne": data.patient_id}}):
            codice_paziente = generate_patient_code(patient.get("nome", ""), patient.get("cognome", ""))
        await db.patients.update_one({"id": data.patient_id}, {"$set": {"codice_paziente": codice_paziente}})
    
    # Get next scheda number for this patient
    counter = patient.get("scheda_med_counter", 0) + 1
    await db.patients.update_one({"id": data.patient_id}, {"$set": {"scheda_med_counter": counter}})
    
    # Generate scheda code: codice_paziente-numero (es. m234h-1)
    codice = f"{codice_paziente}-{counter}"
    
    scheda_data = data.model_dump()
    scheda_data["codice"] = codice
    scheda = SchedaMedicazioneMED(**scheda_data)
    doc = scheda.model_dump()
    await db.schede_medicazione_med.insert_one(doc)
    return scheda

@api_router.get("/schede-medicazione-med", response_model=List[SchedaMedicazioneMED])
async def get_schede_medicazione_med(
    patient_id: str,
    ambulatorio: Ambulatorio,
    payload: dict = Depends(verify_token)
):
    if ambulatorio.value not in payload["ambulatori"]:
        raise HTTPException(status_code=403, detail="Non hai accesso a questo ambulatorio")
    
    schede = await db.schede_medicazione_med.find(
        {"patient_id": patient_id, "ambulatorio": ambulatorio.value},
        {"_id": 0}
    ).sort("data_compilazione", -1).to_list(1000)
    return schede

@api_router.get("/schede-medicazione-med/{scheda_id}", response_model=SchedaMedicazioneMED)
async def get_scheda_medicazione_med(scheda_id: str, payload: dict = Depends(verify_token)):
    scheda = await db.schede_medicazione_med.find_one({"id": scheda_id}, {"_id": 0})
    if not scheda:
        raise HTTPException(status_code=404, detail="Scheda non trovata")
    if scheda["ambulatorio"] not in payload["ambulatori"]:
        raise HTTPException(status_code=403, detail="Non hai accesso a questo ambulatorio")
    return scheda

@api_router.put("/schede-medicazione-med/{scheda_id}", response_model=SchedaMedicazioneMED)
async def update_scheda_medicazione_med(scheda_id: str, data: dict, payload: dict = Depends(verify_token)):
    scheda = await db.schede_medicazione_med.find_one({"id": scheda_id}, {"_id": 0})
    if not scheda:
        raise HTTPException(status_code=404, detail="Scheda non trovata")
    if scheda["ambulatorio"] not in payload["ambulatori"]:
        raise HTTPException(status_code=403, detail="Non hai accesso a questo ambulatorio")
    
    await db.schede_medicazione_med.update_one({"id": scheda_id}, {"$set": data})
    updated = await db.schede_medicazione_med.find_one({"id": scheda_id}, {"_id": 0})
    return updated

# ============== SCHEDE IMPIANTO PICC ==============
@api_router.post("/schede-impianto-picc", response_model=SchedaImpiantoPICC)
async def create_scheda_impianto_picc(data: SchedaImpiantoPICCCreate, payload: dict = Depends(verify_token)):
    if data.ambulatorio.value not in payload["ambulatori"]:
        raise HTTPException(status_code=403, detail="Non hai accesso a questo ambulatorio")
    
    scheda = SchedaImpiantoPICC(**data.model_dump())
    doc = scheda.model_dump()
    await db.schede_impianto_picc.insert_one(doc)
    return scheda

@api_router.get("/schede-impianto-picc", response_model=List[SchedaImpiantoPICC])
async def get_schede_impianto_picc(
    patient_id: str,
    ambulatorio: Ambulatorio,
    payload: dict = Depends(verify_token)
):
    if ambulatorio.value not in payload["ambulatori"]:
        raise HTTPException(status_code=403, detail="Non hai accesso a questo ambulatorio")
    
    schede = await db.schede_impianto_picc.find(
        {"patient_id": patient_id, "ambulatorio": ambulatorio.value},
        {"_id": 0}
    ).sort("data_impianto", -1).to_list(1000)
    return schede

@api_router.put("/schede-impianto-picc/{scheda_id}", response_model=SchedaImpiantoPICC)
async def update_scheda_impianto_picc(scheda_id: str, data: dict, payload: dict = Depends(verify_token)):
    scheda = await db.schede_impianto_picc.find_one({"id": scheda_id}, {"_id": 0})
    if not scheda:
        raise HTTPException(status_code=404, detail="Scheda non trovata")
    if scheda["ambulatorio"] not in payload["ambulatori"]:
        raise HTTPException(status_code=403, detail="Non hai accesso a questo ambulatorio")
    
    await db.schede_impianto_picc.update_one({"id": scheda_id}, {"$set": data})
    updated = await db.schede_impianto_picc.find_one({"id": scheda_id}, {"_id": 0})
    return updated

# Generate PDF for Scheda Impianto PICC in official format
@api_router.get("/schede-impianto-picc/{scheda_id}/pdf")
async def download_scheda_impianto_pdf(scheda_id: str, payload: dict = Depends(verify_token)):
    """Download scheda impianto PICC as PDF in official format"""
    scheda = await db.schede_impianto_picc.find_one({"id": scheda_id}, {"_id": 0})
    if not scheda:
        raise HTTPException(status_code=404, detail="Scheda non trovata")
    if scheda["ambulatorio"] not in payload["ambulatori"]:
        raise HTTPException(status_code=403, detail="Non hai accesso a questo ambulatorio")
    
    # Get patient info
    patient = await db.patients.find_one({"id": scheda["patient_id"]}, {"_id": 0})
    
    # Generate PDF
    pdf_bytes = generate_scheda_impianto_pdf(scheda, patient)
    
    # Use data_posizionamento or data_impianto for filename
    data_file = scheda.get('data_posizionamento') or scheda.get('data_impianto') or 'nd'
    
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=scheda_impianto_{data_file}.pdf"}
    )

def generate_scheda_impianto_pdf(scheda: dict, patient: dict) -> bytes:
    """Generate PDF for Scheda Impianto PICC - EXACT format as per official form"""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=0.5*cm, bottomMargin=0.5*cm, leftMargin=0.8*cm, rightMargin=0.8*cm)
    story = []
    
    # Styles
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle('Title', fontSize=11, alignment=1, fontName='Helvetica-Bold', spaceAfter=3)
    section_header = ParagraphStyle('SectionHeader', fontSize=9, fontName='Helvetica-Bold', alignment=1, 
                                    backColor=colors.HexColor('#e5e7eb'), spaceBefore=6, spaceAfter=3)
    normal_style = ParagraphStyle('Normal', fontSize=7, spaceAfter=2, fontName='Helvetica')
    small_style = ParagraphStyle('Small', fontSize=6.5, spaceAfter=1, fontName='Helvetica')
    italic_small = ParagraphStyle('ItalicSmall', fontSize=6, fontName='Helvetica-Oblique', textColor=colors.grey)
    
    def cb(checked):
        """Checkbox helper - simple text representation"""
        if checked:
            return "[X]"  # Checked
        else:
            return "[  ]"  # Empty
    
    def cb_list(arr, val):
        """Check if value is in list"""
        is_checked = isinstance(arr, list) and val in arr
        return cb(is_checked)
    
    def get_val(key, default=""):
        """Get value from scheda, return default only if None"""
        val = scheda.get(key)
        if val is None:
            return default
        return val
    
    # === HEADER ===
    story.append(Paragraph("SCHEDA IMPIANTO e GESTIONE ACCESSI VENOSI", title_style))
    story.append(Paragraph("Allegato n. 2", ParagraphStyle('Right', fontSize=7, alignment=2)))
    story.append(Spacer(1, 5))
    
    # Patient Info Box - Header info
    patient_name = f"{patient.get('cognome', '')} {patient.get('nome', '')}" if patient else ""
    patient_dob = patient.get('data_nascita', '') if patient else ""
    patient_sex = patient.get('sesso', '') if patient else ""
    
    # Format sesso properly
    sesso_display = f"{cb(patient_sex == 'M')} M   {cb(patient_sex == 'F')} F"
    
    header_data = [
        [Paragraph("<b>Presidio Ospedaliero/Struttura Sanitaria:</b>", small_style), 
         get_val('presidio_ospedaliero'), 
         Paragraph("<b>Codice:</b>", small_style), 
         get_val('codice'),
         Paragraph("<b>U.O.:</b>", small_style), 
         get_val('unita_operativa')],
        [Paragraph("<b>Cognome e Nome Paziente:</b>", small_style), 
         patient_name,
         Paragraph("<b>Data di nascita:</b>", small_style), 
         patient_dob,
         Paragraph("<b>Sesso:</b>", small_style), 
         sesso_display],
        [Paragraph("<b>Preso in carico dalla struttura dal:</b>", small_style), 
         get_val('data_presa_carico'),
         Paragraph("<b>Cartella Clinica n.:</b>", small_style), 
         get_val('cartella_clinica'), "", ""],
    ]
    t = Table(header_data, colWidths=[4.5*cm, 4*cm, 2.5*cm, 2.5*cm, 1.5*cm, 3.5*cm])
    t.setStyle(TableStyle([
        ('FONTSIZE', (0, 0), (-1, -1), 6.5),
        ('BOX', (0, 0), (-1, -1), 1, colors.black),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 2),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
    ]))
    story.append(t)
    story.append(Spacer(1, 8))
    
    # === SECTION 1: CATETERE GIÀ PRESENTE ===
    story.append(Paragraph("SEZIONE CATETERE GIÀ PRESENTE", section_header))
    story.append(Paragraph("(Da compilare se catetere già presente al momento della presa in carico ambulatoriale o in regime di degenza)", italic_small))
    story.append(Spacer(1, 3))
    
    tipo_presente = get_val('catetere_presente_tipo')
    tipo_opts = [
        ("cvc_non_tunnellizzato", "CVC non tunnellizzato (breve termine)"),
        ("cvc_tunnellizzato", "CVC tunnellizzato (lungo termine tipo Groshong, Hickman, Broviac)"),
        ("picc", "CVC medio termine (PICC)"),
        ("port", "PORT (lungo termine)"),
        ("midline", "Midline"),
    ]
    
    tipo_line = "Tipo di Catetere: " + "  ".join([f"{cb(tipo_presente == opt[0])} {opt[1]}" for opt in tipo_opts])
    story.append(Paragraph(tipo_line, small_style))
    story.append(Spacer(1, 2))
    
    story.append(Paragraph(f"Riportare: - Struttura/reparto dove il catetere è stato inserito: {get_val('catetere_presente_struttura')}", small_style))
    
    mod_presente = get_val('catetere_presente_modalita')
    story.append(Paragraph(f"data: {get_val('catetere_presente_data')}  ora: {get_val('catetere_presente_ora')}  modalità: {cb(mod_presente == 'emergenza_urgenza')} emergenza/urgenza  {cb(mod_presente == 'programmato_elezione')} programmato/elezione", small_style))
    
    rx_presente = get_val('catetere_presente_rx')
    story.append(Paragraph(f"Se è stato effettuato controllo RX Post-Inserimento: {cb(rx_presente == True)} SI  {cb(rx_presente == False)} NO", small_style))
    
    da_sostituire = get_val('catetere_da_sostituire')
    story.append(Paragraph(f"Catetere da sostituire: {cb(da_sostituire == True)} SI  {cb(da_sostituire == False)} NO   se si compilare la SEZIONE IMPIANTO", small_style))
    
    story.append(Spacer(1, 8))
    
    # === SECTION 2: IMPIANTO CATETERE ===
    story.append(Paragraph("SEZIONE IMPIANTO CATETERE", section_header))
    story.append(Paragraph("(Da compilare se catetere viene impiantato nella struttura)", italic_small))
    story.append(Spacer(1, 3))
    
    # TIPO DI CATETERE - Aggiornato con nuove opzioni
    tipo = get_val('tipo_catetere')
    tipo_opts_new = [
        ("picc", "PICC"),
        ("midline", "Midline"),
        ("picc_port", "PICC Port"),
        ("port_a_cath", "PORT a cath"),
        ("altro", "Altro"),
    ]
    tipo_line = "<b>TIPO DI CATETERE:</b> " + "  ".join([f"{cb(tipo == opt[0])} {opt[1]}" for opt in tipo_opts_new])
    if tipo == 'altro':
        tipo_line += f" specificare: {get_val('tipo_catetere_altro')}"
    story.append(Paragraph(tipo_line, small_style))
    story.append(Spacer(1, 2))
    
    # POSIZIONAMENTO CVC
    pos_cvc = get_val('posizionamento_cvc')
    cvc_opts = [("succlavia_dx", "succlavia dx"), ("succlavia_sn", "succlavia sn"), 
                ("giugulare_dx", "giugulare interna dx"), ("giugulare_sn", "giugulare interna sn"), ("altro", "altro")]
    pos_line = "<b>POSIZIONAMENTO CVC:</b> " + "  ".join([f"{cb(pos_cvc == opt[0])} {opt[1]}" for opt in cvc_opts])
    if pos_cvc == 'altro':
        pos_line += f" specificare: {get_val('posizionamento_cvc_altro')}"
    story.append(Paragraph(pos_line, small_style))
    story.append(Spacer(1, 2))
    
    # POSIZIONAMENTO PICC con nuovi campi
    braccio = get_val('braccio')
    vena = get_val('vena')
    picc_line = f"<b>POSIZIONAMENTO PICC:</b> {cb(braccio == 'dx')} braccio dx  {cb(braccio == 'sn')} braccio sn    <b>Vena:</b> {cb(vena == 'basilica')} basilica  {cb(vena == 'cefalica')} cefalica  {cb(vena == 'brachiale')} brachiale"
    story.append(Paragraph(picc_line, small_style))
    
    # Nuovi campi misure catetere
    misure_line = f"<b>Diametro vena:</b> {get_val('diametro_vena_mm')} mm    <b>Profondità:</b> {get_val('profondita_cm')} cm    <b>Exit-site:</b> {get_val('exit_site_cm')} cm"
    story.append(Paragraph(misure_line, small_style))
    
    catetere_line = f"<b>Lunghezza totale:</b> {get_val('lunghezza_totale_cm')} cm    <b>Lunghezza impiantata:</b> {get_val('lunghezza_impiantata_cm')} cm    <b>French:</b> {get_val('french')}    <b>Lumi:</b> {get_val('lumi')}    <b>Lotto:</b> {get_val('lotto')}"
    story.append(Paragraph(catetere_line, small_style))
    story.append(Spacer(1, 3))
    
    # PROCEDURE DETAILS
    val_sito = get_val('valutazione_sito')
    story.append(Paragraph(f"<b>VALUTAZIONE MIGLIOR SITO DI INSERIMENTO:</b>  {cb(val_sito == True)} SI  {cb(val_sito == False)} NO", small_style))
    
    eco = get_val('ecoguidato')
    story.append(Paragraph(f"<b>IMPIANTO ECOGUIDATO:</b>  {cb(eco == True)} SI  {cb(eco == False)} NO", small_style))
    
    igiene = get_val('igiene_mani')
    story.append(Paragraph(f"<b>IGIENE DELLE MANI (LAVAGGIO ANTISETTICO DELLE MANI O FRIZIONE ALCOLICA):</b>  {cb(igiene == True)} SI  {cb(igiene == False)} NO", small_style))
    
    prec = get_val('precauzioni_barriera')
    story.append(Paragraph(f"<b>UTILIZZO MASSIME PRECAUZIONI DI BARRIERA</b> (berretto, maschera, camice sterile, guanti sterili, telo sterile sul paziente): {cb(prec == True)} SI  {cb(prec == False)} NO", small_style))
    
    # DISINFEZIONE
    disinfezione = get_val('disinfezione') or []
    story.append(Paragraph(f"<b>DISINFEZIONE DELLA CUTE INTEGRA:</b>  {cb_list(disinfezione, 'clorexidina_2')} CLOREXIDINA IN SOLUZIONE ALCOLICA 2%    {cb_list(disinfezione, 'iodiopovidone')} IODIOPOVIDONE", small_style))
    
    # COLLA HYSTOACRILICA (nuovo)
    colla = get_val('colla_hystoacrilica')
    story.append(Paragraph(f"<b>UTILIZZO COLLA HYSTOACRILICA:</b>  {cb(colla == True)} SI  {cb(colla == False)} NO", small_style))
    
    # DISPOSITIVI
    sut = get_val('sutureless_device')
    story.append(Paragraph(f"<b>IMPIEGO DI \"SUTURELESS DEVICES\" PER IL FISSAGGIO DEL CATETERE:</b>  {cb(sut == True)} SI  {cb(sut == False)} NO", small_style))
    
    med_trasp = get_val('medicazione_trasparente')
    med_occl = get_val('medicazione_occlusiva')
    story.append(Paragraph(f"<b>IMPIEGO DI MEDICAZIONE SEMIPERMEABILE TRASPARENTE:</b>  {cb(med_trasp == True)} SI  {cb(med_trasp == False)} NO    <b>IMPIEGO DI MEDICAZIONE OCCLUSIVA:</b>  {cb(med_occl == True)} SI  {cb(med_occl == False)} NO", small_style))
    
    # CONTROLLI (aggiornato con ECG intracavitario)
    rx_post = get_val('controllo_rx')
    ecg_intra = get_val('ecg_intracavitario')
    story.append(Paragraph(f"<b>CONTROLLO RX POST-INSERIMENTO:</b>  {cb(rx_post == True)} SI  {cb(rx_post == False)} NO    <b>ECG INTRACAVITARIO:</b>  {cb(ecg_intra == True)} SI  {cb(ecg_intra == False)} NO", small_style))
    
    # MODALITÀ
    mod = get_val('modalita')
    story.append(Paragraph(f"<b>MODALITÀ:</b>  {cb(mod == 'emergenza')} EMERGENZA  {cb(mod == 'urgenza')} URGENZA  {cb(mod == 'elezione')} ELEZIONE", small_style))
    
    # MOTIVAZIONE - Aggiornato con nuove opzioni
    motivazione = get_val('motivazione') or []
    motiv_line = f"<b>MOTIVAZIONE DI INSERIMENTO CVC:</b>  {cb_list(motivazione, 'chemioterapia')} chemioterapia  {cb_list(motivazione, 'scarso_patrimonio_venoso')} scarso patrimonio venoso  {cb_list(motivazione, 'npt')} NPT  {cb_list(motivazione, 'monitoraggio')} monitoraggio invasivo  {cb_list(motivazione, 'altro')} altro"
    if 'altro' in motivazione:
        motiv_line += f" (specificare): {get_val('motivazione_altro')}"
    story.append(Paragraph(motiv_line, small_style))
    
    story.append(Spacer(1, 10))
    
    # === FOOTER con 1° e 2° operatore ===
    data_pos = get_val('data_posizionamento') or get_val('data_impianto')
    footer_data = [
        [Paragraph("<b>DATA POSIZIONAMENTO:</b>", small_style), data_pos, "", ""],
        [Paragraph("<b>1° OPERATORE:</b>", small_style), get_val('operatore'), Paragraph("<b>FIRMA:</b>", small_style), "________________"],
        [Paragraph("<b>2° OPERATORE:</b>", small_style), get_val('secondo_operatore'), Paragraph("<b>FIRMA:</b>", small_style), "________________"],
    ]
    ft = Table(footer_data, colWidths=[4*cm, 6*cm, 2*cm, 6.5*cm])
    ft.setStyle(TableStyle([
        ('FONTSIZE', (0, 0), (-1, -1), 7),
        ('BOX', (0, 0), (-1, -1), 1, colors.black),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    story.append(ft)
    
    # Note se presenti
    if get_val('note'):
        story.append(Spacer(1, 8))
        story.append(Paragraph(f"<b>NOTE:</b> {get_val('note')}", normal_style))
    
    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()


# ============== SCHEDE GESTIONE PICC (MENSILE) ==============
@api_router.post("/schede-gestione-picc", response_model=SchedaGestionePICC)
async def create_scheda_gestione_picc(data: SchedaGestionePICCCreate, payload: dict = Depends(verify_token)):
    if data.ambulatorio.value not in payload["ambulatori"]:
        raise HTTPException(status_code=403, detail="Non hai accesso a questo ambulatorio")
    
    # Check if already exists for this month
    existing = await db.schede_gestione_picc.find_one({
        "patient_id": data.patient_id,
        "ambulatorio": data.ambulatorio.value,
        "mese": data.mese
    })
    if existing:
        raise HTTPException(status_code=400, detail="Esiste già una scheda per questo mese")
    
    scheda = SchedaGestionePICC(**data.model_dump())
    doc = scheda.model_dump()
    await db.schede_gestione_picc.insert_one(doc)
    return scheda

@api_router.get("/schede-gestione-picc", response_model=List[SchedaGestionePICC])
async def get_schede_gestione_picc(
    patient_id: str,
    ambulatorio: Ambulatorio,
    mese: Optional[str] = None,
    payload: dict = Depends(verify_token)
):
    if ambulatorio.value not in payload["ambulatori"]:
        raise HTTPException(status_code=403, detail="Non hai accesso a questo ambulatorio")
    
    query = {"patient_id": patient_id, "ambulatorio": ambulatorio.value}
    if mese:
        query["mese"] = mese
    
    schede = await db.schede_gestione_picc.find(query, {"_id": 0}).sort("mese", -1).to_list(100)
    return schede

@api_router.put("/schede-gestione-picc/{scheda_id}", response_model=SchedaGestionePICC)
async def update_scheda_gestione_picc(scheda_id: str, data: dict, payload: dict = Depends(verify_token)):
    scheda = await db.schede_gestione_picc.find_one({"id": scheda_id}, {"_id": 0})
    if not scheda:
        raise HTTPException(status_code=404, detail="Scheda non trovata")
    if scheda["ambulatorio"] not in payload["ambulatori"]:
        raise HTTPException(status_code=403, detail="Non hai accesso a questo ambulatorio")
    
    data["updated_at"] = datetime.now(timezone.utc).isoformat()
    await db.schede_gestione_picc.update_one({"id": scheda_id}, {"$set": data})
    updated = await db.schede_gestione_picc.find_one({"id": scheda_id}, {"_id": 0})
    return updated

# ============== PHOTOS / ATTACHMENTS ==============
@api_router.post("/photos")
async def upload_photo(
    patient_id: str = Form(...),
    ambulatorio: str = Form(...),
    tipo: str = Form(...),
    data: str = Form(...),
    descrizione: Optional[str] = Form(None),
    file_type: Optional[str] = Form("image"),
    original_name: Optional[str] = Form(None),
    scheda_med_id: Optional[str] = Form(None),
    file: UploadFile = File(...),
    payload: dict = Depends(verify_token)
):
    if ambulatorio not in payload["ambulatori"]:
        raise HTTPException(status_code=403, detail="Non hai accesso a questo ambulatorio")
    
    contents = await file.read()
    image_data = base64.b64encode(contents).decode('utf-8')
    
    # Determine file type from content type if not provided
    mime_type = file.content_type
    if not file_type or file_type == "image":
        if mime_type and 'pdf' in mime_type:
            file_type = 'pdf'
        elif mime_type and ('word' in mime_type or 'document' in mime_type):
            file_type = 'word'
        elif mime_type and ('excel' in mime_type or 'spreadsheet' in mime_type):
            file_type = 'excel'
        elif mime_type and mime_type.startswith('image/'):
            file_type = 'image'
    
    photo = Photo(
        patient_id=patient_id,
        ambulatorio=Ambulatorio(ambulatorio),
        tipo=tipo,
        descrizione=descrizione,
        data=data,
        image_data=image_data,
        file_type=file_type,
        original_name=original_name or file.filename,
        mime_type=mime_type,
        scheda_med_id=scheda_med_id if scheda_med_id != "pending" else None
    )
    doc = photo.model_dump()
    await db.photos.insert_one(doc)
    
    return {"id": photo.id, "message": "File caricato"}

@api_router.get("/photos")
async def get_photos(
    patient_id: str,
    ambulatorio: Ambulatorio,
    tipo: Optional[str] = None,
    payload: dict = Depends(verify_token)
):
    if ambulatorio.value not in payload["ambulatori"]:
        raise HTTPException(status_code=403, detail="Non hai accesso a questo ambulatorio")
    
    query = {"patient_id": patient_id, "ambulatorio": ambulatorio.value}
    if tipo:
        query["tipo"] = tipo
    
    photos = await db.photos.find(query, {"_id": 0}).sort("data", -1).to_list(100)
    return photos

@api_router.get("/photos/{photo_id}")
async def get_photo(photo_id: str, payload: dict = Depends(verify_token)):
    photo = await db.photos.find_one({"id": photo_id}, {"_id": 0})
    if not photo:
        raise HTTPException(status_code=404, detail="Foto non trovata")
    if photo["ambulatorio"] not in payload["ambulatori"]:
        raise HTTPException(status_code=403, detail="Non hai accesso a questo ambulatorio")
    return photo

@api_router.delete("/photos/{photo_id}")
async def delete_photo(photo_id: str, payload: dict = Depends(verify_token)):
    photo = await db.photos.find_one({"id": photo_id}, {"_id": 0})
    if not photo:
        raise HTTPException(status_code=404, detail="Foto non trovata")
    if photo["ambulatorio"] not in payload["ambulatori"]:
        raise HTTPException(status_code=403, detail="Non hai accesso a questo ambulatorio")
    
    await db.photos.delete_one({"id": photo_id})
    return {"message": "Foto eliminata"}

# ============== DOCUMENTS ==============
@api_router.get("/documents")
async def get_documents(
    ambulatorio: Ambulatorio,
    categoria: Optional[str] = None,
    payload: dict = Depends(verify_token)
):
    if ambulatorio.value not in payload["ambulatori"]:
        raise HTTPException(status_code=403, detail="Non hai accesso a questo ambulatorio")
    
    docs = DOCUMENT_TEMPLATES.copy()
    
    # Villa Ginestre only sees PICC documents
    if ambulatorio == Ambulatorio.VILLA_GINESTRE:
        docs = [d for d in docs if d["categoria"] == "PICC"]
    
    if categoria:
        docs = [d for d in docs if d["categoria"] == categoria]
    
    return docs

# ============== STATISTICS ==============
@api_router.get("/statistics")
async def get_statistics(
    ambulatorio: Ambulatorio,
    anno: int,
    mese: Optional[int] = None,
    tipo: Optional[str] = None,
    payload: dict = Depends(verify_token)
):
    if ambulatorio.value not in payload["ambulatori"]:
        raise HTTPException(status_code=403, detail="Non hai accesso a questo ambulatorio")
    
    # Villa Ginestre only shows PICC stats
    if ambulatorio == Ambulatorio.VILLA_GINESTRE and tipo == "MED":
        raise HTTPException(status_code=400, detail="Villa delle Ginestre non ha statistiche MED")
    
    # Build date range
    if mese:
        start_date = f"{anno}-{mese:02d}-01"
        if mese == 12:
            end_date = f"{anno + 1}-01-01"
        else:
            end_date = f"{anno}-{mese + 1:02d}-01"
    else:
        start_date = f"{anno}-01-01"
        end_date = f"{anno + 1}-01-01"
    
    query = {
        "ambulatorio": ambulatorio.value,
        "data": {"$gte": start_date, "$lt": end_date}
    }
    if tipo:
        query["tipo"] = tipo
    elif ambulatorio == Ambulatorio.VILLA_GINESTRE:
        query["tipo"] = "PICC"
    
    appointments = await db.appointments.find(query, {"_id": 0}).to_list(10000)
    
    # Calculate statistics
    total_accessi = len(appointments)
    unique_patients = len(set(a["patient_id"] for a in appointments))
    
    # Prestazioni count
    prestazioni_count = {}
    for app in appointments:
        for prest in app.get("prestazioni", []):
            prestazioni_count[prest] = prestazioni_count.get(prest, 0) + 1
    
    # Monthly breakdown
    monthly_stats = {}
    for app in appointments:
        month = app["data"][:7]  # YYYY-MM
        if month not in monthly_stats:
            monthly_stats[month] = {"accessi": 0, "pazienti": set(), "prestazioni": {}}
        monthly_stats[month]["accessi"] += 1
        monthly_stats[month]["pazienti"].add(app["patient_id"])
        for prest in app.get("prestazioni", []):
            monthly_stats[month]["prestazioni"][prest] = monthly_stats[month]["prestazioni"].get(prest, 0) + 1
    
    # Convert sets to counts
    for month in monthly_stats:
        monthly_stats[month]["pazienti_unici"] = len(monthly_stats[month]["pazienti"])
        del monthly_stats[month]["pazienti"]
    
    return {
        "anno": anno,
        "mese": mese,
        "ambulatorio": ambulatorio.value,
        "tipo": tipo,
        "totale_accessi": total_accessi,
        "pazienti_unici": unique_patients,
        "prestazioni": prestazioni_count,
        "dettaglio_mensile": monthly_stats
    }

@api_router.get("/statistics/compare")
async def compare_statistics(
    ambulatorio: Ambulatorio,
    periodo1_anno: int,
    periodo1_mese: Optional[int] = None,
    periodo2_anno: int = None,
    periodo2_mese: Optional[int] = None,
    tipo: Optional[str] = None,
    payload: dict = Depends(verify_token)
):
    if ambulatorio.value not in payload["ambulatori"]:
        raise HTTPException(status_code=403, detail="Non hai accesso a questo ambulatorio")
    
    # Get stats for both periods
    stats1 = await get_statistics(ambulatorio, periodo1_anno, periodo1_mese, tipo, payload)
    stats2 = await get_statistics(ambulatorio, periodo2_anno or periodo1_anno, periodo2_mese, tipo, payload)
    
    # Calculate differences
    diff = {
        "accessi": stats2["totale_accessi"] - stats1["totale_accessi"],
        "pazienti_unici": stats2["pazienti_unici"] - stats1["pazienti_unici"],
        "prestazioni": {}
    }
    
    all_prestazioni = set(stats1["prestazioni"].keys()) | set(stats2["prestazioni"].keys())
    for prest in all_prestazioni:
        val1 = stats1["prestazioni"].get(prest, 0)
        val2 = stats2["prestazioni"].get(prest, 0)
        diff["prestazioni"][prest] = val2 - val1
    
    return {
        "periodo1": stats1,
        "periodo2": stats2,
        "differenze": diff
    }

# ============== CALENDAR HELPERS ==============
@api_router.get("/calendar/holidays")
async def get_calendar_holidays(anno: int):
    return get_holidays(anno)

@api_router.get("/calendar/slots")
async def get_time_slots():
    """Returns available time slots"""
    morning_slots = []
    afternoon_slots = []
    
    # Morning: 08:30 - 13:00
    current = datetime.strptime("08:30", "%H:%M")
    end_morning = datetime.strptime("13:00", "%H:%M")
    while current < end_morning:
        morning_slots.append(current.strftime("%H:%M"))
        current += timedelta(minutes=30)
    
    # Afternoon: 15:00 - 17:00
    current = datetime.strptime("15:00", "%H:%M")
    end_afternoon = datetime.strptime("17:00", "%H:%M")
    while current < end_afternoon:
        afternoon_slots.append(current.strftime("%H:%M"))
        current += timedelta(minutes=30)
    
    return {
        "mattina": morning_slots,
        "pomeriggio": afternoon_slots,
        "tutti": morning_slots + afternoon_slots
    }

# ============== DELETE ENDPOINTS ==============

@api_router.delete("/schede-impianto-picc/{scheda_id}")
async def delete_scheda_impianto(scheda_id: str, payload: dict = Depends(verify_token)):
    scheda = await db.schede_impianto_picc.find_one({"id": scheda_id}, {"_id": 0})
    if not scheda:
        raise HTTPException(status_code=404, detail="Scheda non trovata")
    if scheda["ambulatorio"] not in payload["ambulatori"]:
        raise HTTPException(status_code=403, detail="Non hai accesso a questo ambulatorio")
    
    await db.schede_impianto_picc.delete_one({"id": scheda_id})
    return {"message": "Scheda impianto eliminata"}

@api_router.delete("/schede-gestione-picc/{scheda_id}")
async def delete_scheda_gestione(scheda_id: str, payload: dict = Depends(verify_token)):
    scheda = await db.schede_gestione_picc.find_one({"id": scheda_id}, {"_id": 0})
    if not scheda:
        raise HTTPException(status_code=404, detail="Scheda non trovata")
    if scheda["ambulatorio"] not in payload["ambulatori"]:
        raise HTTPException(status_code=403, detail="Non hai accesso a questo ambulatorio")
    
    await db.schede_gestione_picc.delete_one({"id": scheda_id})
    return {"message": "Scheda gestione eliminata"}

@api_router.delete("/schede-medicazione-med/{scheda_id}")
async def delete_scheda_medicazione(scheda_id: str, payload: dict = Depends(verify_token)):
    scheda = await db.schede_medicazione_med.find_one({"id": scheda_id}, {"_id": 0})
    if not scheda:
        raise HTTPException(status_code=404, detail="Scheda non trovata")
    if scheda["ambulatorio"] not in payload["ambulatori"]:
        raise HTTPException(status_code=403, detail="Non hai accesso a questo ambulatorio")
    
    await db.schede_medicazione_med.delete_one({"id": scheda_id})
    return {"message": "Scheda medicazione eliminata"}

@api_router.put("/schede-impianto-picc/{scheda_id}")
async def update_scheda_impianto(scheda_id: str, data: dict, payload: dict = Depends(verify_token)):
    scheda = await db.schede_impianto_picc.find_one({"id": scheda_id}, {"_id": 0})
    if not scheda:
        raise HTTPException(status_code=404, detail="Scheda non trovata")
    if scheda["ambulatorio"] not in payload["ambulatori"]:
        raise HTTPException(status_code=403, detail="Non hai accesso a questo ambulatorio")
    
    data["updated_at"] = datetime.now(timezone.utc).isoformat()
    await db.schede_impianto_picc.update_one({"id": scheda_id}, {"$set": data})
    updated = await db.schede_impianto_picc.find_one({"id": scheda_id}, {"_id": 0})
    return updated

# ============== IMPLANT STATISTICS ==============
@api_router.get("/statistics/implants")
async def get_implant_statistics(
    ambulatorio: Ambulatorio,
    anno: int,
    mese: Optional[int] = None,
    payload: dict = Depends(verify_token)
):
    """Get statistics for implants (PICC, Port, Midline, etc.)"""
    if ambulatorio.value not in payload["ambulatori"]:
        raise HTTPException(status_code=403, detail="Non hai accesso a questo ambulatorio")
    
    # Build date range query
    if mese:
        start_date = f"{anno}-{mese:02d}-01"
        if mese == 12:
            end_date = f"{anno + 1}-01-01"
        else:
            end_date = f"{anno}-{mese + 1:02d}-01"
    else:
        start_date = f"{anno}-01-01"
        end_date = f"{anno + 1}-01-01"
    
    # Query implants
    query = {
        "ambulatorio": ambulatorio.value,
        "data_impianto": {"$gte": start_date, "$lt": end_date}
    }
    
    schede = await db.schede_impianto_picc.find(query, {"_id": 0}).to_list(1000)
    
    # Get list of existing patient IDs
    existing_patients = await db.patients.distinct("id", {"ambulatorio": ambulatorio.value})
    existing_patient_ids = set(existing_patients)
    
    # Count by type - only for existing patients
    tipo_counts = {}
    monthly_breakdown = {}
    
    for scheda in schede:
        # Skip if patient no longer exists
        patient_id = scheda.get("patient_id")
        if patient_id and patient_id not in existing_patient_ids:
            continue
            
        tipo = scheda.get("tipo_catetere", "altro")
        tipo_counts[tipo] = tipo_counts.get(tipo, 0) + 1
        
        # Monthly breakdown
        data_impianto = scheda.get("data_impianto", "")
        if data_impianto:
            month_key = data_impianto[:7]  # "YYYY-MM"
            if month_key not in monthly_breakdown:
                monthly_breakdown[month_key] = {}
            monthly_breakdown[month_key][tipo] = monthly_breakdown[month_key].get(tipo, 0) + 1
    
    # Labels for types
    tipo_labels = {
        "picc": "PICC",
        "picc_port": "PICC/Port",
        "midline": "Midline",
        "cvd_non_tunnellizzato": "CVC non tunnellizzato",
        "cvd_tunnellizzato": "CVC tunnellizzato",
        "port": "PORT",
    }
    
    return {
        "totale_impianti": len(schede),
        "per_tipo": tipo_counts,
        "tipo_labels": tipo_labels,
        "dettaglio_mensile": monthly_breakdown
    }

# ============== PATIENT FOLDER DOWNLOAD ==============

def generate_patient_pdf_section(patient: dict, schede_med: list, schede_impianto: list, schede_gestione: list, section: str = "all") -> bytes:
    """Generate PDF for a specific section of the patient folder
    section: 'all', 'anagrafica', 'medicazione', 'impianto', 'gestione'
    """
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=2*cm, leftMargin=2*cm, topMargin=2*cm, bottomMargin=2*cm)
    
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle('CustomTitle', parent=styles['Heading1'], fontSize=18, spaceAfter=30, alignment=TA_CENTER)
    heading_style = ParagraphStyle('CustomHeading', parent=styles['Heading2'], fontSize=14, spaceAfter=12, textColor=colors.HexColor('#1e40af'))
    normal_style = ParagraphStyle('CustomNormal', parent=styles['Normal'], fontSize=11, spaceAfter=6)
    
    story = []
    
    # Title based on section
    section_titles = {
        "all": "Cartella Clinica Completa",
        "anagrafica": "Anagrafica e Anamnesi",
        "medicazione": "Schede Medicazione",
        "impianto": "Schede Impianto PICC"
    }
    title = f"{section_titles.get(section, 'Cartella Clinica')} - {patient.get('cognome', '')} {patient.get('nome', '')}"
    story.append(Paragraph(title, title_style))
    story.append(Spacer(1, 20))
    
    # SEZIONE ANAGRAFICA - always show for 'all' and 'anagrafica'
    if section in ["all", "anagrafica"]:
        story.append(Paragraph("Dati Anagrafici", heading_style))
        info_data = [
            ["Nome:", patient.get('nome', '-')],
            ["Cognome:", patient.get('cognome', '-')],
            ["Tipo:", patient.get('tipo', '-')],
            ["Codice Fiscale:", patient.get('codice_fiscale', '-')],
            ["Data di Nascita:", patient.get('data_nascita', '-')],
            ["Sesso:", patient.get('sesso', '-')],
            ["Telefono:", patient.get('telefono', '-')],
            ["Email:", patient.get('email', '-')],
            ["Medico di Base:", patient.get('medico_base', '-')],
            ["Stato:", patient.get('status', '-')],
        ]
        table = Table(info_data, colWidths=[4*cm, 12*cm])
        table.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
        ]))
        story.append(table)
        story.append(Spacer(1, 20))
        
        # Anamnesi section
        if patient.get('anamnesi') or patient.get('terapia_in_atto') or patient.get('allergie'):
            story.append(Paragraph("Anamnesi", heading_style))
            if patient.get('anamnesi'):
                story.append(Paragraph(f"<b>Anamnesi:</b> {patient.get('anamnesi', '-')}", normal_style))
            if patient.get('terapia_in_atto'):
                story.append(Paragraph(f"<b>Terapia in Atto:</b> {patient.get('terapia_in_atto', '-')}", normal_style))
            if patient.get('allergie'):
                story.append(Paragraph(f"<b>Allergie:</b> {patient.get('allergie', '-')}", normal_style))
            story.append(Spacer(1, 20))
    
    # SEZIONE MEDICAZIONE - show for 'all' and 'medicazione'
    if section in ["all", "medicazione"] and schede_med:
        story.append(Paragraph("Schede Medicazione MED", heading_style))
        for idx, scheda in enumerate(schede_med, 1):
            story.append(Paragraph(f"<b>Medicazione #{idx} - Data: {scheda.get('data_compilazione', '-')}</b>", normal_style))
            story.append(Paragraph(f"Fondo: {', '.join(scheda.get('fondo', [])) or '-'}", normal_style))
            story.append(Paragraph(f"Margini: {', '.join(scheda.get('margini', [])) or '-'}", normal_style))
            story.append(Paragraph(f"Cute perilesionale: {', '.join(scheda.get('cute_perilesionale', [])) or '-'}", normal_style))
            story.append(Paragraph(f"Essudato Quantità: {scheda.get('essudato_quantita', '-')}", normal_style))
            story.append(Paragraph(f"Essudato Tipo: {', '.join(scheda.get('essudato_tipo', [])) or '-'}", normal_style))
            if scheda.get('medicazione'):
                story.append(Paragraph(f"Medicazione: {scheda.get('medicazione', '-')}", normal_style))
            if scheda.get('prossimo_cambio'):
                story.append(Paragraph(f"Prossimo Cambio: {scheda.get('prossimo_cambio', '-')}", normal_style))
            if scheda.get('firma'):
                story.append(Paragraph(f"Firma Operatore: {scheda.get('firma', '-')}", normal_style))
            story.append(Spacer(1, 15))
        story.append(Spacer(1, 10))
    
    # SEZIONE IMPIANTO PICC - show for 'all' and 'impianto' (only complete)
    if section in ["all", "impianto"]:
        schede_complete = [s for s in schede_impianto if s.get('scheda_type') == 'completa']
        if schede_complete:
            story.append(Paragraph("Schede Impianto PICC (Complete)", heading_style))
            
            for idx, scheda in enumerate(schede_complete, 1):
                if idx > 1:
                    from reportlab.platypus import PageBreak
                    story.append(PageBreak())
                
                story.append(Paragraph(f"<b>Scheda Impianto #{idx}</b>", normal_style))
                story.append(Spacer(1, 10))
                
                def cb(checked):
                    return "[X]" if checked else "[  ]"
                
                def get_scheda_val(key, default=""):
                    val = scheda.get(key)
                    return default if val is None else val
                
                # Header info
                data_impianto = scheda.get('data_posizionamento') or scheda.get('data_impianto') or '-'
                story.append(Paragraph(f"<b>Data Impianto:</b> {data_impianto}", normal_style))
                story.append(Paragraph(f"<b>Presidio:</b> {get_scheda_val('presidio_ospedaliero', '-')}", normal_style))
                story.append(Paragraph(f"<b>U.O.:</b> {get_scheda_val('unita_operativa', '-')}", normal_style))
                story.append(Spacer(1, 10))
                
                # Tipo catetere
                tipo_opts = [
                    ("cvc_non_tunnellizzato", "CVC non tunnellizzato"),
                    ("cvc_tunnellizzato", "CVC tunnellizzato"),
                    ("picc", "PICC"),
                    ("port", "PORT"),
                    ("midline", "Midline"),
                ]
                tipo = get_scheda_val('tipo_catetere')
                tipo_line = "<b>TIPO DI CATETERE:</b> " + "  ".join([f"{cb(tipo == opt[0])} {opt[1]}" for opt in tipo_opts])
                story.append(Paragraph(tipo_line, normal_style))
                
                # Posizionamento
                braccio = get_scheda_val('braccio')
                vena = get_scheda_val('vena')
                pos_line = f"<b>POSIZIONAMENTO:</b> {cb(braccio == 'dx')} Braccio Dx  {cb(braccio == 'sn')} Braccio Sn    "
                pos_line += f"<b>Vena:</b> {cb(vena == 'basilica')} Basilica  {cb(vena == 'cefalica')} Cefalica  {cb(vena == 'brachiale')} Brachiale"
                story.append(Paragraph(pos_line, normal_style))
                story.append(Paragraph(f"<b>Exit-site:</b> {get_scheda_val('exit_site_cm', '-')} cm", normal_style))
                story.append(Spacer(1, 8))
                
                # Procedure con checkbox SI/NO
                procedures = [
                    ('valutazione_sito', 'VALUTAZIONE MIGLIOR SITO DI INSERIMENTO'),
                    ('ecoguidato', 'IMPIANTO ECOGUIDATO'),
                    ('igiene_mani', 'IGIENE DELLE MANI'),
                    ('precauzioni_barriera', 'UTILIZZO MASSIME PRECAUZIONI DI BARRIERA'),
                ]
                for key, label in procedures:
                    val = get_scheda_val(key)
                    line = f"<b>{label}:</b>  {cb(val == True)} SI  {cb(val == False)} NO"
                    story.append(Paragraph(line, normal_style))
                
                # Disinfezione
                disinfezione = get_scheda_val('disinfezione') or []
                dis_line = f"<b>DISINFEZIONE:</b>  {cb('clorexidina_2' in disinfezione)} Clorexidina 2%  {cb('iodiopovidone' in disinfezione)} Iodiopovidone"
                story.append(Paragraph(dis_line, normal_style))
                
                # Dispositivi
                dispositivi = [
                    ('sutureless_device', 'SUTURELESS DEVICE'),
                    ('medicazione_trasparente', 'MEDICAZIONE TRASPARENTE'),
                    ('medicazione_occlusiva', 'MEDICAZIONE OCCLUSIVA'),
                    ('controllo_rx', 'CONTROLLO RX POST-INSERIMENTO'),
                    ('controllo_ecg', 'CONTROLLO ECG POST-INSERIMENTO'),
                ]
                for key, label in dispositivi:
                    val = get_scheda_val(key)
                    line = f"<b>{label}:</b>  {cb(val == True)} SI  {cb(val == False)} NO"
                    story.append(Paragraph(line, normal_style))
                
                # Modalità
                modalita = get_scheda_val('modalita')
                mod_line = f"<b>MODALITÀ:</b>  {cb(modalita == 'emergenza')} EMERGENZA  {cb(modalita == 'urgenza')} URGENZA  {cb(modalita == 'elezione')} ELEZIONE"
                story.append(Paragraph(mod_line, normal_style))
                
                # Motivazione
                motivazione = get_scheda_val('motivazione') or []
                motiv_opts = [("chemioterapia", "Chemioterapia"), ("difficolta_vene", "Difficoltà vene"), 
                              ("terapia_prolungata", "Terapia prolungata"), ("monitoraggio", "Monitoraggio")]
                motiv_line = "<b>MOTIVAZIONE:</b>  " + "  ".join([f"{cb(m[0] in motivazione)} {m[1]}" for m in motiv_opts])
                story.append(Paragraph(motiv_line, normal_style))
                
                # Operatore
                story.append(Spacer(1, 8))
                story.append(Paragraph(f"<b>OPERATORE:</b> {get_scheda_val('operatore', '-')}", normal_style))
                
                if scheda.get('note'):
                    story.append(Paragraph(f"<b>Note:</b> {scheda.get('note', '')}", normal_style))
                
                story.append(Spacer(1, 15))
            story.append(Spacer(1, 10))
        
        # Gestione PICC (monthly)
        if schede_gestione:
            story.append(Spacer(1, 20))
            story.append(Paragraph("Schede Gestione PICC (Accessi Venosi)", heading_style))
            
            gestione_items = [
                ("data_giorno_mese", "Data (giorno/mese)"),
                ("uso_precauzioni_barriera", "Uso massime precauzioni barriera"),
                ("lavaggio_mani", "Lavaggio mani"),
                ("guanti_non_sterili", "Uso guanti non sterili"),
                ("cambio_guanti_sterili", "Cambio guanti con guanti sterili"),
                ("rimozione_medicazione_sutureless", "Rimozione medicazione e sostituzione sutureless"),
                ("rimozione_medicazione_straordinaria", "Rimozione medicazione ord/straordinaria"),
                ("ispezione_sito", "Ispezione del sito"),
                ("sito_dolente", "Sito dolente"),
                ("edema_arrossamento", "Presenza di edema/arrossamento"),
                ("disinfezione_sito", "Disinfezione del sito"),
                ("exit_site_cm", "Exit-site cm"),
                ("fissaggio_sutureless", "Fissaggio catetere con sutureless device"),
                ("medicazione_trasparente", "Medicazione semipermeabile trasparente"),
                ("lavaggio_fisiologica", "Lavaggio con fisiologica 10cc/20cc"),
                ("disinfezione_clorexidina", "Disinfezione Clorexidina 2%"),
                ("difficolta_aspirazione", "Difficoltà di aspirazione"),
                ("difficolta_iniezione", "Difficoltà iniezione"),
                ("medicazione_clorexidina_prolungato", "Medicazione Clorexidina rilascio prol."),
                ("port_protector", "Utilizzo Port Protector"),
                ("lock_eparina", "Lock eparina per lavaggi"),
                ("sostituzione_set", "Sostituzione set infusione"),
                ("ore_sostituzione_set", "Ore da precedente sostituzione set"),
                ("febbre", "Febbre"),
                ("emocoltura", "Prelievo emocoltura"),
                ("emocoltura_positiva", "Emocoltura positiva per CVC"),
                ("trasferimento", "Trasferimento altra struttura"),
                ("rimozione_cvc", "Rimozione CVC"),
                ("sigla_operatore", "SIGLA OPERATORE"),
            ]
            
            for scheda in schede_gestione:
                story.append(Paragraph(f"<b>Mese: {scheda.get('mese', '-')}</b>", normal_style))
                giorni = scheda.get('giorni', {})
                
                if giorni:
                    sorted_dates = sorted(giorni.keys())
                    
                    for chunk_start in range(0, len(sorted_dates), 10):
                        chunk_dates = sorted_dates[chunk_start:chunk_start + 10]
                        header_row = ["Attività"] + [d.split("-")[-1] for d in chunk_dates]
                        table_data = [header_row]
                        
                        for item_id, item_label in gestione_items:
                            row = [item_label]
                            for date_str in chunk_dates:
                                val = giorni.get(date_str, {}).get(item_id, "-")
                                row.append(val if val else "-")
                            table_data.append(row)
                        
                        col_widths = [5*cm] + [1.2*cm] * len(chunk_dates)
                        table = Table(table_data, colWidths=col_widths)
                        table.setStyle(TableStyle([
                            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                            ('FONTNAME', (0, 1), (0, -1), 'Helvetica'),
                            ('FONTSIZE', (0, 0), (-1, -1), 6),
                            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#166534')),
                            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                            ('ALIGN', (1, 0), (-1, -1), 'CENTER'),
                            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                            ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
                            ('TOPPADDING', (0, 0), (-1, -1), 2),
                            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f0f0f0')]),
                        ]))
                        story.append(table)
                        story.append(Spacer(1, 10))
                    
                    if scheda.get('note'):
                        story.append(Paragraph(f"<b>Note:</b> {scheda.get('note', '')}", normal_style))
                else:
                    story.append(Paragraph("Nessuna medicazione registrata per questo mese.", normal_style))
                
                story.append(Spacer(1, 15))
    
    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()


def generate_patient_pdf(patient: dict, schede_med: list, schede_impianto: list, schede_gestione: list, photos: list) -> bytes:
    """Generate a PDF with patient data - NO allegati, NO foto in scheda MED, only COMPLETE scheda impianto"""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=2*cm, leftMargin=2*cm, topMargin=2*cm, bottomMargin=2*cm)
    
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle('CustomTitle', parent=styles['Heading1'], fontSize=18, spaceAfter=30, alignment=TA_CENTER)
    heading_style = ParagraphStyle('CustomHeading', parent=styles['Heading2'], fontSize=14, spaceAfter=12, textColor=colors.HexColor('#1e40af'))
    normal_style = ParagraphStyle('CustomNormal', parent=styles['Normal'], fontSize=11, spaceAfter=6)
    
    story = []
    
    # Title
    story.append(Paragraph(f"Cartella Clinica - {patient.get('cognome', '')} {patient.get('nome', '')}", title_style))
    story.append(Spacer(1, 20))
    
    # SEZIONE 1: Dati Anagrafici
    story.append(Paragraph("Dati Anagrafici", heading_style))
    info_data = [
        ["Nome:", patient.get('nome', '-')],
        ["Cognome:", patient.get('cognome', '-')],
        ["Tipo:", patient.get('tipo', '-')],
        ["Codice Fiscale:", patient.get('codice_fiscale', '-')],
        ["Data di Nascita:", patient.get('data_nascita', '-')],
        ["Sesso:", patient.get('sesso', '-')],
        ["Telefono:", patient.get('telefono', '-')],
        ["Email:", patient.get('email', '-')],
        ["Medico di Base:", patient.get('medico_base', '-')],
        ["Stato:", patient.get('status', '-')],
    ]
    table = Table(info_data, colWidths=[4*cm, 12*cm])
    table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
    ]))
    story.append(table)
    story.append(Spacer(1, 20))
    
    # SEZIONE 2: Anamnesi
    if patient.get('anamnesi') or patient.get('terapia_in_atto') or patient.get('allergie'):
        story.append(Paragraph("Anamnesi", heading_style))
        if patient.get('anamnesi'):
            story.append(Paragraph(f"<b>Anamnesi:</b> {patient.get('anamnesi', '-')}", normal_style))
        if patient.get('terapia_in_atto'):
            story.append(Paragraph(f"<b>Terapia in Atto:</b> {patient.get('terapia_in_atto', '-')}", normal_style))
        if patient.get('allergie'):
            story.append(Paragraph(f"<b>Allergie:</b> {patient.get('allergie', '-')}", normal_style))
        story.append(Spacer(1, 20))
    
    # SEZIONE 3: Schede Medicazione MED (senza anagrafica, senza foto)
    if schede_med:
        story.append(Paragraph("Schede Medicazione MED", heading_style))
        for idx, scheda in enumerate(schede_med, 1):
            story.append(Paragraph(f"<b>Medicazione #{idx} - Data: {scheda.get('data_compilazione', '-')}</b>", normal_style))
            story.append(Paragraph(f"Fondo: {', '.join(scheda.get('fondo', [])) or '-'}", normal_style))
            story.append(Paragraph(f"Margini: {', '.join(scheda.get('margini', [])) or '-'}", normal_style))
            story.append(Paragraph(f"Cute perilesionale: {', '.join(scheda.get('cute_perilesionale', [])) or '-'}", normal_style))
            story.append(Paragraph(f"Essudato Quantità: {scheda.get('essudato_quantita', '-')}", normal_style))
            story.append(Paragraph(f"Essudato Tipo: {', '.join(scheda.get('essudato_tipo', [])) or '-'}", normal_style))
            if scheda.get('medicazione'):
                story.append(Paragraph(f"Medicazione: {scheda.get('medicazione', '-')}", normal_style))
            if scheda.get('prossimo_cambio'):
                story.append(Paragraph(f"Prossimo Cambio: {scheda.get('prossimo_cambio', '-')}", normal_style))
            if scheda.get('firma'):
                story.append(Paragraph(f"Firma Operatore: {scheda.get('firma', '-')}", normal_style))
            # NOTE: NO foto qui - le foto rimangono solo nell'applicativo
            story.append(Spacer(1, 15))
        story.append(Spacer(1, 10))
    
    # SEZIONE 4: Schede Impianto PICC - SOLO schede COMPLETE nel formato ufficiale
    schede_complete = [s for s in schede_impianto if s.get('scheda_type') == 'completa']
    if schede_complete:
        story.append(Paragraph("Schede Impianto PICC (Complete)", heading_style))
        
        for idx, scheda in enumerate(schede_complete, 1):
            # Aggiungi PageBreak se non è la prima scheda
            if idx > 1:
                story.append(PageBreak())
            
            # Usa lo stesso formato del PDF singolo
            story.append(Paragraph(f"<b>Scheda Impianto #{idx}</b>", normal_style))
            story.append(Spacer(1, 10))
            
            # Helper functions for this scheda
            def cb(checked):
                if checked:
                    return "[X]"
                else:
                    return "[  ]"
            
            def get_scheda_val(key, default=""):
                val = scheda.get(key)
                if val is None:
                    return default
                return val
            
            # Header info
            data_impianto = scheda.get('data_posizionamento') or scheda.get('data_impianto') or '-'
            story.append(Paragraph(f"<b>Data Impianto:</b> {data_impianto}", normal_style))
            story.append(Paragraph(f"<b>Presidio:</b> {get_scheda_val('presidio_ospedaliero', '-')}", normal_style))
            story.append(Paragraph(f"<b>U.O.:</b> {get_scheda_val('unita_operativa', '-')}", normal_style))
            story.append(Spacer(1, 10))
            
            # Tipo catetere
            tipo_opts = [
                ("cvc_non_tunnellizzato", "CVC non tunnellizzato"),
                ("cvc_tunnellizzato", "CVC tunnellizzato"),
                ("picc", "PICC"),
                ("port", "PORT"),
                ("midline", "Midline"),
            ]
            tipo = get_scheda_val('tipo_catetere')
            tipo_line = "<b>TIPO DI CATETERE:</b> " + "  ".join([f"{cb(tipo == opt[0])} {opt[1]}" for opt in tipo_opts])
            story.append(Paragraph(tipo_line, normal_style))
            
            # Posizionamento
            braccio = get_scheda_val('braccio')
            vena = get_scheda_val('vena')
            pos_line = f"<b>POSIZIONAMENTO:</b> {cb(braccio == 'dx')} Braccio Dx  {cb(braccio == 'sn')} Braccio Sn    "
            pos_line += f"<b>Vena:</b> {cb(vena == 'basilica')} Basilica  {cb(vena == 'cefalica')} Cefalica  {cb(vena == 'brachiale')} Brachiale"
            story.append(Paragraph(pos_line, normal_style))
            story.append(Paragraph(f"<b>Exit-site:</b> {get_scheda_val('exit_site_cm', '-')} cm", normal_style))
            story.append(Spacer(1, 8))
            
            # Procedure con checkbox SI/NO
            procedures = [
                ('valutazione_sito', 'VALUTAZIONE MIGLIOR SITO DI INSERIMENTO'),
                ('ecoguidato', 'IMPIANTO ECOGUIDATO'),
                ('igiene_mani', 'IGIENE DELLE MANI'),
                ('precauzioni_barriera', 'UTILIZZO MASSIME PRECAUZIONI DI BARRIERA'),
            ]
            for key, label in procedures:
                val = get_scheda_val(key)
                line = f"<b>{label}:</b>  {cb(val == True)} SI  {cb(val == False)} NO"
                story.append(Paragraph(line, normal_style))
            
            # Disinfezione
            disinfezione = get_scheda_val('disinfezione') or []
            dis_line = f"<b>DISINFEZIONE:</b>  {cb('clorexidina_2' in disinfezione)} Clorexidina 2%  {cb('iodiopovidone' in disinfezione)} Iodiopovidone"
            story.append(Paragraph(dis_line, normal_style))
            
            # Dispositivi
            dispositivi = [
                ('sutureless_device', 'SUTURELESS DEVICE'),
                ('medicazione_trasparente', 'MEDICAZIONE TRASPARENTE'),
                ('medicazione_occlusiva', 'MEDICAZIONE OCCLUSIVA'),
                ('controllo_rx', 'CONTROLLO RX POST-INSERIMENTO'),
                ('controllo_ecg', 'CONTROLLO ECG POST-INSERIMENTO'),
            ]
            for key, label in dispositivi:
                val = get_scheda_val(key)
                line = f"<b>{label}:</b>  {cb(val == True)} SI  {cb(val == False)} NO"
                story.append(Paragraph(line, normal_style))
            
            # Modalità
            modalita = get_scheda_val('modalita')
            mod_line = f"<b>MODALITÀ:</b>  {cb(modalita == 'emergenza')} EMERGENZA  {cb(modalita == 'urgenza')} URGENZA  {cb(modalita == 'elezione')} ELEZIONE"
            story.append(Paragraph(mod_line, normal_style))
            
            # Motivazione
            motivazione = get_scheda_val('motivazione') or []
            motiv_opts = [("chemioterapia", "Chemioterapia"), ("difficolta_vene", "Difficoltà vene"), 
                          ("terapia_prolungata", "Terapia prolungata"), ("monitoraggio", "Monitoraggio")]
            motiv_line = "<b>MOTIVAZIONE:</b>  " + "  ".join([f"{cb(m[0] in motivazione)} {m[1]}" for m in motiv_opts])
            story.append(Paragraph(motiv_line, normal_style))
            
            # Operatore
            story.append(Spacer(1, 8))
            story.append(Paragraph(f"<b>OPERATORE:</b> {get_scheda_val('operatore', '-')}", normal_style))
            
            if scheda.get('note'):
                story.append(Paragraph(f"<b>Note:</b> {scheda.get('note', '')}", normal_style))
            
            story.append(Spacer(1, 15))
        story.append(Spacer(1, 10))
    
    # PICC Gestione Schede (Monthly Management)
    if schede_gestione:
        story.append(Spacer(1, 20))
        story.append(Paragraph("Schede Gestione PICC (Accessi Venosi)", heading_style))
        
        # Define the items to display
        gestione_items = [
            ("data_giorno_mese", "Data (giorno/mese)"),
            ("uso_precauzioni_barriera", "Uso massime precauzioni barriera"),
            ("lavaggio_mani", "Lavaggio mani"),
            ("guanti_non_sterili", "Uso guanti non sterili"),
            ("cambio_guanti_sterili", "Cambio guanti con guanti sterili"),
            ("rimozione_medicazione_sutureless", "Rimozione medicazione e sostituzione sutureless"),
            ("rimozione_medicazione_straordinaria", "Rimozione medicazione ord/straordinaria"),
            ("ispezione_sito", "Ispezione del sito"),
            ("sito_dolente", "Sito dolente"),
            ("edema_arrossamento", "Presenza di edema/arrossamento"),
            ("disinfezione_sito", "Disinfezione del sito"),
            ("exit_site_cm", "Exit-site cm"),
            ("fissaggio_sutureless", "Fissaggio catetere con sutureless device"),
            ("medicazione_trasparente", "Medicazione semipermeabile trasparente"),
            ("lavaggio_fisiologica", "Lavaggio con fisiologica 10cc/20cc"),
            ("disinfezione_clorexidina", "Disinfezione Clorexidina 2%"),
            ("difficolta_aspirazione", "Difficoltà di aspirazione"),
            ("difficolta_iniezione", "Difficoltà iniezione"),
            ("medicazione_clorexidina_prolungato", "Medicazione Clorexidina rilascio prol."),
            ("port_protector", "Utilizzo Port Protector"),
            ("lock_eparina", "Lock eparina per lavaggi"),
            ("sostituzione_set", "Sostituzione set infusione"),
            ("ore_sostituzione_set", "Ore da precedente sostituzione set"),
            ("febbre", "Febbre"),
            ("emocoltura", "Prelievo emocoltura"),
            ("emocoltura_positiva", "Emocoltura positiva per CVC"),
            ("trasferimento", "Trasferimento altra struttura"),
            ("rimozione_cvc", "Rimozione CVC"),
            ("sigla_operatore", "SIGLA OPERATORE"),
        ]
        
        for scheda in schede_gestione:
            story.append(Paragraph(f"<b>Mese: {scheda.get('mese', '-')}</b>", normal_style))
            giorni = scheda.get('giorni', {})
            
            if giorni:
                # Sort dates
                sorted_dates = sorted(giorni.keys())
                num_cols = min(len(sorted_dates), 10)  # Max 10 columns per table for readability
                
                # Split into chunks if more than 10 dates
                for chunk_start in range(0, len(sorted_dates), 10):
                    chunk_dates = sorted_dates[chunk_start:chunk_start + 10]
                    
                    # Build header row
                    header_row = ["Attività"] + [d.split("-")[-1] for d in chunk_dates]  # Show day number
                    
                    # Build data rows
                    table_data = [header_row]
                    for item_id, item_label in gestione_items:
                        row = [item_label]
                        for date_str in chunk_dates:
                            val = giorni.get(date_str, {}).get(item_id, "-")
                            row.append(val if val else "-")
                        table_data.append(row)
                    
                    # Create table
                    col_widths = [5*cm] + [1.2*cm] * len(chunk_dates)
                    table = Table(table_data, colWidths=col_widths)
                    table.setStyle(TableStyle([
                        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                        ('FONTNAME', (0, 1), (0, -1), 'Helvetica'),
                        ('FONTSIZE', (0, 0), (-1, -1), 6),
                        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#166534')),
                        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                        ('ALIGN', (1, 0), (-1, -1), 'CENTER'),
                        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
                        ('TOPPADDING', (0, 0), (-1, -1), 2),
                        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f0f0f0')]),
                    ]))
                    story.append(table)
                    story.append(Spacer(1, 10))
                
                # Add notes if present
                if scheda.get('note'):
                    story.append(Paragraph(f"<b>Note:</b> {scheda.get('note', '')}", normal_style))
            else:
                story.append(Paragraph("Nessuna medicazione registrata per questo mese.", normal_style))
            
            story.append(Spacer(1, 15))
    
    # NOTE: Allegati section removed from PDF download as per user request
    # Gli allegati NON vengono scaricati con la cartella paziente
    
    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()


def generate_patient_zip(patient: dict, schede_med: list, schede_impianto: list, schede_gestione: list, photos: list) -> bytes:
    """Generate a ZIP with patient data - NO allegati, only PDF cartella clinica"""
    buffer = io.BytesIO()
    
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
        # Add PDF summary (NO allegati, NO foto MED)
        pdf_data = generate_patient_pdf(patient, schede_med, schede_impianto, schede_gestione, [])
        zf.writestr(f"cartella_clinica_{patient.get('cognome', 'paziente')}_{patient.get('nome', '')}.pdf", pdf_data)
        
        # Add patient JSON data
        import json
        patient_json = json.dumps(patient, indent=2, ensure_ascii=False)
        zf.writestr("dati_paziente.json", patient_json)
        
        # Add MED schede as JSON (without photos)
        if schede_med:
            med_json = json.dumps(schede_med, indent=2, ensure_ascii=False)
            zf.writestr("schede_medicazione_med.json", med_json)
        
        # Add only COMPLETE PICC impianto schede as JSON (no semplificata)
        schede_complete = [s for s in schede_impianto if s.get('scheda_type') != 'semplificata']
        if schede_complete:
            impianto_json = json.dumps(schede_complete, indent=2, ensure_ascii=False)
            zf.writestr("schede_impianto_picc.json", impianto_json)
        
        # Add PICC gestione schede as JSON
        if schede_gestione:
            gestione_json = json.dumps(schede_gestione, indent=2, ensure_ascii=False)
            zf.writestr("schede_gestione_picc.json", gestione_json)
        
        # NOTE: NO allegati nel ZIP - si scaricano singolarmente
    
    buffer.seek(0)
    return buffer.getvalue()


@api_router.get("/patients/{patient_id}/download/pdf")
async def download_patient_pdf(patient_id: str, section: str = "all", payload: dict = Depends(verify_token)):
    """Download patient folder as PDF - with optional section filter
    section: 'all', 'anagrafica', 'medicazione', 'impianto', 'gestione'
    """
    patient = await db.patients.find_one({"id": patient_id}, {"_id": 0})
    if not patient:
        raise HTTPException(status_code=404, detail="Paziente non trovato")
    if patient["ambulatorio"] not in payload["ambulatori"]:
        raise HTTPException(status_code=403, detail="Non hai accesso a questo ambulatorio")
    
    # Fetch data based on section
    schede_med = []
    schede_impianto = []
    schede_gestione = []
    
    if section in ["all", "medicazione"]:
        schede_med = await db.schede_medicazione_med.find({"patient_id": patient_id}, {"_id": 0}).to_list(1000)
    
    if section in ["all", "impianto"]:
        schede_impianto = await db.schede_impianto_picc.find({"patient_id": patient_id}, {"_id": 0}).to_list(1000)
    
    if section in ["all", "gestione"]:
        schede_gestione = await db.schede_gestione_picc.find({"patient_id": patient_id}, {"_id": 0}).to_list(1000)
    
    # Generate PDF with the appropriate section
    pdf_data = generate_patient_pdf_section(patient, schede_med, schede_impianto, schede_gestione, section)
    
    section_names = {"all": "completa", "anagrafica": "anagrafica", "medicazione": "medicazione", "impianto": "impianto", "gestione": "gestione_picc"}
    section_name = section_names.get(section, section)
    filename = f"cartella_{section_name}_{patient.get('cognome', 'paziente')}_{patient.get('nome', '')}.pdf"
    
    return StreamingResponse(
        io.BytesIO(pdf_data),
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


@api_router.get("/patients/{patient_id}/download/zip")
async def download_patient_zip(patient_id: str, payload: dict = Depends(verify_token)):
    """Download patient folder as ZIP - NO allegati (si scaricano singolarmente)"""
    patient = await db.patients.find_one({"id": patient_id}, {"_id": 0})
    if not patient:
        raise HTTPException(status_code=404, detail="Paziente non trovato")
    if patient["ambulatorio"] not in payload["ambulatori"]:
        raise HTTPException(status_code=403, detail="Non hai accesso a questo ambulatorio")
    
    # Fetch all related data - NO photos (allegati si scaricano separatamente)
    schede_med = await db.schede_medicazione_med.find({"patient_id": patient_id}, {"_id": 0}).to_list(1000)
    schede_impianto = await db.schede_impianto_picc.find({"patient_id": patient_id}, {"_id": 0}).to_list(1000)
    schede_gestione = await db.schede_gestione_picc.find({"patient_id": patient_id}, {"_id": 0}).to_list(1000)
    
    zip_data = generate_patient_zip(patient, schede_med, schede_impianto, schede_gestione, [])
    
    filename = f"cartella_{patient.get('cognome', 'paziente')}_{patient.get('nome', '')}.zip"
    
    return StreamingResponse(
        io.BytesIO(zip_data),
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


# ============== ROOT ==============
@api_router.get("/")
async def root():
    return {"message": "Ambulatorio Infermieristico API", "version": "1.0.0"}

# ============== PRESCRIZIONI ==============
class PrescrizioneCreate(BaseModel):
    patient_id: str
    ambulatorio: Ambulatorio
    data_inizio: str  # YYYY-MM-DD
    durata_mesi: int = 1  # 1, 2, or 3 months

class Prescrizione(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    patient_id: str
    ambulatorio: Ambulatorio
    data_inizio: str
    durata_mesi: int
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

@api_router.get("/prescrizioni")
async def get_prescrizioni(
    ambulatorio: Ambulatorio,
    current_user: dict = Depends(get_current_user)
):
    """Get all prescriptions for an ambulatorio"""
    cursor = db.prescrizioni.find({"ambulatorio": ambulatorio})
    prescrizioni = await cursor.to_list(length=1000)
    result = []
    for p in prescrizioni:
        item = {
            "id": p.get("id", str(p.get("_id", ""))),
            "patient_id": p.get("patient_id"),
            "ambulatorio": p.get("ambulatorio"),
            "data_inizio": p.get("data_inizio"),
            "durata_mesi": p.get("durata_mesi"),
            "created_at": p.get("created_at"),
            "updated_at": p.get("updated_at")
        }
        result.append(item)
    return result

@api_router.post("/prescrizioni")
async def create_or_update_prescrizione(
    data: PrescrizioneCreate,
    current_user: dict = Depends(get_current_user)
):
    """Create or update a prescription for a patient"""
    # Check if prescription already exists for this patient
    existing = await db.prescrizioni.find_one({
        "patient_id": data.patient_id,
        "ambulatorio": data.ambulatorio
    })
    
    if existing:
        # Update existing
        await db.prescrizioni.update_one(
            {"_id": existing["_id"]},
            {
                "$set": {
                    "data_inizio": data.data_inizio,
                    "durata_mesi": data.durata_mesi,
                    "updated_at": datetime.now(timezone.utc).isoformat()
                }
            }
        )
        return {"message": "Prescrizione aggiornata", "id": existing.get("id")}
    else:
        # Create new
        prescrizione = Prescrizione(
            patient_id=data.patient_id,
            ambulatorio=data.ambulatorio,
            data_inizio=data.data_inizio,
            durata_mesi=data.durata_mesi
        )
        await db.prescrizioni.insert_one(prescrizione.model_dump())
        return {"message": "Prescrizione creata", "id": prescrizione.id}

@api_router.delete("/prescrizioni/{patient_id}")
async def delete_prescrizione(
    patient_id: str,
    ambulatorio: Ambulatorio,
    current_user: dict = Depends(get_current_user)
):
    """Delete a prescription for a patient"""
    result = await db.prescrizioni.delete_one({
        "patient_id": patient_id,
        "ambulatorio": ambulatorio
    })
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Prescrizione non trovata")
    return {"message": "Prescrizione eliminata"}

# Include the router in the main app
app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
