# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""DENETİM İZİ — HTTP tarafı (2026-08-09 denetimi, Tier 3).

ARIZA: geri dönüşsüz işlemlerin (toplu silme, dışa/içe aktarma, operatör ekleme-çıkarma, PII
redaksiyonu) tek izi 60 MB'lık DÖNEN bir metin log'unda **kimliksiz** tek bir satırdı. "Hasta
kayıtlarım kayboldu" denildiğinde kimin, ne zaman, nereden ve kaç kaydı sildiğini gösterecek
hiçbir şey yoktu — log döndüğünde o satır da yok oluyordu.

Bu modül tek bir iş yapar: **isteği** (IP + kanıtlanmış operatör) **olaya** bağlar ve şifreli
`audit_events` tablosuna ekler (bkz. `database/treatment_history_db.denetim_yaz`).

⚠️ TASARIM KARARI — denetim yazımı işlemi ENGELLEMEZ. Dolu bir disk ya da kilitli bir DB
yüzünden veterinerin veri dışa aktaramaz hâle gelmesi, izin kaybından daha kötüdür. Yazılamayan
iz sessiz de kalmaz: `denetim_yaz` ERROR log'lar.

⚠️ İÇERİK YAZILMAZ. Hasta adı, not, analiz metni buraya GİRMEZ — yalnız kapsam, adet ve sonuç.
Denetim izi, sildiği verinin ikinci bir kopyası olamaz.
"""

import logging

logger = logging.getLogger(__name__)


def istemci_ip(request) -> str:
    """İsteğin geldiği adres. Tünel / beyanlı ters-proxy arkasındaysa istemci adresi de kaydedilir (`<soket> (via <istemci>)`) —
    "127.0.0.1" yazıp gerçek kaynağı kaybetmek denetim izini işe yaramaz kılar.
    D3.34 (B-2.12): `via` yalnız GÜVENİLİR eşten gelen başlıktan (`servers.auth.istemci_adresi`); eskiden her başlık yazılıyordu →
    LAN'daki bir cihaz `X-Forwarded-For: 8.8.8.8` ile ize SAHTE uzak kaynak yazdırıyordu."""
    try:
        from servers.auth import istemci_adresi

        ham = (request.client.host if request.client else "") or ""
        uzak = istemci_adresi(request)
        return f"{ham} (via {uzak})" if uzak and uzak != ham else ham
    except Exception:
        return ""


def _db():
    from servers import api_server as _api

    try:
        return _api._get_treatment_db()
    except Exception:
        return None


def yaz(
    request,
    event_type: str,
    *,
    operator_email: str = "",
    scope: str = "",
    item_count=None,
    outcome: str = "ok",
    detail=None,
) -> bool:
    """Denetim olayını yaz. ASLA istisna atmaz.

    ⚠️ C2-4.1 (2-C incelemesi · Ö.4-Y8): async uçlar bunu OLAY DÖNGÜSÜNDE çağırır; tedavi DB'si başka bir yazıcı tarafından
    kilitliyken INSERT `busy_timeout` (5 sn) kadar bekliyor, döngü donuyor ve ACİL DURDUR bekliyordu (ölçüldü: 9,8 sn; STOP
    donanım kuyruğuna 4,4 sn). Yazım `utils.dongu_disi_yazim.calistir` ile: döngüde tek işçili FIFO yürütücüde, en çok 0,25 sn
    beklenerek (normal yükte yanıt yine yazımdan SONRA döner; DB meşgulse iz işçide tamamlanır — kaybolmaz). Döngü dışından
    çağrı eskisi gibi eşzamanlı. Dönüş: yazıldı → True, yazılamadı → False, arka planda sürüyor → True."""
    try:
        db = _db()
        if db is None:
            logger.error("DENETIM IZI YAZILAMADI (%s): tedavi DB'si yok", event_type)
            return False
        from utils import dongu_disi_yazim

        sonuc = dongu_disi_yazim.calistir(
            db.denetim_yaz,
            event_type,
            operator_email=operator_email or "",
            client_ip=istemci_ip(request) if request is not None else "",
            scope=scope,
            item_count=item_count,
            outcome=outcome,
            detail=detail,
            ad=f"denetim izi ({event_type})",
        )
        return True if sonuc is None else bool(sonuc)
    except Exception:
        logger.exception("denetim izi yazilamadi (%s)", event_type)
        return False


def kimlikli_yaz(request, event_type: str, *, beyan: str = "", **kw) -> bool:
    """`yaz` + operatör kimliğini SUNUCU tarafında çöz.

    İstemcinin gönderdiği e-posta beyanı tek başına yeterli değildir (bkz.
    `servers.auth.cozumlenmis_operator`): kayıtlı bir hekimi kanıtsız taklit eden bir beyan
    denetim izine de o hekimin adıyla girerse, iz delil olmaktan çıkar ve iftiraya dönüşür.
    Kanıtlanamayan beyanda kayıt SAHİPSİZ yazılır ve beyan `detail` içinde ayrıca saklanır.
    """
    try:
        from servers.auth import cozumlenmis_operator

        kimlik = cozumlenmis_operator(request, beyan)
    except Exception:
        kimlik = ""
    if beyan and not kimlik:
        d = dict(kw.pop("detail", None) or {})
        d["kanitsiz_beyan"] = (beyan or "")[:200]
        kw["detail"] = d
    return yaz(request, event_type, operator_email=kimlik, **kw)
