# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""ÇOKLU KLİNİK: BULUT ANAHTAR UZAYI — Supabase denetimi 2026-08-30.

Sahip sorusu: "çoklu klinik kullanımında düşün, Supabase düzgün çalışıyor mu?"

ÖLÇÜLEN ARIZA (canlıda doğrulandı):
`public.treatment_sessions` birincil anahtarı YALNIZ `id` idi. Ama `id`, kliniğin YEREL
SQLite tablosundan gelir ve orada AUTOINCREMENT'tir (`database/treatment_history_db.py`),
yani her klinikte 1, 2, 3… diye başlar. Canlıdaki tek kaydın id'si düpedüz `2` idi.

    Klinik A → id=1 yazar, GLOBAL anahtarı kaplar
    Klinik B → id=1 yazar → `on conflict (id) ... where device_id = p_device_id`
               → WHERE tutmaz → UPDATE yok, INSERT yok, HATA DA YOK
               → B'nin seansı SESSİZCE kaybolur

⚠️ Bu bir güvenlik açığı DEĞİL (kimse başkasının verisini okuyamaz/ezemez — `_pemf_verify_device`
ve `where device_id` korumaları ölçüldü ve sağlam). Bu bir VERİ KAYBI sorunudur ve en kötü yanı
sessiz olmasıdır.

DÜZELTME: anahtar `(device_id, id)`. Canlıda uygulandı ve DAVRANIŞSAL doğrulandı — iki geçici
klinik aynı `id=1` ile yazdı, ikisi de bulutta göründü, sonra temizlendi.

⚠️ `public.patients` AYNI DESENDE AMA GÜVENLİ: oradaki `id` UUID
(`database/patient_database.py` → TEXT PRIMARY KEY; canlı örnek `5819280a-2734-...`).
UUID çakışması pratikte imkânsız → o tabloya KASITLI dokunulmadı (gereksiz şema riski).
Bu dosya o kararı da kilitler: biri `patients.id`i sıralı bir değere çevirirse kapı düşer.
"""

from __future__ import annotations

import re
from pathlib import Path

_KOK = Path(__file__).resolve().parents[1]
_GOC = _KOK / "supabase" / "seans_kimligi_bilesik_anahtar.sql"
_KANONIK = _KOK / "database" / "supabase_secure_v2.sql"
_YEREL_SEANS = _KOK / "database" / "treatment_history_db.py"
_YEREL_HASTA = _KOK / "database" / "patient_database.py"


def _oku(p: Path) -> str:
    assert p.exists(), f"beklenen dosya yok: {p}"
    return p.read_text(encoding="utf-8")


# ── 1) Göç dosyası: anahtar cihaz-kapsamlı ──────────────────────────────────


def test_KRITIK_seans_anahtari_CIHAZ_KAPSAMLI():
    """⚠️ SESSİZ VERİ KAYBININ KİLİDİ: anahtar yalnız `id` olursa ikinci klinik yazamaz."""
    s = _oku(_GOC).lower()
    assert re.search(r"primary key\s*\(\s*device_id\s*,\s*id\s*\)", s), (
        "göç, birincil anahtarı (device_id, id) yapmıyor → çoklu klinikte seanslar çakışır"
    )


def test_KRITIK_upsert_session_CIHAZ_ICI_cakisma_kullaniyor():
    """`on conflict (id)` kalırsa şema düzelse bile RPC eski davranışı sürdürür."""
    for dosya in (_GOC, _KANONIK):
        s = _oku(dosya).lower()
        i = s.find("function public.upsert_session")
        assert i != -1, f"{dosya.name}: upsert_session tanımı yok"
        govde = s[i : s.find("$function$;", i) if "$function$;" in s[i:] else len(s)]
        govde = govde[: govde.find("grant ")] if "grant " in govde else govde
        assert "on conflict (device_id, id)" in govde, (
            f"{dosya.name}: upsert_session hâlâ cihazlar-arası çakışma kullanıyor "
            f"→ ikinci kliniğin seansı sessizce düşer"
        )


def test_cross_tenant_EZME_korumasi_KORUNDU():
    """⚠️ Karşıt-kanıt: bileşik anahtar geldi diye `where device_id` KALDIRILMAMALI.

    Bileşik anahtarla teknik olarak gereksiz görünür; ama anahtar ileride yine değişirse
    bu satır cross-tenant ezmeyi engelleyen SON savunmadır."""
    for dosya in (_GOC, _KANONIK):
        s = _oku(dosya).lower()
        i = s.find("function public.upsert_session")
        govde = s[i : i + 2200]
        assert "where public.treatment_sessions.device_id = p_device_id" in govde, (
            f"{dosya.name}: cihaz-sahiplik kontrolü kaldırılmış — cross-tenant ezme yolu açılır"
        )


def test_secret_dogrulamasi_HER_YAZMADA():
    """Her yazma RPC'si önce cihaz sırrını doğrulamalı; yoksa device_id bilen herkes yazar."""
    s = _oku(_KANONIK).lower()
    for fn in ("upsert_session", "upsert_patient", "resolve_patients", "resolve_sessions"):
        i = s.find(f"function public.{fn}")
        assert i != -1, f"{fn} tanımı yok"
        assert "_pemf_verify_device(p_device_id, p_secret)" in s[i : i + 900], (
            f"{fn} cihaz sırrını doğrulamıyor → device_id (gizli DEĞİL) bilen herkes erişir"
        )


# ── 2) Kararın dayandığı yerel gerçekler ────────────────────────────────────


def test_KRITIK_yerel_seans_id_SIRALI_oldugu_icin_bilesik_anahtar_SART():
    """Düzeltmenin GEREKÇESİNİ kilitler: seans id'si yerelde AUTOINCREMENT.

    Biri bunu UUID'ye çevirirse bileşik anahtar gereksizleşir (ama zararsız kalır); tersi
    daha tehlikeli — bu test, gerekçenin hâlâ geçerli olduğunu görünür tutar."""
    s = _oku(_YEREL_SEANS).lower()
    assert "id integer primary key autoincrement" in s, (
        "seans id üretimi değişmiş — bulut anahtar kararı yeniden değerlendirilmeli "
        "(bu test bilgilendirme amaçlı düşer, düzeltme gerekmeyebilir)"
    )


def test_hasta_id_UUID_oldugu_icin_DOKUNULMADI():
    """⚠️ Kapsam kararı: `patients` tablosuna bilerek dokunulmadı çünkü id UUID.

    Bu test o varsayımı kilitler: hasta id'si sıralı bir değere dönerse `patients` de
    aynı sessiz-kayıp sınıfına girer ve göç oraya da gerekir."""
    s = _oku(_YEREL_HASTA).lower()
    assert "id text primary key" in s, (
        "hasta id'si artık TEXT/UUID değil → patients tablosu da çoklu klinikte çakışabilir; "
        "seans için yapılan göç oraya da uygulanmalı"
    )
    assert "autoincrement" not in s.split("create table if not exists patients")[1][:400], (
        "hasta tablosunda AUTOINCREMENT belirdi → UUID varsayımı çöktü"
    )
