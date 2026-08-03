"""Hasta (patient) CRUD uçları (audit B-2.2: api_server.py'den ayrıldı — modüler router).
Yalnız `database.patient_database`'e bağlı; paylaşılan donanım/seans/live-state'i KULLANMAZ.
Yollar birebir korunur (/api/patients...) → istemci sözleşmesi değişmez (pagination + delete_all guard dahil)."""
import logging
import os

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from database.patient_database import get_patient_database

router = APIRouter(tags=["patients"])
logger = logging.getLogger("patient_router")


def _enforce_patient_auth(request: Request) -> None:
    """Audit P2: PEMF_REQUIRE_PATIENT_AUTH=1 iken hasta PII/yazma/silme uclarinda LAN-muafiyetini
    KALDIR — operator token zorunlu (ayni-WiFi misafir/IoT tum PII'yi dokup silmesin). VARSAYILAN
    KAPALI: mobil app LAN'da token'siz erisiyor; deployment token dagitip acabilir (geriye-uyumlu)."""
    if os.getenv("PEMF_REQUIRE_PATIENT_AUTH", "0") != "1":
        return
    try:
        from servers.auth import check_token
    except Exception:
        raise HTTPException(status_code=503, detail="Auth altyapisi kullanilamiyor")
    tok = request.headers.get("X-API-Key") or request.query_params.get("token") or ""
    if not check_token(tok):
        raise HTTPException(status_code=401, detail="Operator token gerekli (hasta verisi korumali).")


class PatientInput(BaseModel):
    id: str = ""
    name: str = ""
    species: str = ""
    breed: str = ""
    age: str = ""
    weight: str = ""
    owner: str = ""
    vet_contact: str = ""
    owner_email: str = ""  # hasta sahibinin e-postasi (rapor gonderimi icin)
    operator_email: str = ""  # kaydi olusturan hekimin e-postasi (klinik-ici "benim hastalarim" filtresi; add'de set, update'te yok sayilir)


class DeleteAllPayload(BaseModel):
    confirm: str = ""  # audit B-8.2: kazara toplu-silme koruması


@router.get("/api/patients")
def get_all_patients(request: Request, limit: int = 0, offset: int = 0):
    """Hastaları döndürür. Pagination (audit B-8.2): limit>0 ile sayfalanır (offset kaydırır);
    limit=0 → HEPSİ (geriye uyumlu — eski istemci parametre göndermez). Yanıt: {status,data,total}."""
    _enforce_patient_auth(request)
    db = get_patient_database()
    if not db:
        raise HTTPException(status_code=500, detail="Patient DB not initialized")
    # DENETIM P2: eskiden TUM hastalar cekilip (hepsinin alan-basi Fernet desifresi yapilarak,
    # DB kilidi tutularak) sonra Python'da dilimleniyordu → limit=20 istegi bile binlerce
    # kayitlik klinikte tum tabloyu desifre ediyor ve o sure boyunca hasta-DB'sini blokluyordu.
    # Sayfalama artik SQL'de; 'total' ise desifre gerektirmeyen COUNT ile alinir.
    off = max(0, offset)
    data = db.get_all_patients(limit=limit, offset=off)
    total = db.count_patients()
    return {"status": "success", "data": data, "total": total}


@router.post("/api/patients")
def add_new_patient(patient: PatientInput, request: Request):
    """Yeni hasta ekler veya id verilirse mevcut hastayı günceller."""
    _enforce_patient_auth(request)
    db = get_patient_database()
    if not db:
        raise HTTPException(status_code=500, detail="Patient DB not initialized")
    payload = patient.dict()
    patient_id = payload.pop("id", "") or ""
    if patient_id:
        success = db.update_patient(patient_id, payload)
        return {"status": "success" if success else "error", "patient_id": patient_id}
    patient_id = db.add_patient(payload)
    return {"status": "success", "patient_id": patient_id}


@router.delete("/api/patients/{patient_id}")
def remove_patient(patient_id: str, request: Request):
    """Hasta siler"""
    _enforce_patient_auth(request)
    db = get_patient_database()
    success = db.delete_patient(patient_id)
    return {"status": "success" if success else "error"}


@router.post("/api/patients/{patient_id}/delete")
def remove_patient_compat(patient_id: str, request: Request):
    """Backward-compatible delete route used by the current Expo app."""
    return remove_patient(patient_id, request)


@router.post("/api/patients/delete_all")
def remove_all_patients(request: Request, payload: DeleteAllPayload = DeleteAllPayload()):
    """TÜM hastaları siler — KORUMALI (audit B-8.2): gövdede {"confirm":"DELETE_ALL"} ZORUNLU.
    Eskiden boş POST tüm hastaları geri-dönülemez siliyordu (yalnız middleware auth). Yanlış-tık/
    otomatik-istek koruması; frontend confirm gönderir."""
    _enforce_patient_auth(request)
    if payload.confirm != "DELETE_ALL":
        raise HTTPException(status_code=400,
                            detail="Toplu silme için onay gerekli: gövdede {\"confirm\":\"DELETE_ALL\"} gönderin.")
    db = get_patient_database()
    if not db:
        raise HTTPException(status_code=500, detail="Patient DB not initialized")
    # Audit P3: atomik clear_all_patients() (DELETE + commit + VACUUM) — eskiden get_all + tek-tek
    # delete (atomik DEĞİL, VACUUM yok → silinen PII freelist'te kurtarılabilir kalıyordu; 300.'de
    # hata → tutarsız durum). count'u silmeden önce al (response doğru olsun).
    count = len(db.get_all_patients())
    ok = db.clear_all_patients()
    logging.getLogger(__name__).warning("TOPLU HASTA SİLME uygulandı (atomik+VACUUM, %d hasta).", count)
    return {"status": "success" if ok else "error", "deleted": count}
