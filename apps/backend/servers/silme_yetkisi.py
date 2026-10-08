# Author: mertaygn, cglrgrkn
"""Hasta ve seans SİLME yetkisi — sahiplik JETONDAN (D2.72 · B-6.26 · Y92).

⚠️ NEDEN VAR: silme uçları (`patient_router` tekil + toplu, `history_router` tekil ×2 + toplu) yalnız onay dizesine
bakıyordu; kimliksiz ev sahibi ya da başka bir hekim (jetonlu da olsa) bir hekimin hasta ve SEANS (tıbbi kayıt) kayıtlarını
geri dönüşsüz silebiliyordu (DENETIM-06 B-6.26, aday İG-6.4 ölçtü: 200 `7/7`, başka hekim satırı silindi).

KURAL (sahip kararı Y92 — plandan üstün):
  * Cihazda kayıtlı operatör YOKSA (Kural 2: tek hekimli klinik) kısıt YOK — bugünkü gibi silinir. A-01: LAN erişim
    sınıfı değişmez (kimlik kuralıdır, erişim kuralı değil).
  * Kayıtlı operatör VARSA silme kimliği YALNIZ jetondan (`cozumlenmis_operator` beyansız): kimliksiz → 428 "Operatör seçin".
  * Hedeflerden biri bile BAŞKA (cihazda kayıtlı) bir hekime aitse → 403 ve HİÇBİR kayıt silinmez (atomik: toplu silmenin "ya
    hepsi ya hiçbiri" sözleşmesiyle aynı). "Tüm Klinik" görünümü de değiştirmez.
  * ⚠️ Y104 (sahip kararı, önerilenden farklı): SAHİPSİZ kayıt — sahibi boş/NULL YA DA cihazda KAYITLI OLMAYAN bir e-posta
    (operatörler kurulmadan önce ortak giriş e-postasıyla yazılanlar) — kimlikli her hekim tarafından HER YERDEN (cihaz, LAN,
    tünel) silinebilir; iz o hekimin adına (uçların `kimlikli_yaz`ı jetondan). Kimlik DB'si okunamıyorsa yalnız sahibi BOŞ kayıt
    sahipsiz sayılır; sahibinin kayıtlı olup olmadığı bilinemeyen kayıt 403 (fail-closed). ⚠️ Risk kaydı (sahip): geri
    dönüşsüz silme yüzeyi geniş. Kapı: tests/test_silme_SAHIPSIZ_KIMLIKLI_her_hekim_her_yerden_Y104.py
  * Red izde `reddedildi` olarak kalır (sinyal kaybolmasın); iz kayıt adı/PII taşımaz, yalnız sayılar.
  * Var olmayan kimlikler sahiplik sorusuna girmez (uçların kendi "bulunamadı" davranışı sürer).
Kliniğin TAMAMINI silme (`/api/patients/delete_all`) ayrı kural: A-03 · D2.11.
"""

from __future__ import annotations

from fastapi import HTTPException

KIMLIKSIZ_DETAY = "Operatör seçin — silmek için önce üst bardan hangi hekim olduğunuzu seçin."


def yabanci_detayi(n: int) -> str:
    return (
        f"Yalnız kendi ve sahipsiz kayıtları silebilirsiniz — seçimdeki {n} kayıt başka bir hekime ait; "
        "hiçbir kayıt silinmedi."
    )


def sahiplik_kapisi(request, sahipler: dict, *, olay: str, scope: str) -> None:
    """`sahipler` = {kayıt kimliği: kaydın operator_email'i} (YALNIZ var olan kayıtlar). İzinsizse HTTPException atar."""
    from servers import audit_log as _iz
    from servers.auth import cozumlenmis_operator, kayitli_operator_epostalari, kimlik_db_okunamiyor, kimliksiz_detayi

    kayitlilar = kayitli_operator_epostalari()  # None = okunamadı (fail-closed)
    if kayitlilar is not None and not kayitlilar:
        return  # Kural 2
    kimlik = cozumlenmis_operator(request)  # beyan YOK → yalnız jeton
    if not kimlik:
        # Y113: kimlik DB'si okunamıyorsa ileti arızayı ve çareyi söyler ("Operatör seçin" DEMEZ); iz nedeni ayırır.
        neden = "kimlik_db_okunamiyor" if kimlik_db_okunamiyor() else "kimliksiz"
        _iz.yaz(request, olay, scope=scope, item_count=0, outcome="reddedildi", detail={"neden": neden})
        raise HTTPException(status_code=428, detail=kimliksiz_detayi(KIMLIKSIZ_DETAY))

    def _yabanci(sahip) -> bool:
        s = (sahip or "").strip().lower()
        if s == kimlik or not s:
            return False  # kendi ya da sahibi boş (Y104)
        return kayitlilar is None or s in kayitlilar  # kayıtlı BAŞKA hekim — ya da bilinemiyor (fail-closed)

    yabanci = sum(1 for sahip in sahipler.values() if _yabanci(sahip))
    if yabanci:
        _iz.yaz(
            request,
            olay,
            operator_email=kimlik,
            scope=scope,
            item_count=0,
            outcome="reddedildi",
            detail={"neden": "sahiplik", "yabanci": yabanci, "istenen": len(sahipler)},
        )
        raise HTTPException(status_code=403, detail=yabanci_detayi(yabanci))
