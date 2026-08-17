# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""SUNUCU TAZELİK FİLTRESİ, "CİHAZ KAPALI" TEŞHİSİNİ ÖLÜ KOD YAPIYORDU (denetim 2026-08-17).

`resolve_device` RPC'si satırı SUNUCUDA `last_seen > now() - interval '5 minutes'` ile eliyordu.
İstemci `deviceRegistry.isFresh` de AYNI 5 dakikayı uyguluyor. İki pencere eşit olduğu için bayat
bir satır istemciye HİÇ ulaşamıyor:

  · `_cozumle`nin `if (!isFresh(...)) return { durum: "bayat" }` dalı ULAŞILAMAZ (ölü kod);
  · `agTanisi`nin `bayat → cihaz_kapali` teşhisi de bu yüzden hiç çalışmıyor;
  · kullanıcı `{durum:"yok"}` alıyor ve ekranda **"Kodu kontrol edin"** yazıyor — oysa kod DOĞRU,
    cihaz KAPALI. Bu tam olarak 2026-08-12 saha bildiriminin (`deviceRegistry.ts:80`) tekrarı:
    kullanıcı yanlış yöne bakıp kodu defalarca kontrol ediyor.

DEĞİŞMEZ: sunucu penceresi istemci penceresinden GENİŞ olmalı. Tazelik kararı İSTEMCİDE verilir;
sunucu yalnız kaba bir üst sınır (çöp satır) koyar. Aksi hâlde "çevrimdışı" ile "kod yanlış"
AYIRT EDİLEMEZ.

⚠️ GERİLEME YOK: istemci `STALE_MS` 5 dakikada kalır, yani bayat `tunnel_url` HİÇBİR ZAMAN
kullanılmaz (`pairing.cihazaBaglan` ve `getRemoteUrlForDevice` yalnız `durum === "bulundu"`e
bakıyor). Genişletme sadece SEBEBİ istemciye taşır, bağlanma kararını DEĞİŞTİRMEZ.

⚠️ Bu kapı SQL'i ÇALIŞTIRMAZ (canlı Postgres gerekmez); yorum-soyulu metin denetimi yapar.
"""

import re
from pathlib import Path

import pytest

_KOK = Path(__file__).resolve().parent.parent
_KURULUM_SQL = _KOK / "database" / "supabase_devices.sql"
_CANLI_SQL = _KOK / "supabase" / "resolve_device_bayat_gorunur.sql"
_ISTEMCI_TS = _KOK / "pf" / "src" / "services" / "deviceRegistry.ts"

_BIRIM_SN = {
    "second": 1,
    "seconds": 1,
    "minute": 60,
    "minutes": 60,
    "hour": 3600,
    "hours": 3600,
    "day": 86400,
    "days": 86400,
    "week": 604800,
    "weeks": 604800,
    "month": 2592000,
    "months": 2592000,
    "year": 31536000,
    "years": 31536000,
}


def _yorumsuz(p: Path) -> str:
    """`--` satır yorumlarını at.

    ⚠️ ZORUNLU: bu denetimin kendi eklediği gerekçe yorumları eski `'5 minutes'` metnini AYNEN
    içeriyor. Yorumlar soyulmazsa kapı kendi açıklamasını görüp yanlış-kırmızı verir; daha kötüsü,
    düzeltme geri alındığında yorumdaki metni görüp yanlış-YEŞİL verebilir."""
    if not p.is_file():
        return ""
    return "\n".join(l for l in p.read_text(encoding="utf-8").split("\n") if not l.strip().startswith("--"))


def _resolve_govdesi(metin: str) -> str:
    i = metin.lower().find("function public.resolve_device")
    assert i >= 0, "resolve_device tanimi YOK"
    j = metin.find("$$;", i)
    assert j > i, "resolve_device govdesi kapanmiyor"
    return metin[i:j]


def _pencere_sn(govde: str) -> int:
    """`last_seen > now() - interval 'N birim'` filtresini saniyeye çevir."""
    m = re.search(
        r"last_seen\s*>\s*now\(\)\s*-\s*interval\s*'\s*(\d+)\s+([a-z]+)\s*'",
        govde,
        re.IGNORECASE,
    )
    assert m, (
        "resolve_device'de `last_seen > now() - interval '...'` filtresi YOK/tanimsiz. Filtre "
        "TAMAMEN kaldirilirsa hizmetten cikarilmis eski cihazlar da cozulebilir hale gelir."
    )
    birim = m.group(2).lower()
    assert birim in _BIRIM_SN, f"taninmayan interval birimi: {birim!r}"
    return int(m.group(1)) * _BIRIM_SN[birim]


def _istemci_pencere_sn() -> int:
    """`deviceRegistry.ts` içindeki `STALE_MS` çarpımını hesapla."""
    ts = _ISTEMCI_TS.read_text(encoding="utf-8")
    m = re.search(r"const\s+STALE_MS\s*=\s*([0-9*\s]+);", ts)
    assert m, "istemcide STALE_MS bulunamadi (isim degistiyse bu kapi guncellenmeli)"
    carpanlar = [int(x) for x in re.findall(r"\d+", m.group(1))]
    carpim = 1
    for c in carpanlar:
        carpim *= c
    return carpim // 1000


def test_KRITIK_sunucu_penceresi_ISTEMCIDEN_GENIS(  # noqa: N802
):
    """Ana değişmez: sunucu bayat satırı GEÇİRMELİ, tazeliğe istemci karar vermeli."""
    sunucu = _pencere_sn(_resolve_govdesi(_yorumsuz(_KURULUM_SQL)))
    istemci = _istemci_pencere_sn()
    assert sunucu > istemci, (
        f"resolve_device penceresi ({sunucu} sn) istemci STALE_MS'inden ({istemci} sn) GENIS DEGIL "
        f"-> bayat satir istemciye HIC ulasmaz, `durum:'bayat'` dali ve `agTanisi`nin "
        f"`cihaz_kapali` teshisi OLU KOD olur ve kullanicıya kod yanlis denir."
    )
    assert sunucu >= 7 * 86400, (
        f"pencere ({sunucu} sn) 'uzun suredir kapali cihaz' senaryosunu kapsamiyor: klinik cihazi "
        f"hafta sonu/tatil boyunca kapali kalabilir ve teshis yine 'kod yanlis'a doner."
    )


def test_KARSIT_KANIT_pencere_SINIRSIZ_degil():
    """Karşıt-kanıt: filtreyi tamamen kaldırmak da yanlış (hizmetten çıkmış cihaz çözülür)."""
    sunucu = _pencere_sn(_resolve_govdesi(_yorumsuz(_KURULUM_SQL)))
    assert sunucu <= 400 * 86400, f"pencere ({sunucu} sn) fiilen SINIRSIZ — eski kayitlar da cozulur"


def test_KRITIK_canliya_uygulanacak_SQL_dosyasi_VAR_ve_IMZASI_AYNI():
    """Kurulum betiği yalnız YENİ kurulumları düzeltir; sahadaki proje elle güncellenmeli.

    ⚠️ `database/supabase_devices.sql` v2 kuruluyken TEKRAR ÇALIŞTIRILAMAZ (sırsız aşırı-yükler
    geri gelir; bkz. `database/README.md` uyarısı). Bu yüzden ayrı, YALNIZ `resolve_device`e
    dokunan bir dosya gerekiyor."""
    assert _CANLI_SQL.is_file(), (
        "supabase/resolve_device_bayat_gorunur.sql YOK -> sahadaki canli projede pencere 5 dk "
        "kalir ve duzeltme kullaniciya HIC ulasmaz (kurulum betigi tekrar calistirilamaz)."
    )
    govde = _yorumsuz(_CANLI_SQL)
    low = govde.lower()

    assert _pencere_sn(_resolve_govdesi(govde)) > _istemci_pencere_sn(), (
        "canliya uygulanacak dosyadaki pencere de istemciden genis DEGIL"
    )
    # İmza BİREBİR aynı olmalı: `create or replace` ancak o zaman geçerlidir ve PostgREST'te
    # ikinci bir aşırı-yükleme (PGRST203) yaratmaz.
    assert re.search(
        r"create\s+or\s+replace\s+function\s+public\.resolve_device\s*\(\s*p_code\s+text[^)]*p_device_id\s+text",
        low,
    ), "imza degismis — `create or replace` yerine YENI asiri-yukleme olusur (PGRST203)"
    assert "security definer" in low and "search_path" in low, "SECURITY DEFINER + sabit search_path sart"
    assert "grant execute on function public.resolve_device(text,text) to anon" in low, (
        "`grant execute ... to anon` YOK -> mobil uygulama RPC'yi cagiramaz (revoke sonrasi kilitlenir)"
    )

    # ⚠️ GERİLEME KAPISI: bu dosya `upsert_device`e DOKUNMAMALI. Ona dokunursa v2'nin bcrypt'li
    # imzasının yanına sırsız v1 aşırı-yüklemesi geri gelir ve anon'a yeniden grant edilir —
    # `database/README.md`de yazılı olan tam o tuzak.
    assert "upsert_device" not in low, (
        "dosya `upsert_device`e dokunuyor -> v2 bcrypt modeli bozulur (sirsiz asiri-yuk geri gelir)"
    )


def test_canli_SQL_adimi_BELGELENMIS():
    """Elle çalıştırılacak bir SQL, README'de yazılı değilse fiilen yok sayılır.

    (2026-08-04 denetiminin dersi: `supabase/` dosyaları README'de listelenmediği için hiç
    denetlenmemişti.)"""
    readme = (_KOK / "database" / "README.md").read_text(encoding="utf-8")
    assert "resolve_device_bayat_gorunur.sql" in readme, (
        "elle uygulanacak SQL adimi database/README.md'de YOK -> sahibi calistirmayi bilemez"
    )


if __name__ == "__main__":
    import os

    raise SystemExit(pytest.main([os.path.abspath(__file__), "-v"]))
