import csv
import io
import logging
import os
import time
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel
from starlette.background import BackgroundTask

from database.treatment_history_db import get_treatment_db
from utils.path_utils import get_app_data_directory
from utils.pdf_report_generator import get_pdf_generator

router = APIRouter(prefix="/api/history", tags=["history"])
logger = logging.getLogger("HistoryRouter")


class HistoryDeletePayload(BaseModel):
    session_id: int

# Canonical veri klasörü — api_server (gözlem-notu/KPI/AI-log) ile AYNI olmalı,
# yoksa yazıcı/okuyucu farklı DB dosyalarına düşer (split-brain → geçmiş boş görünür).
_app_data_dir = get_app_data_directory()
_REPORTS_DIR = _app_data_dir / "temp_reports"

def _safe_unlink(path):
    """P1 audit 2026-06-28: rapor PDF'i (tam hasta PII) gonderildikten SONRA sil — at-rest
    SQLCipher korumasini diskteki duz-metin PDF ile baypas etmesin."""
    try:
        os.remove(path)
    except Exception:
        pass

def _purge_old_reports(max_age_sec: int = 3600):
    """temp_reports/ icindeki >1 saatlik orphan PDF'leri sil (crash/eski surum kalintilari).
    FileResponse BackgroundTask normal akisi temizler; bu yalniz orphanlar icindir."""
    try:
        if not _REPORTS_DIR.exists():
            return
        now = time.time()
        for f in _REPORTS_DIR.glob("*.pdf"):
            try:
                if now - f.stat().st_mtime > max_age_sec:
                    f.unlink()
            except Exception:
                pass
    except Exception:
        pass

_purge_old_reports()  # import-zamani orphan temizligi


def get_db():
    return get_treatment_db(_app_data_dir)

def get_pdf_gen():
    return get_pdf_generator(_app_data_dir)

@router.get("/")
def get_history(limit: int = 100, cursor: int = None, db=Depends(get_db)):
    """Seans geçmişini listele (audit B-8.2: keyset/cursor pagination).

    - `limit`: sayfa boyutu (varsayılan 100).
    - `cursor`: bir önceki sayfanın SON öğesinin `id`'si → ondan ESKİ seanslar (sonraki sayfa).
      Verilmezse en yeni `limit` seans döner (ilk sayfa). "Sonraki sayfa var mı" = dönen kayıt == limit.
    Geriye uyumlu: eski istemci `cursor` göndermez → eski davranış (en yeni `limit`)."""
    try:
        sessions = db.get_session_history(limit=limit, before_id=cursor)
        return sessions
    except Exception as e:
        logger.error(f"Error fetching history: {e}")
        raise HTTPException(status_code=500, detail="İşlem başarısız")

@router.get("/statistics")
def get_statistics(db=Depends(get_db)):
    """Klinik tedavi istatistiklerini getir"""
    try:
        stats = db.get_statistics()
        return stats
    except Exception as e:
        logger.error(f"Error fetching statistics: {e}")
        raise HTTPException(status_code=500, detail="İşlem başarısız")

@router.get("/export_pdf")
def export_pdf(session_ids: str = Query(..., description="Virgülle ayrılmış session id listesi. Örn: 1,2,3"), 
               pdf_gen=Depends(get_pdf_gen)):
    """Seçili seanslar için PDF raporu oluşturup indir"""
    try:
        id_list = [int(sid.strip()) for sid in session_ids.split(",")]
        # PDF'i tmp bir yere üret
        tmp_dir = _app_data_dir / "temp_reports"
        tmp_dir.mkdir(exist_ok=True)
        _purge_old_reports()
        out_path = str(tmp_dir / f"report_{id_list[0]}_{int(time.time()*1000)}.pdf")
        
        pdf_path = pdf_gen.generate_session_report(session_ids=id_list, output_path=out_path)
        
        return FileResponse(
            path=pdf_path, 
            media_type='application/pdf', 
            filename="PEMF_Report.pdf",
            background=BackgroundTask(_safe_unlink, pdf_path),  # P1 audit: gonderim sonrasi PII PDF'i sil
        )
    except Exception as e:
        logger.error(f"Error generating PDF: {e}")
        raise HTTPException(status_code=500, detail="İşlem başarısız")

@router.get("/export_csv")
def export_csv(db=Depends(get_db)):
    """Tüm seans geçmişini CSV olarak indir"""
    try:
        sessions = db.get_session_history(limit=10000)
        if not sessions:
            return Response(content="Veri bulunamadi", media_type="text/plain")
            
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Headers
        headers = ["ID", "Hasta", "Hedef", "Mod", "Sure(dk)", "Frekans(Hz)", "Siddet(mT)", "Tarih", "Baslangic", "Durum", "Notlar"]
        writer.writerow(headers)
        
        for s in sessions:
            writer.writerow([
                s.get("id", ""),
                s.get("patient_name", ""),
                s.get("target_condition", ""),
                s.get("treatment_mode", ""),
                s.get("duration_minutes", ""),
                s.get("frequency_hz", ""),
                s.get("intensity_mt", ""),
                s.get("session_date", ""),
                s.get("start_time", ""),
                s.get("session_status", ""),
                s.get("patient_notes", "")
            ])
            
        csv_data = output.getvalue()
        output.close()

        # Excel (özellikle Türkçe Windows) BOM'suz UTF-8'i sistem codepage'i (Windows-1254)
        # sanıp Türkçe karakterleri bozuyor. utf-8-sig ile BOM ekleyip charset belirtiyoruz.
        csv_bytes = csv_data.encode("utf-8-sig")

        return Response(
            content=csv_bytes,
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": "attachment; filename=PEMF_History.csv"}
        )
    except Exception as e:
        logger.error(f"Error generating CSV: {e}")
        raise HTTPException(status_code=500, detail="İşlem başarısız")


@router.get("/export_patient_pdf")
def export_patient_pdf(patient_name: str, pdf_gen=Depends(get_pdf_gen)):
    """Belirli bir hasta için genel PDF raporu oluşturup indir"""
    try:
        tmp_dir = _app_data_dir / "temp_reports"
        tmp_dir.mkdir(exist_ok=True)
        out_path = str(tmp_dir / f"patient_report_{int(time.time()*1000)}.pdf")
        
        pdf_path = pdf_gen.generate_patient_report(patient_name=patient_name, output_path=out_path)
        
        return FileResponse(
            path=pdf_path, 
            media_type='application/pdf', 
            filename=f"{patient_name}_PEMF_Report.pdf",
            background=BackgroundTask(_safe_unlink, pdf_path),  # P1 audit: gonderim sonrasi PII PDF'i sil
        )
    except Exception as e:
        logger.error(f"Error generating patient PDF: {e}")
        raise HTTPException(status_code=500, detail="İşlem başarısız")


@router.post("/delete")
def delete_session_compat(payload: HistoryDeletePayload, db=Depends(get_db)):
    """Backward-compatible delete route used by the current Expo app."""
    try:
        db.delete_session(payload.session_id)
        return {"status": "success"}
    except Exception as e:
        logger.error(f"Error deleting session {payload.session_id}: {e}")
        raise HTTPException(status_code=500, detail="İşlem başarısız")


class HistoryNotesPayload(BaseModel):
    session_id: int
    notes: str = ""


@router.post("/update_notes")
def update_notes(payload: HistoryNotesPayload, db=Depends(get_db)):
    """Bir seansın notlarını günceller (Expo Geçmiş ekranı). /{session_id}'den ÖNCE tanımlı."""
    try:
        db.update_session_notes(payload.session_id, payload.notes)
        return {"status": "success"}
    except Exception as e:
        logger.error(f"Error updating notes for session {payload.session_id}: {e}")
        raise HTTPException(status_code=500, detail="İşlem başarısız")


def _epoch_to_hms(epoch):
    """Wall-clock epoch -> 'HH:MM:SS'. None/gecersizde bos string."""
    if epoch is None:
        return ""
    try:
        return datetime.fromtimestamp(float(epoch)).strftime("%H:%M:%S")
    except (ValueError, OSError, OverflowError, TypeError):
        return ""


@router.get("/{session_id}/details")
def get_session_full_details(session_id: int, db=Depends(get_db)):
    """Asama-3: Bir seansin tam rapor sozlesmesi (seans + bobin calismalari +
    her run'in sensor ozeti + grafik icin sensor ornekleri)."""
    try:
        raw = db.get_session_details(session_id)
        if not raw:
            raise HTTPException(status_code=404, detail="Session not found")

        session = {
            "id": raw.get("id"),
            "session_date": raw.get("session_date"),
            "start_time": raw.get("start_time"),
            "end_time": raw.get("end_time"),
            "duration_minutes": raw.get("duration_minutes"),
            "started_epoch": raw.get("started_epoch"),
            "ended_epoch": raw.get("ended_epoch"),
            "treatment_mode": raw.get("treatment_mode"),
            "target_condition": raw.get("target_condition"),
            "operator_name": raw.get("operator_name"),
            "patient_name": raw.get("patient_name"),
            "patient_notes": raw.get("patient_notes"),
            "session_status": raw.get("session_status"),
        }

        summaries = db.get_run_summaries(session_id)
        runs = db.get_session_coil_runs(session_id)
        coil_runs = []
        for r in runs:
            coil_runs.append({
                "coil_id": r.get("coil_id"),
                "hw_type": r.get("hw_type"),
                "started_epoch": r.get("started_epoch"),
                "ended_epoch": r.get("ended_epoch"),
                "duration_seconds": r.get("duration_seconds"),
                "frequency_hz": r.get("frequency_hz"),
                "duty_percent": r.get("duty_percent"),
                "phase": r.get("phase"),
                "intensity_mt": r.get("intensity_mt"),
                "summary": summaries.get(r.get("id")),
            })

        sensor_samples = []
        for s in db.get_sensor_samples(session_id):
            sensor_samples.append({
                "coil_id": s.get("coil_id"),
                "sample_ts": s.get("sample_ts"),
                "temperature_c": s.get("temperature_c"),
                "ambient_temp_c": s.get("ambient_temp_c"),
                "current_a": s.get("current_a"),
                "magnetic_field_mt": s.get("magnetic_field_mt"),
                "coil_run_id": s.get("coil_run_id"),
                "sample_count": s.get("sample_count"),
            })

        return {
            "session": session,
            "coil_runs": coil_runs,
            "sensor_samples": sensor_samples,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching session details {session_id}: {e}")
        raise HTTPException(status_code=500, detail="İşlem başarısız")


@router.get("/{session_id}/coil_runs.csv")
def export_coil_runs_csv(session_id: int, db=Depends(get_db)):
    """Asama-3: Bir seansin bobin calismalarini CSV olarak indir."""
    try:
        runs = db.get_session_coil_runs(session_id)
        summaries = db.get_run_summaries(session_id)

        output = io.StringIO()
        writer = csv.writer(output)

        headers = [
            "Bobin", "Donanim", "Baslangic", "Bitis", "Sure(sn)",
            "Frekans(Hz)", "Duty(%)", "Faz", "Siddet(mT)",
            "Ort.Sicaklik(C)", "Maks.Sicaklik(C)", "Ort.Akim(A)",
            "Ort.Alan(mT)", "Ornek",
        ]
        writer.writerow(headers)

        for r in runs:
            summ = summaries.get(r.get("id")) or {}
            writer.writerow([
                r.get("coil_id", ""),
                r.get("hw_type", ""),
                _epoch_to_hms(r.get("started_epoch")),
                _epoch_to_hms(r.get("ended_epoch")),
                r.get("duration_seconds", ""),
                r.get("frequency_hz", ""),
                r.get("duty_percent", ""),
                r.get("phase", ""),
                r.get("intensity_mt", ""),
                summ.get("temp_avg", ""),
                summ.get("temp_max", ""),
                summ.get("current_avg", ""),
                summ.get("field_avg", ""),
                summ.get("sample_count", ""),
            ])

        csv_data = output.getvalue()
        output.close()

        # Excel (Türkçe Windows) BOM'suz UTF-8'i Windows-1254 sanip bozuyor;
        # utf-8-sig ile BOM ekleyip charset belirtiyoruz.
        csv_bytes = csv_data.encode("utf-8-sig")

        return Response(
            content=csv_bytes,
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": f"attachment; filename=PEMF_Session_{session_id}_Coils.csv"}
        )
    except Exception as e:
        logger.error(f"Error generating coil runs CSV for session {session_id}: {e}")
        raise HTTPException(status_code=500, detail="İşlem başarısız")


@router.get("/{session_id}")
def get_session_detail(session_id: int, db=Depends(get_db)):
    """Bir seansın detaylı parametrelerini getir"""
    try:
        detail = db.get_session_details(session_id)
        if not detail:
            raise HTTPException(status_code=404, detail="Session not found")
        return detail
    except Exception as e:
        logger.error(f"Error fetching session {session_id}: {e}")
        raise HTTPException(status_code=500, detail="İşlem başarısız")

@router.delete("/{session_id}")
def delete_session(session_id: int, db=Depends(get_db)):
    """Seans sil"""
    try:
        db.delete_session(session_id)
        return {"status": "success"}
    except Exception as e:
        logger.error(f"Error deleting session {session_id}: {e}")
        raise HTTPException(status_code=500, detail="İşlem başarısız")
