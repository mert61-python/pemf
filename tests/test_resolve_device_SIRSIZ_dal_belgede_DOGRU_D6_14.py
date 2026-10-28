# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""D6.14 (B-3.61) — `resolve_device`in SIRSIZ `device_id` dalı SQL notlarında doğru anlatılır (davranış karar gereği KALIR).

ÖLÇÜLEN (HEAD ebf1c3fe, 2026-10-28): `apps/backend/database/supabase_secure_v2.sql:86-87` "resolve_device DEĞİŞMEDİ — mobil app cihazı
PAIRING-KODU … ile çözer; … Tünel-URL okuması pairing-kodu-gate'li kalır (v1 doğruydu)" diyor. Oysa `resolve_device` gövdesi
(`supabase_devices.sql`, canlıya uygulanan `supabase/resolve_device_bayat_gorunur.sql`) `(p_device_id is not null and d.device_id =
p_device_id) or (p_code …)` — TAM `device_id`i bilen herkes, pairing kodu OLMADAN son 30 günde görülmüş cihazın `tunnel_url` /
`local_ip`sini okur. Aynı dosyanın başlığı `device_id`in "GİZLİ DEĞİL" olduğunu söylüyor. Dal BİLEREK korunur: eşleşmiş mobil
uygulama keşif merdiveninde kayıtlı kimlikle yeniden bağlanır (`apps/ui/src/services/deviceRegistry.ts` `uzakCihaziKimlikleCoz` →
`getRemoteUrlForDevice`); tünel adresi tek başına yetki vermez (tünel açıkken cihaz API'sinde kimlik doğrulama ZORUNLU).

Kapı yalnız depo dosyalarını okur (SQL yorumları atılarak gövde ayrıştırılır); veritabanı / ağ YOK.
"""

from __future__ import annotations

import re
from pathlib import Path

KOK = Path(__file__).resolve().parents[1]
SQL_DOSYALARI = sorted(
    [
        *(KOK / "apps" / "backend" / "database").glob("*.sql"),
        *(KOK / "supabase").glob("*.sql"),
        *(KOK / "apps" / "ui" / "supabase").glob("*.sql"),
    ]
)
V2 = KOK / "apps" / "backend" / "database" / "supabase_secure_v2.sql"
SIRSIZ_DAL = re.compile(r"p_device_id\s+is\s+not\s+null\s+and\s+d\.device_id\s*=\s*p_device_id")
GATE_IDDIASI = re.compile(r"pairing[\s_-]*kodu[\s_-]*gate", re.I)
#: Tur 2 (çürütücü): aynı iddianın eş anlamlıları ("yalnız eşleştirme koduyla", "pairing koduyla kapılı") — birebir kalıp
#: kaçırıyordu. Olumsuz kullanım ("pairing koduyla KAPILI DEĞİLDİR") EŞLEŞMEZ.
GATE_ESANLAM = re.compile(
    r"(?:yalnız|yalniz|sadece|only)[^\n]{0,30}(?:pairing|eşleştirme|eslestirme)[\s_-]*(?:kod|code)"
    r"|(?:pairing|eşleştirme|eslestirme)[\s_-]*(?:kodu|koduyla|code)[^\n]{0,15}(?:kapılı|kapili|gate)(?!\w*\s*DE[ĞG][İI]L)",
    re.I,
)
UI_KAYIT = KOK / "apps" / "ui" / "src" / "services" / "deviceRegistry.ts"


def _yorumsuz(sql: str) -> str:
    sql = re.sub(r"/\*.*?\*/", " ", sql, flags=re.S)
    return re.sub(r"--[^\n]*", " ", sql)


def _resolve_device_govdeleri() -> dict[str, str]:
    govdeler = {}
    for p in SQL_DOSYALARI:
        temiz = _yorumsuz(p.read_text(encoding="utf-8"))
        for m in re.finditer(
            r"function\s+public\.resolve_device\s*\(.*?\bas\s+\$\$(.*?)\$\$\s*;", temiz, flags=re.S | re.I
        ):
            govdeler[f"{p.relative_to(KOK).as_posix()}@{m.start()}"] = m.group(1)
    return govdeler


def _sirsiz_dal_var() -> bool:
    govdeler = _resolve_device_govdeleri()
    assert govdeler, "aparat: hiçbir .sql dosyasında resolve_device gövdesi bulunamadı"
    return any(SIRSIZ_DAL.search(g) for g in govdeler.values())


def test_KRITIK_sirsiz_device_id_dali_varken_hicbir_SQL_notu_pairing_kodu_GATE_demez():
    if not _sirsiz_dal_var():  # dal bir gün sır isterse "gate" iddiası doğru olabilir — o zaman bu kol denetlemez
        return
    bulunan = []
    for p in SQL_DOSYALARI:
        for no, satir in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
            if GATE_IDDIASI.search(satir) or GATE_ESANLAM.search(satir):
                bulunan.append(f"{p.relative_to(KOK).as_posix()}:{no}: {satir.strip()}")
    assert not bulunan, (
        "resolve_device'in device_id dalı SIRSIZ (pairing kodu istemez) ama not tünel-URL okumasının "
        "pairing-kodu ile kapılı olduğunu söylüyor:\n" + "\n".join(bulunan)
    )


def test_secure_v2_notu_SIRSIZ_device_id_dalini_ve_gerekcesini_soyler():
    assert _sirsiz_dal_var(), "aparat: resolve_device'in sırsız device_id dalı bulunamadı — notu yeniden ölçün"
    metin = V2.read_text(encoding="utf-8")
    i = metin.find("-- NOT: resolve_device")
    assert i != -1, "secure_v2'de resolve_device NOT'u yok"
    # Not bloğu: NOT satırından ilk boş / SQL satırına kadar; kapı-dosyası adı ("Kapı:" satırı) ölçüte KARIŞMAZ.
    blok_satirlari = []
    for s in metin[i:].splitlines():
        if not s.startswith("--"):
            break
        if "Kapı:" not in s:
            blok_satirlari.append(s)
    blok = "\n".join(blok_satirlari)
    assert re.search(r"device_id dalı SIRSIZ", blok), (
        f"secure_v2 resolve_device notu device_id dalının SIRSIZ olduğunu söylemiyor:\n{blok}"
    )
    assert "KAPILI DEĞİL" in blok, f"secure_v2 notu tünel-URL okumasının kodla KAPILI OLMADIĞINI söylemiyor:\n{blok}"
    assert "uzakCihaziKimlikleCoz" in blok, (
        "secure_v2 notu dalın neden korunduğunu (eşleşmiş istemcinin yeniden bağlanması) söylemiyor"
    )
    # Tur 2 (çürütücü, ölçüm bağı): gerekçe olarak anılan istemci işlevi GERÇEKTEN var ve device_id dalıyla çözüyor — eskiden
    # yalnız adın notta geçmesi aranıyordu (işlev kaldırılsa / yeniden adlandırılsa gerekçe bayatlar, kapı yeşil kalırdı).
    ui = UI_KAYIT.read_text(encoding="utf-8")
    m = re.search(r"export\s+(?:async\s+)?function\s+uzakCihaziKimlikleCoz\b(.*?)\n}", ui, re.S)
    assert m and "p_device_id" in m.group(1), (
        f"notun gerekçesi `uzakCihaziKimlikleCoz` {UI_KAYIT.relative_to(KOK).as_posix()}'te yok ya da device_id dalıyla "
        "çözmüyor — notu yeniden ölçün"
    )
