# Author: mertaygn, cglrgrkn
"""OPERATÖR JETONLARI — kayıt kime yazılacak, SUNUCU karar verir (2026-08-09 denetimi, Tier 1).

ARIZA
-----
`/api/operators/verify` PIN'i doğruluyor ama yalnız `{ok, email}` dönüyordu: doğrulama ile
sonraki YAZMALAR arasında hiçbir bağ yoktu. `operator_email` her uçta İSTEMCİ BEYANIYDI.
Sonuç: cihaza erişebilen herkes (klinik ağındaki bir cihaz, eski bir mobil kopya, elle atılan
tek bir istek) başka bir hekimin adıyla seans başlatabilir, AI analizi ve hasta kaydı
yazabilirdi. PBKDF2 + kilitlenme + PIN'in tamamı, kimsenin doğrulamadığı bir dize yüzünden
anlamsız kalıyordu — üstelik özelliğin AMACI kaydın doğru hekime atfedilmesiydi.

ÇÖZÜM
-----
PIN doğrulanınca kısa ömürlü bir jeton verilir; yazma yollarında `operator_email` JETONDAN
türetilir, gövdeden değil.

TASARIM KARARLARI
-----------------
* YALNIZ BELLEKTE. Diske yazılmaz — `desktop-session` ile aynı gerekçe: kalıcılık istemci
  tarafındadır, backend yeniden başlarsa operatör PIN'ini yeniden girer (saniyelik iş).
* TTL var ama seans SÜRERKEN de geçerlidir: jetonun ortada ölmesi, süren bir tedavinin
  kaydını sahipsiz bırakırdı. Yenileme her kullanımda (`sliding`) yapılır.
* Jeton `secrets.token_urlsafe` ile üretilir ve HİÇBİR seviyede LOGLANMAZ.
* Kapasite sınırı: klinikte en fazla birkaç operatör olur; sınırsız sözlük, erişimi olan birinin
  bellek şişirmesine açık olurdu.
"""

from __future__ import annotations

import secrets
import threading
import time

#: Jeton ömrü — hareketsizlik sayacı (her kullanımda tazelenir). Klinik vardiyası boyunca
#: operatörün tekrar tekrar PIN girmesi akışı bozardı; 12 saat vardiyayı rahat kapsar.
TTL_SANIYE = 12 * 60 * 60

#: Aynı anda tutulabilecek en fazla jeton (bellek şişirmeye karşı).
_MAX_JETON = 64

_jetonlar: dict[str, dict] = {}
_kilit = threading.Lock()


def _temizle_kilitli(simdi: float) -> None:
    """Süresi dolmuşları at. ÇAĞIRAN kilidi tutuyor olmalı."""
    for t in [t for t, v in _jetonlar.items() if v["son"] + TTL_SANIYE <= simdi]:
        _jetonlar.pop(t, None)


def uret(email: str) -> str:
    """Doğrulanmış operatör için jeton üret. E-posta normalize edilir."""
    e = (email or "").strip().lower()
    if not e:
        raise ValueError("bos e-posta icin jeton uretilemez")
    jeton = secrets.token_urlsafe(32)
    simdi = time.time()
    with _kilit:
        _temizle_kilitli(simdi)
        if len(_jetonlar) >= _MAX_JETON:
            # En eskiyi düşür — yeni doğrulamayı reddetmek kliniği kilitlerdi.
            en_eski = min(_jetonlar, key=lambda t: _jetonlar[t]["son"])
            _jetonlar.pop(en_eski, None)
        _jetonlar[jeton] = {"email": e, "son": simdi}
    return jeton


def cozumle(jeton: str) -> str:
    """Jetondan e-posta. Geçersiz/süresi dolmuşsa "" döner. Geçerliyse TTL tazelenir."""
    t = (jeton or "").strip()
    if not t:
        return ""
    simdi = time.time()
    with _kilit:
        kayit = _jetonlar.get(t)
        if not kayit:
            return ""
        if kayit["son"] + TTL_SANIYE <= simdi:
            _jetonlar.pop(t, None)
            return ""
        kayit["son"] = simdi  # sliding: aktif operatör vardiya boyunca düşmesin
        return kayit["email"]


def iptal(jeton: str) -> bool:
    """Jetonu düşür (operatör kilitle / çıkış)."""
    with _kilit:
        return _jetonlar.pop((jeton or "").strip(), None) is not None


def iptal_email(email: str) -> int:
    """Bir operatörün TÜM jetonlarını düşür — cihazdan çıkarıldığında ZORUNLU, yoksa
    çıkarılmış bir hekim jetonu düşene kadar kayıt yazmaya devam ederdi."""
    e = (email or "").strip().lower()
    with _kilit:
        hedef = [t for t, v in _jetonlar.items() if v["email"] == e]
        for t in hedef:
            _jetonlar.pop(t, None)
        return len(hedef)


def temizle_hepsi() -> None:
    """Tüm jetonları düşür (testler ve kapanış)."""
    with _kilit:
        _jetonlar.clear()


def sayi() -> int:
    """Geçerli jeton sayısı (teşhis/test)."""
    simdi = time.time()
    with _kilit:
        _temizle_kilitli(simdi)
        return len(_jetonlar)
