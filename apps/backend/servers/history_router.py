# Author: mertaygn, cglrgrkn
import csv
import io
import logging
import os
import time
from datetime import datetime
from pathlib import Path

from database.treatment_history_db import get_treatment_db
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from pydantic import BaseModel
from starlette.background import BackgroundTask
from utils import ceviri, mt_duzeltme
from utils.akim_olcumu import akim_olcumu_acik
from utils.path_utils import get_app_data_directory
from utils.pdf_report_generator import get_pdf_generator
from utils.seans_durum import durum_etiketi

router = APIRouter(prefix="/api/history", tags=["history"])
logger = logging.getLogger("HistoryRouter")


def _akimsiz_ozet(ozet, akim_acik: bool):
    """CH4 · Y154: akım sensörü KAPALIYKEN bobin çalışması özetinin `current_avg`'ı verilmez (kopya; DB'deki değer değişmez)."""
    if akim_acik or not isinstance(ozet, dict):
        return ozet
    return {**ozet, "current_avg": None}


def _alan_notlu_ozet(ozet):
    """CH3 · Y152: ÷5 düzeltilmiş koşu özetine notu ekler (`alan_notu`; düzeltilmemişte boş). Kopya; DB değişmez."""
    if not isinstance(ozet, dict):
        return ozet
    return {**ozet, "alan_notu": mt_duzeltme.alan_notu(ozet.get("alan_duzeltme"))}


class HistoryDeletePayload(BaseModel):
    session_id: int


class HistoryBulkDeletePayload(BaseModel):
    """Toplu silme gövdesi — ⚠️ ONAY ALANI ZORUNLU.

    `patients/delete_all` ile AYNI desen (audit B-8.2): gövdesiz/kazara bir POST geri
    dönülemez biçimde onlarca seansı silmesin. Arayüz operatöre sorup bunu gönderir.
    """

    session_ids: list[int] = []
    confirm: str = ""


# Canonical veri klasörü — api_server (gözlem-notu/KPI/AI-log) ile AYNI olmalı,
# yoksa yazıcı/okuyucu farklı DB dosyalarına düşer (split-brain → geçmiş boş görünür).
_app_data_dir = get_app_data_directory()
_REPORTS_DIR = _app_data_dir / "temp_reports"


def _diske_kaydet(icerik: bytes, ad: str) -> dict:
    """Dosyayı KULLANICININ MASAÜSTÜNE yazar ve yolunu döndürür.

    ===========================================================================
    ⚠️ NEDEN VAR — "İndir" düğmeleri masaüstü uygulamasında ÖLÜYDÜ (2026-09-11)
    ===========================================================================
    Arayüz Tauri v2 **WebView2** penceresinde koşuyor. İstemci indirmeyi
    `fetch → blob → <a download>.click()` ile yapıyordu; bu WebView2'de ancak
    uygulama bir indirme işleyicisi kaydederse çalışır. `launcher/app/src/main.rs`
    hiçbir `on_download` / dialog / fs eklentisi KAYDETMİYOR → tıklama **sessizce
    hiçbir şey yapmıyordu.** Hata da çıkmıyordu: kod `a.click()`ten sonra hiçbir
    geri bildirim vermeden dönüyordu, yani "çalıştı" ile "öldü" AYNI görünüyordu.

    Rust tarafını düzeltmek launcher'ın yeniden yayınlanmasını gerektirirdi; sahada
    tek makine var ve yayın DURDURULDU. Backend zaten AYNI MAKİNEDE koşuyor → dosyayı
    o yazar, arayüz de yolu söyler. Hiçbir Tauri eklentisi, hiçbir launcher sürümü
    gerekmez.

    ⚠️ HEDEF DİZİN TEK KAYNAKTAN: seans CSV'siyle AYNI çözücü kullanılır
    (`servers.seans_alan_kaydi.masaustu_dizini`) — "sahibin dosyaları nereye gider"
    sorusunun depoda TEK cevabı olsun. Test süiti o çözücüyü yamalıyor
    (`conftest._masaustunu_koru`), böylece bu uç da gerçek masaüstüne SIZMAZ.
    """
    from servers.seans_alan_kaydi import masaustu_dizini

    dizin, gerekce = masaustu_dizini()
    guvenli = "".join(c for c in ad if c.isalnum() or c in ("_", "-", ".")) or "PEMF_disa_aktarim"
    hedef = Path(dizin) / guvenli
    # Aynı saniyede iki dışa aktarım üst üste YAZMASIN.
    if hedef.exists():
        kok, uzanti = os.path.splitext(guvenli)
        hedef = Path(dizin) / f"{kok}_{int(time.time() * 1000)}{uzanti}"
    hedef.write_bytes(icerik)
    logger.info("Disa aktarim diske yazildi: %s (%s)", hedef, gerekce)
    return {"status": "success", "yol": str(hedef), "ad": hedef.name, "bayt": len(icerik)}


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
def get_history(request: Request, limit: int = 100, cursor: int = None, db=Depends(get_db)):
    """Seans geçmişini listele (audit B-8.2: keyset/cursor pagination).

    - `limit`: sayfa boyutu (varsayılan 100).
    - `cursor`: bir önceki sayfanın SON öğesinin `id`'si → ondan ESKİ seanslar (sonraki sayfa).
      Verilmezse en yeni `limit` seans döner (ilk sayfa). "Sonraki sayfa var mı" = dönen kayıt == limit.
    Geriye uyumlu: eski istemci `cursor` göndermez → eski davranış (en yeni `limit`).
    SG.G1: istek `X-PEMF-Profil` bildiriyorsa yalnız o profilin seansları (`utils/profil`); bildirmeyen eski istemci süzgeçsiz."""
    from utils.profil import istek_profili

    try:
        sessions = db.get_session_history(limit=limit, before_id=cursor, profil=istek_profili(request))
        return sessions
    except Exception as e:
        logger.error(f"Error fetching history: {e}")
        raise HTTPException(status_code=500, detail=ceviri.t("gecmis.hata.islemBasarisiz"))


@router.get("/statistics")
def get_statistics(request: Request, db=Depends(get_db)):
    """Seans istatistiklerini getir (SG.G1: istek profili bildiriyorsa yalnız o profilin seansları)."""
    from utils.profil import istek_profili

    try:
        _p = istek_profili(request)
        stats = db.get_statistics(profil=_p) if _p else db.get_statistics()  # başlıksız çağrı BİREBİR eskisi
        return stats
    except Exception as e:
        logger.error(f"Error fetching statistics: {e}")
        raise HTTPException(status_code=500, detail=ceviri.t("gecmis.hata.islemBasarisiz"))


@router.get("/export_pdf")
def export_pdf(
    session_ids: str = Query(..., description="Virgülle ayrılmış session id listesi. Örn: 1,2,3"),
    kaydet: int = Query(
        0,
        description="1 = dosyayı SUNUCUNUN çalıştığı makinenin masaüstüne yaz ve JSON yol döndür "
        "(masaüstü uygulaması için; tarayıcı indirmesi WebView2'de çalışmıyor). "
        "0 = normal akış indirmesi (web/mobil).",
    ),
    pdf_gen=Depends(get_pdf_gen),
):
    """Seçili seanslar için PDF raporu oluşturup indir.

    ⚠️ `kaydet=1` yalnız backend ile arayüz AYNI makinedeyken anlamlıdır; istemci bunu
    `apiBaseUrl` localhost'a bakıyorsa gönderir (bkz. TreatmentHistoryScreen)."""
    try:
        id_list = [int(sid.strip()) for sid in session_ids.split(",")]
        # PDF'i tmp bir yere üret
        tmp_dir = _app_data_dir / "temp_reports"
        tmp_dir.mkdir(exist_ok=True)
        _purge_old_reports()
        out_path = str(tmp_dir / f"report_{id_list[0]}_{int(time.time() * 1000)}.pdf")

        pdf_path = pdf_gen.generate_session_report(session_ids=id_list, output_path=out_path)

        if kaydet:
            try:
                veri = Path(pdf_path).read_bytes()
            finally:
                _safe_unlink(pdf_path)  # geçici PII PDF'i her durumda sil
            return _diske_kaydet(veri, f"PEMF_Rapor_{len(id_list)}_seans.pdf")

        return FileResponse(
            path=pdf_path,
            media_type='application/pdf',
            filename="PEMF_Report.pdf",
            background=BackgroundTask(_safe_unlink, pdf_path),  # P1 audit: gonderim sonrasi PII PDF'i sil
        )
    except Exception as e:
        logger.error(f"Error generating PDF: {e}")
        raise HTTPException(status_code=500, detail=ceviri.t("gecmis.hata.islemBasarisiz"))


#: D2.16: CSV dışa aktarmasının geçmiş SAYFA boyu (tavan DEĞİL — sayfalar sonuna kadar okunur).
_CSV_SAYFA = 5000


#: D2-3.3: okuma sırasında geri yükleme oldu/sürüyor — dosya verilmez.
def _csv_geri_yukleme_suruyor() -> str:
    return ceviri.t("gecmis.hata.geriYukleme")


def _geri_yukleme_nesli(db) -> int:
    """D2-3.3: api_server `_ice_aktar`ın tedavi DB nesnesine yazdığı sayaç (yalnız örnek sözlüğünden — sahte/Mock DB'de 0)."""
    n = getattr(db, "__dict__", {}).get("_geri_yukleme_nesli", 0)
    return n if isinstance(n, int) else 0


@router.get("/export_csv")
def export_csv(
    session_ids: str = Query(
        "",
        description="Opsiyonel: virgülle ayrılmış id listesiyle SINIRLA (aktif operatör-kapsam/arama). Boş = tümü (geriye uyumlu).",
    ),
    kaydet: int = Query(0, description="1 = masaüstüne yaz + JSON yol döndür (bkz. export_pdf)."),
    db=Depends(get_db),
    request: Request = None,
):
    """Seans geçmişini CSV indir. session_ids verilirse YALNIZ o kayıtlar (ekranda görünen
    operatör-kapsam+arama) döner → 'Benim Seanslarım' seçiliyken tüm-klinik PII dökümü olmaz (KVKK)."""
    # ⚠️ O-A3.7 (2-B incelemesi) · S-D.1 [ÖNERİLEN UYGULANDI, Y123]: kimlik LİSTESİZ ("Tümünü") istek kliniğin TÜM seans geçmişini
    # (hasta adı, notlar) verir → kayıtlı operatörlü klinikte KİMLİK ister (jetonsuz 428; Y103 "kimse seçili değilse kayıt
    # gösterilmez" ilkesinin dışa aktarma yüzü). Kimlikli hekim tümünü alır (rol modeli yok — A-28); operatörsüz klinik (Kural 2)
    # ve kimlik listeli istek DEĞİŞMEZ. Kapı: tests/test_csv_KIMLIK_LISTESIZ_istek_kayitli_klinikte_KIMLIK_ister_OA37.py
    if not session_ids.strip() and request is not None:
        from servers.auth import cozumlenmis_operator, kayitli_operator_var, kimliksiz_detayi

        if kayitli_operator_var() and not cozumlenmis_operator(request):
            raise HTTPException(
                status_code=428,
                detail=kimliksiz_detayi(ceviri.t("gecmis.kimlik.disaAktar")),
            )
    try:
        # DENETIM P3: session_ids SQL'e HIC girmiyordu → birkac seans istense bile 10.000 satir
        # 11 LEFT JOIN ile belleğe cekilip Python'da filtreleniyordu. Filtre artik SQL'de.
        _sid = session_ids.strip()
        _idset = None
        if _sid:
            try:
                _idset = [int(x.strip()) for x in _sid.split(",") if x.strip()]
            except ValueError:
                return Response(
                    content=ceviri.t("gecmis.hata.gecersizSessionIds"), media_type="text/plain", status_code=400
                )
        # ⚠️ D2.16 (B-3.24): geçmiş anahtar kümesi (keyset, `before_id`) SAYFALARIYLA sonuna kadar okunur — sınır YOK. Eskiden
        # tek sorgu `limit=10000` ile kırpıyordu: yoğun klinikte "Tümünü dışa aktar" CSV'sinde EN ESKİ tıbbi kayıtlar işaretsiz
        # düşüyordu (ölçüldü: 10.001 seansta 10.000 satır). Kapı: tests/test_csv_TUMU_disa_aktarim_KESILMEZ_D216.py
        # ⚠️ D2-3.3 (2-D incelemesi): sayfalar TEK anlık görüntü değil — okuma sürerken geri yükleme (REPLACE_ALL) başlar/biterse
        # dosya iki durumun karışımı ya da eski geçmişin ilk sayfası olur (AUTOINCREMENT: yeni kimlikler büyük → sonraki sayfa boş).
        # Nesil sayacı (`_ice_aktar`; tek = sürüyor) değiştiyse dosya VERİLMEZ, 409. Kapı: tests/test_csv_TUMU_sayfalar_arasi_GERI_YUKLEME_kesik_dosya_VERMEZ_D233.py
        _nesil = _geri_yukleme_nesli(db)
        if _nesil % 2:
            return JSONResponse(status_code=409, content={"detail": _csv_geri_yukleme_suruyor()})
        sessions = []
        _once = None
        # SG.G1: "Tümünü dışa aktar" da ekrandaki listeyle AYNI profil kümesi (başlıksız eski istemci süzgeçsiz).
        from utils.profil import istek_profili

        _profil = istek_profili(request) if request is not None else None
        while True:
            _sayfa = db.get_session_history(
                limit=_CSV_SAYFA, internal_full=True, session_ids=_idset, before_id=_once, profil=_profil
            )  # Audit P2: tam-export, 500'e kırpma
            sessions.extend(_sayfa)
            if len(_sayfa) < _CSV_SAYFA:
                break
            _once = _sayfa[-1]["id"]
        if _geri_yukleme_nesli(db) != _nesil:
            logger.warning("CSV disa aktarma: okuma sirasinda geri yukleme oldu — tutarsiz dosya VERILMEDI (409).")
            return JSONResponse(status_code=409, content={"detail": _csv_geri_yukleme_suruyor()})
        if not sessions:
            # ⚠️ ESKIDEN BU DA "indirilen dosya" oluyordu: istemci 200'ü başarı sayıp içinde
            # "Veri bulunamadi" yazan bir `PEMF_Gecmis.csv` kaydediyordu. Operatör dosyayı
            # açana kadar kayıt olmadığını anlamıyordu.
            if kaydet:
                return {"status": "bos", "mesaj": ceviri.t("gecmis.csv.kayitYok")}
            return Response(content=ceviri.t("gecmis.csv.veriYok"), media_type="text/plain")

        output = io.StringIO()
        writer = csv.writer(output)

        def _csv_safe(value):
            # CSV formula-injection koruması (OWASP): Excel/LibreOffice '=','+','-','@',TAB,CR ile başlayan
            # hücreyi FORMÜL sanıp çalıştırır (komut yürütme/veri sızdırma). Başına ' ekleyip metne zorla.
            s = "" if value is None else str(value)
            return "'" + s if s[:1] in ("=", "+", "-", "@", "\t", "\r") else s

        # Headers
        headers = [
            "ID",
            ceviri.t("gecmis.csv.hasta"),
            ceviri.t("gecmis.csv.hedef"),
            ceviri.t("gecmis.csv.mod"),
            ceviri.t("gecmis.csv.sure"),
            ceviri.t("gecmis.csv.frekans"),
            ceviri.t("gecmis.csv.ayarlanan"),
            ceviri.t("gecmis.csv.tarih"),
            ceviri.t("gecmis.csv.baslangic"),
            ceviri.t("gecmis.csv.durum"),
            ceviri.t("gecmis.csv.notlar"),
        ]
        writer.writerow(headers)

        # ⚠️ SAHİP BİLDİRİMİ (2026-09-12): "bu csv de tamamlandı yazmalı ingilizce yazıyor
        # completed onu düzelt." Operatör ekranda "Tamamlandı", Excel'de "completed"
        # görüyordu — aynı kaydın iki farklı dili. Durum sütunu artık `durum_etiketi()`
        # ile çevrilir (arayüzle AYNI sözlük; bkz. utils/seans_durum.py).
        # ⚠️ DB'deki ham değer DEĞİŞMEZ — çeviri yalnız bu dışa-aktarım sınırındadır.
        for s in sessions:
            writer.writerow(
                [
                    s.get("id", ""),
                    _csv_safe(s.get("patient_name", "")),
                    _csv_safe(s.get("target_condition", "")),
                    _csv_safe(s.get("treatment_mode", "")),
                    s.get("duration_minutes", ""),
                    s.get("frequency_hz", ""),
                    s.get("intensity_mt", ""),
                    s.get("session_date", ""),
                    s.get("start_time", ""),
                    _csv_safe(durum_etiketi(s.get("session_status", ""))),
                    _csv_safe(s.get("patient_notes", "")),
                ]
            )

        csv_data = output.getvalue()
        output.close()

        # Excel (özellikle Türkçe Windows) BOM'suz UTF-8'i sistem codepage'i (Windows-1254)
        # sanıp Türkçe karakterleri bozuyor. utf-8-sig ile BOM ekleyip charset belirtiyoruz.
        csv_bytes = csv_data.encode("utf-8-sig")

        if kaydet:
            return _diske_kaydet(csv_bytes, "PEMF_Gecmis.csv")

        return Response(
            content=csv_bytes,
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": "attachment; filename=PEMF_History.csv"},
        )
    except Exception as e:
        logger.error(f"Error generating CSV: {e}")
        raise HTTPException(status_code=500, detail=ceviri.t("gecmis.hata.islemBasarisiz"))


@router.get("/export_patient_pdf")
def export_patient_pdf(patient_name: str, pdf_gen=Depends(get_pdf_gen)):
    """Belirli bir hasta için genel PDF raporu oluşturup indir"""
    try:
        tmp_dir = _app_data_dir / "temp_reports"
        tmp_dir.mkdir(exist_ok=True)
        out_path = str(tmp_dir / f"patient_report_{int(time.time() * 1000)}.pdf")

        pdf_path = pdf_gen.generate_patient_report(patient_name=patient_name, output_path=out_path)

        return FileResponse(
            path=pdf_path,
            media_type='application/pdf',
            filename=f"{patient_name}_PEMF_Report.pdf",
            background=BackgroundTask(_safe_unlink, pdf_path),  # P1 audit: gonderim sonrasi PII PDF'i sil
        )
    except Exception as e:
        logger.error(f"Error generating patient PDF: {e}")
        raise HTTPException(status_code=500, detail=ceviri.t("gecmis.hata.islemBasarisiz"))


def _seans_sahipligi(request: Request, db, kimlikler: list, olay: str, scope: str) -> dict:
    """⚠️ D2.72 (B-6.26 · Y92): seans (tıbbi kayıt) silme yalnız KENDİ kaydına; kimlik jetondan; operatörsüz klinik
    kısıtsız (Kural 2). Kural tek yerde: servers/silme_yetkisi.py. Kapı: tests/test_silme_SAHIPLIK_jetondan_D272_Y92.py.
    Denetlenen `{kimlik: sahip}` sözlüğünü döner (B2-1.3: DELETE yalnız bunlara)."""
    from servers.silme_yetkisi import sahiplik_kapisi

    sahipler = db.seans_sahipleri(kimlikler)
    sahiplik_kapisi(request, sahipler, olay=olay, scope=scope)
    return sahipler


def _suruyor_detay() -> str:
    return ceviri.t("gecmis.hata.seansSuruyor")


def _suren_seans_reddi(request: Request, kimlikler, olay: str, scope: str) -> None:
    """⚠️ B2-1.5: SÜREN seansın satırı silinirse tedavi donanımda sürer ama doz satırları ebeveynsiz yazılır, ACİL DURDUR
    olayı FK'dan YAZILAMAZ (ölçüldü) → 409, hiçbir şey silinmez. ⚠️ Ö.4-Y8: `_session_lock` ALINMAZ (ACİL DURDUR beklemez;
    `dict.get` atomik). Kapı: tests/test_seans_SURERKEN_kaydi_silinemez_B2_1_5.py"""
    try:
        from servers import api_server as _api

        _s = _api._active_session
        aktif = _s.get("db_session_id") if _s.get("is_active") else None
    except Exception:
        aktif = None
    if aktif is None or int(aktif) not in {int(k) for k in kimlikler}:
        return
    from servers import audit_log as _iz

    _iz.kimlikli_yaz(request, olay, scope=scope, item_count=0, outcome="reddedildi", detail={"neden": "seans_suruyor"})
    raise HTTPException(status_code=409, detail=_suruyor_detay())


def _tekil_seans_sil(request: Request, db, session_id: int) -> dict:
    """İki tekil silme ucunun (`POST /delete`, `DELETE /{id}`) TEK gövdesi.

    ⚠️ D2.43 (B-2.7 · B-2.10): tedavi kaydının (uygulanan doz dahil) geri dönüşsüz silinmesi izsizdi ve olmayan seansı
    silmek 'success' dönüyordu → her silme `kimlikli_yaz` ile izlenir (kimlik sunucuda çözülür), olmayan seans 404
    (iz `bulunamadi`). Sıra: önce kimlik/sahiplik (D2.72 — kimliksize varlık bilgisi verilmez), sonra varlık.
    Kapı: tests/test_seans_tekil_silme_IZ_ve_404_D243.py.
    """
    from servers import audit_log as _iz
    from servers.silme_yetkisi import sahiplik_kapisi

    scope = f"id={session_id}"
    sahipler = db.seans_sahipleri([session_id])
    sahiplik_kapisi(request, sahipler, olay="history.delete", scope=scope)
    if not sahipler:
        _iz.kimlikli_yaz(request, "history.delete", scope=scope, item_count=0, outcome="bulunamadi")
        raise HTTPException(status_code=404, detail=ceviri.t("gecmis.hata.seansYok"))
    _suren_seans_reddi(request, [session_id], "history.delete", scope)
    # ⚠️ D2.17 (B-3.27): "bu hastanın acil durdurma kaydını ve dozunu kim sildi" — bağlı kayıtların SAYILARI silmeden
    # ÖNCE alınır ve ize girer (içerik değil). Özet okunamazsa silme KISITLANMAZ; iz bunu söyler.
    # Kapı: tests/test_seans_tekil_silme_OZETI_IZDE_D217.py.
    try:
        ozet = db.seans_silme_ozeti(session_id)
    except Exception:
        logger.warning("Seans %s silme ozeti okunamadi — iz ozetsiz yaziliyor.", session_id, exc_info=True)
        ozet = {"ozet_okunamadi": True}
    try:
        db.delete_session(session_id)
    except Exception as e:
        logger.error(f"Error deleting session {session_id}: {e}")
        raise HTTPException(status_code=500, detail=ceviri.t("gecmis.hata.islemBasarisiz"))
    _iz.kimlikli_yaz(request, "history.delete", scope=scope, item_count=1, detail=ozet)
    return {"status": "success"}


@router.post("/delete")
def delete_session_compat(request: Request, payload: HistoryDeletePayload, db=Depends(get_db)):
    """Backward-compatible delete route used by the current Expo app."""
    return _tekil_seans_sil(request, db, payload.session_id)


class HistoryNotesPayload(BaseModel):
    session_id: int
    notes: str = ""


@router.post("/delete_bulk")
def delete_sessions_bulk(request: Request, payload: HistoryBulkDeletePayload, db=Depends(get_db)):
    """SEÇİLİ seansları TEK İŞLEMDE siler (atomik).

    ⚠️ SAHİP BİLDİRİMİ (2026-09-12): "toplu sil seçeneği eksik seans geçmişi tabında
    kullanıcı tek tek silmek zorunda kalıyor."

    ⚠️ NEDEN SUNUCUDA TOPLU, NEDEN İSTEMCİDEN N KEZ /delete DEĞİL: N ayrı istek yarı yolda
    koparsa (ağ, kapanan pencere) operatör HANGİ kayıtların gittiğini bilemez. Geri alınamaz
    bir işlemde "kısmen oldu" en kötü sonuçtur — tek transaction ya hepsini siler ya hiçbirini.

    ⚠️ Denetim izi yazılır: seans silmek geri dönüşsüzdür ve toplu silme, tek-tek silmeden
    çok daha geniş bir eylemdir. Kayda seans ADI/PII girmez, yalnız sayı ve kimlikler.
    """
    if payload.confirm != "DELETE_SELECTED":
        raise HTTPException(
            status_code=400,
            detail=ceviri.t("hasta.hata.topluSilmeOnaySecili"),
        )
    istenen = sorted({int(x) for x in (payload.session_ids or [])})
    if not istenen:
        raise HTTPException(status_code=400, detail=ceviri.t("gecmis.hata.silinecekSecilmedi"))
    denetlenen = _seans_sahipligi(request, db, istenen, "history.delete_bulk", f"{len(istenen)} seans")
    _suren_seans_reddi(request, istenen, "history.delete_bulk", f"{len(istenen)} seans")
    # ⚠️ O-B.7 (D2.17'nin toplu ikizi): silinecek seansların bağlı kayıt SAYILARI (olay, ACİL DURDUR, doz = bobin koşusu, sensör)
    # silmeden ÖNCE ve YALNIZ silinecek (sahipliği denetlenmiş) kimliklerle alınıp ize girer — içerik değil. Özet okunamazsa silme
    # KISITLANMAZ; iz bunu söyler. Kapı: tests/test_seans_toplu_silme_OZETI_IZDE_OB7.py
    _silinecek = sorted(set(istenen) & set(denetlenen))
    try:
        ozet = db.seans_silme_ozeti_toplu(_silinecek)
    except Exception:
        logger.warning("Toplu silme ozeti okunamadi — iz ozetsiz yaziliyor.", exc_info=True)
        ozet = {"ozet_okunamadi": True}
    try:
        silinen = db.delete_sessions_bulk(istenen, yalniz=set(denetlenen))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Toplu seans silme hatasi: {e}")
        raise HTTPException(status_code=500, detail=ceviri.t("gecmis.hata.islemBasarisiz"))
    try:
        from servers import audit_log as _iz

        _iz.kimlikli_yaz(
            request,
            "history.delete_bulk",
            scope=f"{len(istenen)} seans",
            item_count=silinen,
            outcome="ok" if silinen else "bulunamadi",
            detail=ozet,
        )
    except Exception:
        logger.debug("Toplu silme denetim izi yazilamadi (non-fatal).", exc_info=True)
    # ⚠️ `istenen` ile `silinen` AYRI raporlanır: operatör bir başkasının aynı anda sildiği
    # kayıtları seçmiş olabilir. "5 sildim" demek yerine gerçeği söyle.
    return {"status": "success", "istenen": len(istenen), "silinen": silinen}


@router.post("/update_notes")
def update_notes(request: Request, payload: HistoryNotesPayload, db=Depends(get_db)):
    """Bir seansın notlarını günceller (Expo Geçmiş ekranı). /{session_id}'den ÖNCE tanımlı."""
    # ⚠️ Y107 (S-B.4 · O-B.9): kayıtlı operatörlü klinikte seans notu (tıbbi kayıt) KİMLİK ister — kimliksiz (jetonsuz LAN, kilit
    # sonrası eski jeton) 428, not değişmez, deneme izde `reddedildi`. Kimlikli HER hekim düzenler (klinik içi paylaşım; sahiplik
    # sorulmaz), iz düzenleyenin adına. Operatörsüz klinik (Kural 2) değişmez; kimlik DB'si okunamıyorsa Y113 iletisi.
    # Kapı: tests/test_seans_notu_KIMLIK_ister_Y107.py
    from servers import audit_log as _iz
    from servers.auth import cozumlenmis_operator, kayitli_operator_var, kimliksiz_detayi

    if kayitli_operator_var() and not cozumlenmis_operator(request):  # beyan YOK → yalnız jeton
        _iz.kimlikli_yaz(request, "history.notes", scope=f"id={payload.session_id}", item_count=0, outcome="reddedildi")
        raise HTTPException(
            status_code=428,
            detail=kimliksiz_detayi(ceviri.t("gecmis.kimlik.notDuzenle")),
        )
    try:
        db.update_session_notes(payload.session_id, payload.notes)
    except Exception as e:
        logger.error(f"Error updating notes for session {payload.session_id}: {e}")
        raise HTTPException(status_code=500, detail=ceviri.t("gecmis.hata.islemBasarisiz"))
    # ⚠️ D2.43 (B-2.10): tıbbi kaydın değişmesi izlenir — kim, hangi seans. İÇERİK YAZILMAZ: not METNİ ize girmez
    # (denetim izi verinin ikinci kopyası olamaz), yalnız notun var olup olmadığı.
    _iz.kimlikli_yaz(
        request,
        "history.notes",
        scope=f"id={payload.session_id}",
        item_count=1,
        detail={"not_var": bool((payload.notes or "").strip())},
    )
    return {"status": "success"}


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
        # CH4 · Y154: akım sensörü KAPALIYKEN eski kayıtlardaki akım (TD5 öncesi yüzen girişten SAHTE olabilir) VERİLMEZ; veri SİLİNMEZ.
        _akim = akim_olcumu_acik()
        coil_runs = []
        for r in runs:
            coil_runs.append(
                {
                    "coil_id": r.get("coil_id"),
                    "hw_type": r.get("hw_type"),
                    "started_epoch": r.get("started_epoch"),
                    "ended_epoch": r.get("ended_epoch"),
                    "duration_seconds": r.get("duration_seconds"),
                    "frequency_hz": r.get("frequency_hz"),
                    "duty_percent": r.get("duty_percent"),
                    "phase": r.get("phase"),
                    "intensity_mt": r.get("intensity_mt"),
                    "summary": _alan_notlu_ozet(_akimsiz_ozet(summaries.get(r.get("id")), _akim)),
                }
            )

        sensor_samples = []
        for s in db.get_sensor_samples(session_id):
            sensor_samples.append(
                {
                    "coil_id": s.get("coil_id"),
                    "sample_ts": s.get("sample_ts"),
                    "temperature_c": s.get("temperature_c"),
                    "ambient_temp_c": s.get("ambient_temp_c"),
                    "current_a": s.get("current_a") if _akim else None,
                    "magnetic_field_mt": s.get("magnetic_field_mt"),
                    # CH3 · Y152: bu dakikanın alanı ÷5 düzeltildi mi (grafik / rapor notu).
                    "alan_duzeltildi": mt_duzeltme.duzeltildi_mi(s.get("alan_duzeltme")),
                    "coil_run_id": s.get("coil_run_id"),
                    "sample_count": s.get("sample_count"),
                }
            )
        # CH3 · Y152: seansın herhangi bir ölçülen alanı düzeltildiyse seans düzeyinde TEK not (ekran / rapor üstünde).
        _duzeltildi = any(s["alan_duzeltildi"] for s in sensor_samples) or any(
            (k.get("summary") or {}).get("alan_notu") for k in coil_runs
        )
        session["alan_notu"] = mt_duzeltme.alan_notu_metni() if _duzeltildi else ""

        return {
            "session": session,
            "coil_runs": coil_runs,
            "sensor_samples": sensor_samples,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching session details {session_id}: {e}")
        raise HTTPException(status_code=500, detail=ceviri.t("gecmis.hata.islemBasarisiz"))


@router.get("/{session_id}/coil_runs.csv")
def export_coil_runs_csv(session_id: int, db=Depends(get_db)):
    """Asama-3: Bir seansin bobin calismalarini CSV olarak indir."""
    try:
        runs = db.get_session_coil_runs(session_id)
        summaries = db.get_run_summaries(session_id)

        output = io.StringIO()
        writer = csv.writer(output)

        headers = [
            ceviri.t("gecmis.csv.bobin"),
            ceviri.t("gecmis.csv.donanim"),
            ceviri.t("gecmis.csv.baslangic"),
            ceviri.t("gecmis.csv.bitis"),
            ceviri.t("gecmis.csv.sureSn"),
            ceviri.t("gecmis.csv.frekans"),
            ceviri.t("gecmis.csv.duty"),
            ceviri.t("gecmis.csv.faz"),
            ceviri.t("gecmis.csv.ayarlanan"),
            ceviri.t("gecmis.csv.ortSicaklik"),
            ceviri.t("gecmis.csv.maksSicaklik"),
            ceviri.t("gecmis.csv.ortAkim"),
            ceviri.t("gecmis.csv.ortAlan"),
            ceviri.t("gecmis.csv.ornek"),
            # CH3 · Y152: SONA eklendi (mevcut sütun sırası değişmez) — ÷5 düzeltilmiş koşunun notu.
            ceviri.t("gecmis.csv.alanNotu"),
        ]
        writer.writerow(headers)

        _akim = akim_olcumu_acik()
        for r in runs:
            # CH4 · Y154: akım sensörü KAPALIYKEN "Ort.Akim(A)" sütunu BOŞ (sütun sırası — dışa aktarım biçimi — değişmez).
            summ = _akimsiz_ozet(summaries.get(r.get("id")) or {}, _akim)
            writer.writerow(
                [
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
                    mt_duzeltme.alan_notu(summ.get("alan_duzeltme")),
                ]
            )

        csv_data = output.getvalue()
        output.close()

        # Excel (Türkçe Windows) BOM'suz UTF-8'i Windows-1254 sanip bozuyor;
        # utf-8-sig ile BOM ekleyip charset belirtiyoruz.
        csv_bytes = csv_data.encode("utf-8-sig")

        return Response(
            content=csv_bytes,
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": f"attachment; filename=PEMF_Session_{session_id}_Coils.csv"},
        )
    except Exception as e:
        logger.error(f"Error generating coil runs CSV for session {session_id}: {e}")
        raise HTTPException(status_code=500, detail=ceviri.t("gecmis.hata.islemBasarisiz"))


@router.get("/{session_id}")
def get_session_detail(session_id: int, db=Depends(get_db)):
    """Bir seansın detaylı parametrelerini getir"""
    try:
        detail = db.get_session_details(session_id)
        if not detail:
            raise HTTPException(status_code=404, detail="Session not found")
        return detail
    except HTTPException:
        # DENETIM P3: genis `except Exception` KENDI 404'unu da yakalayip 500'e ceviriyordu →
        # istemci "seans yok" ile "sunucu hatasi"ni ayirt edemiyor; mobil taraf 500'u gecici
        # ariza sanip yeniden deniyor (silinmis seansta sonsuz retry). HTTPException'i gecir.
        raise
    except Exception as e:
        logger.error(f"Error fetching session {session_id}: {e}")
        raise HTTPException(status_code=500, detail=ceviri.t("gecmis.hata.islemBasarisiz"))


@router.delete("/{session_id}")
def delete_session(session_id: int, request: Request, db=Depends(get_db)):
    """Seans sil"""
    return _tekil_seans_sil(request, db, session_id)
