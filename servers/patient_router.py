"""Hasta (patient) CRUD uçları (audit B-2.2: api_server.py'den ayrıldı — modüler router).
Yalnız `database.patient_database`'e bağlı; paylaşılan donanım/seans/live-state'i KULLANMAZ.
Yollar birebir korunur (/api/patients...) → istemci sözleşmesi değişmez (pagination + delete_all guard dahil)."""
import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from database.patient_database import get_patient_database

router = APIRouter(tags=["patients"])
logger = logging.getLogger("patient_router")


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


class DeleteAllPayload(BaseModel):
    confirm: str = ""  # audit B-8.2: kazara toplu-silme koruması


@router.get("/api/patients")
def get_all_patients(limit: int = 0, offset: int = 0):
    """Hastaları döndürür. Pagination (audit B-8.2): limit>0 ile sayfalanır (offset kaydırır);
    limit=0 → HEPSİ (geriye uyumlu — eski istemci parametre göndermez). Yanıt: {status,data,total}."""
    db = get_patient_database()
    if not db:
        raise HTTPException(status_code=500, detail="Patient DB not initialized")
    all_patients = db.get_all_patients()
    total = len(all_patients)
    off = max(0, offset)
    data = all_patients[off:off + limit] if limit and limit > 0 else all_patients[off:]
    return {"status": "success", "data": data, "total": total}


@router.post("/api/patients")
def add_new_patient(patient: PatientInput):
    """Yeni hasta ekler veya id verilirse mevcut hastayı günceller."""
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
def remove_patient(patient_id: str):
    """Hasta siler"""
    db = get_patient_database()
    success = db.delete_patient(patient_id)
    return {"status": "success" if success else "error"}


@router.post("/api/patients/{patient_id}/delete")
def remove_patient_compat(patient_id: str):
    """Backward-compatible delete route used by the current Expo app."""
    return remove_patient(patient_id)


@router.post("/api/patients/delete_all")
def remove_all_patients(payload: DeleteAllPayload = DeleteAllPayload()):
    """TÜM hastaları siler — KORUMALI (audit B-8.2): gövdede {"confirm":"DELETE_ALL"} ZORUNLU.
    Eskiden boş POST tüm hastaları geri-dönülemez siliyordu (yalnız middleware auth). Yanlış-tık/
    otomatik-istek koruması; frontend confirm gönderir."""
    if payload.confirm != "DELETE_ALL":
        raise HTTPException(status_code=400,
                            detail="Toplu silme için onay gerekli: gövdede {\"confirm\":\"DELETE_ALL\"} gönderin.")
    db = get_patient_database()
    if not db:
        raise HTTPException(status_code=500, detail="Patient DB not initialized")
    patients = db.get_all_patients()
    for p in patients:
        db.delete_patient(p.get("id"))
    logging.getLogger(__name__).warning("TOPLU HASTA SİLME uygulandı (%d hasta).", len(patients))
    return {"status": "success", "deleted": len(patients)}
