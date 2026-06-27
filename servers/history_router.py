import os
import json
from pathlib import Path
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse, Response
from pydantic import BaseModel
import csv
import io
import logging

from database.treatment_history_db import get_treatment_db
from utils.pdf_report_generator import get_pdf_generator
from utils.path_utils import get_app_data_directory

router = APIRouter(prefix="/api/history", tags=["history"])
logger = logging.getLogger("HistoryRouter")


class HistoryDeletePayload(BaseModel):
    session_id: int

# Canonical veri klasörü — api_server (gözlem-notu/KPI/AI-log) ile AYNI olmalı,
# yoksa yazıcı/okuyucu farklı DB dosyalarına düşer (split-brain → geçmiş boş görünür).
_app_data_dir = get_app_data_directory()

def get_db():
    return get_treatment_db(_app_data_dir)

def get_pdf_gen():
    return get_pdf_generator(_app_data_dir)

@router.get("/")
def get_history(limit: int = 100, db=Depends(get_db)):
    """Tüm seans geçmişini listele"""
    try:
        sessions = db.get_session_history(limit=limit)
        return sessions
    except Exception as e:
        logger.error(f"Error fetching history: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/statistics")
def get_statistics(db=Depends(get_db)):
    """Klinik tedavi istatistiklerini getir"""
    try:
        stats = db.get_statistics()
        return stats
    except Exception as e:
        logger.error(f"Error fetching statistics: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/export_pdf")
def export_pdf(session_ids: str = Query(..., description="Virgülle ayrılmış session id listesi. Örn: 1,2,3"), 
               pdf_gen=Depends(get_pdf_gen)):
    """Seçili seanslar için PDF raporu oluşturup indir"""
    try:
        id_list = [int(sid.strip()) for sid in session_ids.split(",")]
        # PDF'i tmp bir yere üret
        tmp_dir = _app_data_dir / "temp_reports"
        tmp_dir.mkdir(exist_ok=True)
        out_path = str(tmp_dir / f"report_{id_list[0]}.pdf")
        
        pdf_path = pdf_gen.generate_session_report(session_ids=id_list, output_path=out_path)
        
        return FileResponse(
            path=pdf_path, 
            media_type='application/pdf', 
            filename=f"PEMF_Report.pdf"
        )
    except Exception as e:
        logger.error(f"Error generating PDF: {e}")
        raise HTTPException(status_code=500, detail=str(e))

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
        
        return Response(
            content=csv_data,
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=PEMF_History.csv"}
        )
    except Exception as e:
        logger.error(f"Error generating CSV: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/export_patient_pdf")
def export_patient_pdf(patient_name: str, pdf_gen=Depends(get_pdf_gen)):
    """Belirli bir hasta için genel PDF raporu oluşturup indir"""
    try:
        tmp_dir = _app_data_dir / "temp_reports"
        tmp_dir.mkdir(exist_ok=True)
        out_path = str(tmp_dir / f"patient_report.pdf")
        
        pdf_path = pdf_gen.generate_patient_report(patient_name=patient_name, output_path=out_path)
        
        return FileResponse(
            path=pdf_path, 
            media_type='application/pdf', 
            filename=f"{patient_name}_PEMF_Report.pdf"
        )
    except Exception as e:
        logger.error(f"Error generating patient PDF: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/delete")
def delete_session_compat(payload: HistoryDeletePayload, db=Depends(get_db)):
    """Backward-compatible delete route used by the current Expo app."""
    try:
        db.delete_session(payload.session_id)
        return {"status": "success"}
    except Exception as e:
        logger.error(f"Error deleting session {payload.session_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


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
        raise HTTPException(status_code=500, detail=str(e))


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
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/{session_id}")
def delete_session(session_id: int, db=Depends(get_db)):
    """Seans sil"""
    try:
        db.delete_session(session_id)
        return {"status": "success"}
    except Exception as e:
        logger.error(f"Error deleting session {session_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))
