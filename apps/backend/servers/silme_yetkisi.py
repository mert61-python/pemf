# Author: mertaygn, cglrgrkn
"""Hasta ve seans SİLME yetkisi — sahiplik JETONDAN (D2.72 · B-6.26 · Y92).

⚠️ NEDEN VAR: silme uçları (`patient_router` tekil + toplu, `history_router` tekil ×2 + toplu) yalnız onay dizesine
bakıyordu; kimliksiz ev sahibi ya da başka bir hekim (jetonlu da olsa) bir hekimin hasta ve SEANS (tıbbi kayıt) kayıtlarını
geri dönüşsüz silebiliyordu (DENETIM-06 B-6.26, aday İG-6.4 ölçtü: 200 `7/7`, başka hekim satırı silindi).

KURAL (sahip kararı Y92 — plandan üstün):
  * Cihazda kayıtlı operatör YOKSA (Kural 2: tek hekimli klinik) kısıt YOK — bugünkü gibi silinir. A-01: LAN erişim
    sınıfı değişmez (kimlik kuralıdır, erişim kuralı değil).
  * Kayıtlı operatör VARSA silme kimliği YALNIZ jetondan (`cozumlenmis_operator` beyansız): kimliksiz → 428 "Operatör seçin".
  * Hedeflerden biri bile kimliğe ait değilse (başka hekim ya da SAHİPSİZ — "yalnız KENDİ kayıtları") → 403 ve HİÇBİR kayıt
    silinmez (atomik: toplu silmenin "ya hepsi ya hiçbiri" sözleşmesiyle aynı). "Tüm Klinik" görünümü de değiştirmez.
  * Red izde `reddedildi` olarak kalır (sinyal kaybolmasın); iz kayıt adı/PII taşımaz, yalnız sayılar.
  * Var olmayan kimlikler sahiplik sorusuna girmez (uçların kendi "bulunamadı" davranışı sürer).
Kliniğin TAMAMINI silme (`/api/patients/delete_all`) ayrı kural: A-03 · D2.11.
"""

from __future__ import annotations

from fastapi import HTTPException

KIMLIKSIZ_DETAY = "Operatör seçin — silmek için önce üst bardan hangi hekim olduğunuzu seçin."


def yabanci_detayi(n: int) -> str:
    return (
        f"Yalnız kendi kayıtlarınızı silebilirsiniz — seçimdeki {n} kayıt başka bir hekime ait ya da sahipsiz; "
        "hiçbir kayıt silinmedi."
    )


def sahiplik_kapisi(request, sahipler: dict, *, olay: str, scope: str) -> None:
    """`sahipler` = {kayıt kimliği: kaydın operator_email'i} (YALNIZ var olan kayıtlar). İzinsizse HTTPException atar."""
    from servers import audit_log as _iz
    from servers.auth import cozumlenmis_operator, kayitli_operator_var

    if not kayitli_operator_var():
        return  # Kural 2
    kimlik = cozumlenmis_operator(request)  # beyan YOK → yalnız jeton
    if not kimlik:
        _iz.yaz(request, olay, scope=scope, item_count=0, outcome="reddedildi", detail={"neden": "kimliksiz"})
        raise HTTPException(status_code=428, detail=KIMLIKSIZ_DETAY)
    yabanci = sum(1 for sahip in sahipler.values() if (sahip or "").strip().lower() != kimlik)
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
