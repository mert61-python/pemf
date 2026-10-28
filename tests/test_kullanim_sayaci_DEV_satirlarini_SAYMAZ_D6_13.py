# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""D6.13 (B-3.60) — sitedeki "Aktif cihaz (30 gün)" sayısını veren `usage_counts()` `-dev` etiketli geliştirme / Docker satırlarını SAYMAZ.

ÖLÇÜLEN (HEAD ebf1c3fe, 2026-10-28): `servers/sync_worker._cihaz_adi` launcher'sız (elle / test / Docker / derleme dizini) her
backend'in bulut kaydını `<ad>-dev` adıyla yazar ve envanter için "süzmek için: `where name not like '%-dev'`" der (sahip kararı
2026-08-30: engelleme değil ETİKETLEME). Ama `apps/backend/database/supabase_kullanim_sayaci.sql` `usage_counts` gövdesi `devices`
tablosunu SÜZMEDEN sayıyordu → site "Aktif cihaz (30 gün)" (`apps/web` `DownloadStats` → `devices_active`) geliştirici makinelerini /
Docker koşularını klinik cihazı gibi gösteriyordu.

Kapı: fonksiyon gövdesi DOSYADAN alınır (SQL yorumları atılır), bellek-içi SQLite'ta Postgres'e özgü üç kalıp eşlenerek
(`::bigint` atılır · `now() - interval 'N days'` → `datetime('now','-N days')` · `public` / `auth` şemaları ATTACH) koşulur.
Ağ / Supabase YOK; canlıya HİÇBİR ŞEY uygulanmaz (Y172: canlı adım sahiple).
"""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path

KOK = Path(__file__).resolve().parents[1]
SQL = KOK / "apps" / "backend" / "database" / "supabase_kullanim_sayaci.sql"
SYNC = KOK / "apps" / "backend" / "servers" / "sync_worker.py"


def _govde() -> str:
    metin = SQL.read_text(encoding="utf-8")
    metin = re.sub(r"/\*.*?\*/", " ", metin, flags=re.S)
    metin = re.sub(r"--[^\n]*", " ", metin)
    m = re.search(r"function\s+public\.usage_counts\s*\(\s*\).*?\bas\s+\$\$(.*?)\$\$\s*;", metin, flags=re.S | re.I)
    assert m, "usage_counts gövdesi bulunamadı — kapıyı yeniden ölçün"
    return m.group(1)


def _sqlite_icin(govde: str) -> str:
    g = re.sub(r"::\s*bigint", "", govde, flags=re.I)
    g = re.sub(
        r"now\(\)\s*-\s*interval\s*'(\d+)\s+days'", lambda m: f"datetime('now','-{m.group(1)} days')", g, flags=re.I
    )
    assert "interval" not in g.lower() and "::" not in g, f"aparat: eşlenmeyen Postgres kalıbı kaldı: {g}"
    return g.strip().rstrip(";")


def _kos(cihazlar: list[tuple[str, str | None, int]]) -> tuple[int, int, int]:
    """cihazlar: (device_id, name, kaç gün önce görüldü)."""
    c = sqlite3.connect(":memory:")
    try:
        c.execute("attach database ':memory:' as public")
        c.execute("attach database ':memory:' as auth")
        c.execute("create table public.devices (device_id text primary key, name text, last_seen text)")
        c.execute("create table auth.users (id text, email_confirmed_at text)")
        c.executemany("insert into auth.users values (?, ?)", [("u1", "2026-10-01 10:00:00"), ("u2", None)])
        c.executemany(
            "insert into public.devices values (?, ?, datetime('now', ?))",
            [(d, ad, f"-{gun} days") for d, ad, gun in cihazlar],
        )
        return tuple(c.execute(_sqlite_icin(_govde())).fetchone())
    finally:
        c.close()


def test_KRITIK_aktif_cihaz_sayisi_DEV_satirlarini_saymaz():
    accounts, toplam, aktif = _kos(
        [
            ("klinik-1", "PEMF-Vet", 1),  # gerçek klinik cihazı
            ("dev-1", "PEMF-Vet-dev", 1),  # launcher'sız geliştirici koşusu
            ("dev-2", "Klinik-B-dev", 2),  # özel adlı (PEMF_DEVICE_NAME) geliştirici koşusu
        ]
    )
    assert accounts == 1, f"aparat: doğrulanmış hesap sayısı bozuldu: {accounts}"
    assert aktif == 1, f"usage_counts '-dev' satırlarını AKTİF CİHAZ sayıyor: {aktif} (beklenen 1)"
    assert toplam == 1, f"usage_counts '-dev' satırlarını KURULU CİHAZ sayıyor: {toplam} (beklenen 1)"


def test_adsiz_ve_benzer_adli_gercek_cihazlar_SAYILIR_bayat_satir_aktif_sayilmaz():
    _, toplam, aktif = _kos(
        [
            ("eski-surum", None, 3),  # ad alanı boş (eski istemci) — gerçek cihaz, SAYILIR
            ("ad-dev-ici", "PEMF-dev-Vet", 3),  # '-dev' SONDA değil → geliştirme etiketi DEĞİL
            ("bayat", "PEMF-Vet", 45),  # 30 günden eski → toplamda var, aktifte YOK
        ]
    )
    assert toplam == 3, f"usage_counts adsız / '-dev'i sonda olmayan gerçek cihazı düşürüyor: toplam={toplam}"
    assert aktif == 2, (
        f"usage_counts aktif sayısı yanlış (30 gün penceresi bozuldu ya da gerçek cihazı '-dev' sanıyor): aktif={aktif}"
    )


def test_suzgec_ETIKETLEYICI_ile_ayni_soneki_kullanir():
    """`_cihaz_adi` hangi soneki yazıyorsa sayaç onu süzer (iki taraf ayrışırsa sayaç yeniden şişer)."""
    kaynak = SYNC.read_text(encoding="utf-8")
    assert 'ad = f"{ad}-dev"' in kaynak and "where name not like '%-dev'" in kaynak, (
        "sync_worker._cihaz_adi'nin '-dev' etiketi değişti — usage_counts süzgecini yeniden ölçün"
    )
    assert "'%-dev'" in _govde(), "usage_counts gövdesi '-dev' sonekini süzmüyor"
