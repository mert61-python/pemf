# Author: mertaygn, cglrgrkn
"""Hasta (patient) CRUD uçları (audit B-2.2: api_server.py'den ayrıldı — modüler router).
Yalnız `database.patient_database`'e bağlı; paylaşılan donanım/seans/live-state'i KULLANMAZ.
Yollar birebir korunur (/api/patients...) → istemci sözleşmesi değişmez (pagination + delete_all guard dahil)."""

import logging
import os

from database.patient_database import get_patient_database
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from utils import ceviri
from utils.profil import istek_profili

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
        raise HTTPException(status_code=503, detail=ceviri.t("hasta.hata.kimlikAltyapisiYok"))
    tok = request.headers.get("X-API-Key") or request.query_params.get("token") or ""
    if not check_token(tok):
        raise HTTPException(status_code=401, detail=ceviri.t("hasta.hata.operatorJetonuGerekli"))


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


class BulkDeletePayload(BaseModel):
    """SEÇİLİ hastaları silme gövdesi — `DeleteAllPayload` ile AYNI onay deseni."""

    patient_ids: list[str] = []
    confirm: str = ""


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
    # SG.G1 (sahip gözlemi 2026-10-13): istemci etkin profili bildirdiyse (`X-PEMF-Profil`) yalnız o profilin hasta / denekleri — liste
    # ve 'total' AYNI koşulla (sayfalama tutarlı). Başlıksız eski istemci bugünkü gibi hepsini görür. Kapı: tests/test_profil_ayrimi_SG_G1_G2.py
    profil = istek_profili(request)
    # ⚠️ D2-3.1 (2-D incelemesi · D2.66'nın ilk yarısı): okuma KATI — okunamayan hasta DB'si "hasta yok" (200 success, 0) DEĞİL, 503.
    # Eskiden arayüz "Henüz hasta kaydı yok." gösteriyordu; operatör masadaki hayvana yeni kart açıyordu (geçici arızada çift kart).
    try:
        data = db.get_all_patients(limit=limit, offset=off, kati=True, profil=profil)
    except Exception:
        logger.warning(
            "Hasta listesi okunamadi (hasta DB'si acilamiyor) — 503; bu 'hasta yok' DEMEK DEGIL.", exc_info=True
        )
        raise HTTPException(
            status_code=503,
            detail=ceviri.t("hasta.hata.listeOkunamadi"),
        )
    total = db.count_patients(profil=profil)
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
    # ⚠️ D2.41 (B-2.11): hastanın SAHİBİ sunucu kuralından (jeton; kanıtsız kayıtlı-hekim beyanı → sahipsiz; operatörsüz
    # klinikte beyan — Kural 2). Eskiden LAN'dan jetonsuz başka bir hekimin adına hasta açılabiliyordu ("Benim" listesine).
    # Kapı: tests/test_kayit_atfi_COZUMLENMIS_operator_D241.py.
    from servers.auth import cozumlenmis_operator, kayitli_operator_var, kimliksiz_detayi

    payload["operator_email"] = cozumlenmis_operator(request, payload.get("operator_email", ""))
    # ⚠️ Y110 (S-B2.2 · A-61 · B2-2.7): kayıtlı operatörlü cihazda kimliği çözülemeyen YENİ hasta AÇILMAZ — 428. Eskiden eski
    # APK / LAN / kilit sonrası eski jetonla SAHİPSİZ hasta açılıyordu ve arayüzün kapsam kuralı (`patientScope.inScope`) onu
    # kliniğin HER hekiminin "Benim" listesinde sayıyordu. Operatörsüz klinik (Kural 2) ve GÜNCELLEME (yukarıda) değişmez.
    # Kimlik DB'si okunamıyorsa ileti arızayı ve çareyi söyler (Y113). Kapı: tests/test_hasta_ekleme_KAYITLI_cihazda_KIMLIKSIZ_428_Y110.py
    if not payload["operator_email"] and kayitli_operator_var():
        raise HTTPException(
            status_code=428,
            detail=kimliksiz_detayi(ceviri.t("hasta.hata.ekleOperatorSecin")),
        )
    # SG.G1: yeni kayıt oluşturulduğu profille yazılır (başlık yoksa boş → eski kayıt kuralı, S-SG.7). Güncelleme (yukarıda) profile DOKUNMAZ.
    payload["profil"] = istek_profili(request) or ""
    patient_id = db.add_patient(payload)
    return {"status": "success", "patient_id": patient_id}


@router.delete("/api/patients/{patient_id}")
def remove_patient(patient_id: str, request: Request):
    """Hasta siler"""
    _enforce_patient_auth(request)
    db = get_patient_database()
    # ⚠️ D2.72 (Y92): kayıtlı operatörlü cihazda yalnız KENDİ kaydı, kimlik jetondan (bkz. servers/silme_yetkisi.py).
    # Kapı: tests/test_silme_SAHIPLIK_jetondan_D272_Y92.py.
    from servers.silme_yetkisi import sahiplik_kapisi

    sahipler = db.operator_sahipleri([patient_id])
    sahiplik_kapisi(request, sahipler, olay="patient.delete", scope=f"id={patient_id}")
    # Denetim izi (2026-08-09, Tier 3): hasta kaydı silmek geri dönüşsüzdür ve KVKK "unutulma
    # hakkı"nın karşılığıdır — talebin yerine getirildiğinin kanıtı da gerekir. Hasta ADI
    # YAZILMAZ; iz, sildiği verinin ikinci bir kopyası olamaz.
    from servers import audit_log as _iz

    # ⚠️ Y108 (S-B.5 · O-B.8): olmayan hasta 404 (seans uçlarıyla aynı — D2.43); eskiden `200 {"status":"error"}` → arayüz
    # "Hasta silinemedi" diyordu (başka cihazda zaten silinmiş hasta için "silme çalışmıyor"). Sıra: önce kimlik/sahiplik
    # (yukarıda — kimliksize varlık bilgisi verilmez), sonra varlık. Var olan kaydın silinememesi 404 DEĞİL, 500.
    # Kapı: tests/test_hasta_TEKIL_silme_OLMAYAN_404_Y108.py
    if str(patient_id) not in sahipler:
        _iz.kimlikli_yaz(request, "patient.delete", scope=f"id={patient_id}", item_count=0, outcome="bulunamadi")
        raise HTTPException(status_code=404, detail=ceviri.t("hasta.hata.bulunamadi"))
    success = db.delete_patient(patient_id)
    _iz.kimlikli_yaz(
        request,
        "patient.delete",
        scope=f"id={patient_id}",
        item_count=1 if success else 0,
        outcome="ok" if success else "hata",
    )
    if not success:
        raise HTTPException(status_code=500, detail=ceviri.t("hasta.hata.silinemedi"))
    return {"status": "success"}


@router.post("/api/patients/{patient_id}/delete")
def remove_patient_compat(patient_id: str, request: Request):
    """Backward-compatible delete route used by the current Expo app."""
    return remove_patient(patient_id, request)


@router.post("/api/patients/delete_bulk")
def remove_patients_bulk(request: Request, payload: BulkDeletePayload):
    """SEÇİLİ hastaları TEK İŞLEMDE siler (atomik).

    ⚠️ SAHİP BİLDİRİMİ (2026-09-12): "hasta veri tabanında da toplu sil butonu lazım."

    ⚠️ `delete_all` İLE AYNI ŞEY DEĞİL: bu uç YALNIZ operatörün seçtiği kimlikleri siler,
    dolayısıyla `delete_all`ın veteriner-kısıtı burada geçerli değildir — kendi kayıtlarını
    seçip silmek olağan bir iştir. Yine de onay alanı ZORUNLU: kazara/otomatik bir POST
    geri dönülemez biçimde onlarca hasta silmesin (audit B-8.2 deseni).

    ⚠️ Denetim izi: KVKK "unutulma hakkı"nın kanıtı. Hasta ADI YAZILMAZ — iz, sildiği verinin
    ikinci bir kopyası olamaz (tekil silmedeki kuralın aynısı).
    """
    _enforce_patient_auth(request)
    if payload.confirm != "DELETE_SELECTED":
        raise HTTPException(
            status_code=400,
            detail=ceviri.t("hasta.hata.topluSilmeOnaySecili"),
        )
    istenen = sorted({str(x) for x in (payload.patient_ids or []) if str(x or "").strip()})
    if not istenen:
        raise HTTPException(status_code=400, detail=ceviri.t("hasta.hata.silinecekSecilmedi"))
    db = get_patient_database()
    if not db:
        raise HTTPException(status_code=500, detail="Patient DB not initialized")
    # ⚠️ D2.72 (B-6.26 · Y92 · Y104): seçimde BAŞKA (kayıtlı) hekimin kaydı varsa HİÇBİRİ silinmez (403); sahipsiz silinir; kimliksiz 428.
    # Eskiden yalnız onay dizesine bakılıyordu — "Tüm Klinik → Tümünü Seç → Sil" kliniğin kayıtlarını siliyordu
    # (araştırma profili kendisine kapatılan "Tümünü Sil"i böyle dolanıyordu). Kural 2: operatörsüz klinik kısıtsız.
    from servers.silme_yetkisi import sahiplik_kapisi

    sahiplik_kapisi(request, db.operator_sahipleri(istenen), olay="patient.delete_bulk", scope=f"{len(istenen)} hasta")
    try:
        silinen = db.delete_patients_bulk(istenen)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    from servers import audit_log as _iz

    _iz.kimlikli_yaz(
        request,
        "patient.delete_bulk",
        scope=f"{len(istenen)} hasta",
        item_count=silinen,
        outcome="ok" if silinen else "bulunamadi",
    )
    # ⚠️ `istenen` ile `silinen` AYRI raporlanır (bkz. history.delete_bulk): başka bir
    # operatör aynı kaydı bu arada silmiş olabilir; "hepsi silindi" demek yanlış olurdu.
    return {"status": "success", "istenen": len(istenen), "silinen": silinen}


@router.post("/api/patients/delete_all")
def remove_all_patients(request: Request, payload: DeleteAllPayload = DeleteAllPayload()):
    """TÜM hastaları siler — KORUMALI (audit B-8.2): gövdede {"confirm":"DELETE_ALL"} ZORUNLU.
    Eskiden boş POST tüm hastaları geri-dönülemez siliyordu (yalnız middleware auth). Yanlış-tık/
    otomatik-istek koruması; frontend confirm gönderir."""
    _enforce_patient_auth(request)
    # ⚠️ D2.11 (B-2.9 · sahip kararı A-03): kliniğin TAMAMINI silme YALNIZ cihazın kendi ekranından (loopback; tünel /
    # ters-proxy sayılmaz). Telefon ya da ağdaki başka cihaz — geçerli cihaz token'ıyla da — silemez. Eskiden bu uç LAN'dan
    # (ve tünelden) token'sız tek istekle tüm hasta defterini VACUUM'lu siliyordu (ölçüldü).
    # Kapı: tests/test_hasta_TUMUNU_SIL_yalniz_cihazdan_D211_A03.py.
    from servers.auth import cihazin_kendisinden_mi

    if not cihazin_kendisinden_mi(request):
        from servers import audit_log as _iz

        _iz.kimlikli_yaz(request, "patient.delete_all", scope="TUM_HASTALAR", item_count=0, outcome="reddedildi")
        raise HTTPException(
            status_code=403,
            detail=ceviri.t("hasta.hata.tumunuSilYalnizCihaz"),
        )
    # ⚠️ Y106 (S-B.3): kayıtlı operatörlü klinikte kliniğin TAMAMINI silme SEÇİLİ operatör (jeton) ister — kimliksiz (kimse
    # seçili değil, kilit sonrası eski jeton) 428; silme izi o hekimin adına (`kimlikli_yaz` jetondan). Eskiden cihaz ekranından
    # kimliksiz silinip iz sahipsiz kalıyordu. A-03 (yukarıda) AYNEN; operatörsüz klinik (Kural 2) etkilenmez. Kimlik DB'si
    # okunamıyorsa ileti arızayı söyler (Y113). Kapı: tests/test_hasta_TUMUNU_SIL_KIMLIK_ister_Y106.py
    from servers.auth import cozumlenmis_operator, kayitli_operator_var, kimliksiz_detayi

    if kayitli_operator_var() and not cozumlenmis_operator(request):  # beyan YOK → yalnız jeton
        from servers import audit_log as _iz

        _iz.kimlikli_yaz(request, "patient.delete_all", scope="TUM_HASTALAR", item_count=0, outcome="reddedildi")
        raise HTTPException(
            status_code=428,
            detail=kimliksiz_detayi(ceviri.t("hasta.hata.tumunuSilOperatorSecin")),
        )
    if payload.confirm != "DELETE_ALL":
        raise HTTPException(status_code=400, detail=ceviri.t("hasta.hata.topluSilmeOnayTumu"))
    db = get_patient_database()
    if not db:
        raise HTTPException(status_code=500, detail="Patient DB not initialized")
    # Audit P3: atomik clear_all_patients() (DELETE + commit + VACUUM) — eskiden get_all + tek-tek
    # delete (atomik DEĞİL, VACUUM yok → silinen PII freelist'te kurtarılabilir kalıyordu; 300.'de
    # hata → tutarsız durum). count'u silmeden önce al (response doğru olsun).
    # ⚠️ D2.57 (B-3.109): silinen sayı ve VACUUM durumu AYRI — DELETE commit edildikten sonra VACUUM düşerse silme
    # GERÇEKLEŞMİŞTİR: iz "ok" + gerçek sayı + `vacuum: False`, yanıt "success" + `vacuum_ok: false` (arayüz listeyi yeniler ve
    # disk temizliğinin tamamlanamadığını söyler). Eskiden "hata, 0"/"error" — kayıtlar gitmişken.
    # ⚠️ SG.G1: profil bildirildiyse kapsam YALNIZ DARALIR — o profilin listesinde görünen hastalar (araştırmada "Tümünü Sil" veteriner
    # hastalarını silmez). Başlıksız istek bugünkü gibi tamamı (A-03 / Y106 kapıları yukarıda AYNEN).
    _silme_profili = istek_profili(request)
    silinen, vacuum_ok = db.clear_all_patients(profil=_silme_profili)
    ok = silinen >= 0
    # SGI-1.6: kapsam profil süzgeciyle DARALDIYSA iz ve günlük bunu söyler (yoksa "tüm hastalar silindi" yanlış kanıt olur).
    logging.getLogger(__name__).warning(
        "TOPLU HASTA SİLME: %s hasta silindi%s (VACUUM %s).",
        silinen if ok else "HİÇ",
        f" (yalnız profil {_silme_profili})" if _silme_profili else "",
        "tamam" if vacuum_ok else "YAPILAMADI",
    )
    from servers import audit_log as _iz

    _iz.kimlikli_yaz(
        request,
        "patient.delete_all",
        scope="TUM_HASTALAR",
        item_count=silinen if ok else 0,
        outcome="ok" if ok else "hata",
        detail={"vacuum": vacuum_ok, **({"profil": _silme_profili} if _silme_profili else {})},
    )
    if not ok:
        return {"status": "error", "deleted": 0, "detail": ceviri.t("hasta.hata.topluSilinemedi")}
    return {"status": "success", "deleted": silinen, "vacuum_ok": vacuum_ok}
