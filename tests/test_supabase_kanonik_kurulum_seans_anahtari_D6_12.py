# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""D6.12 (B-3.59) — README'nin ZORUNLU kurulum sırası tutarlı bir şema kurar: `treatment_sessions` birincil anahtarı ile etkin
`upsert_session`ın `ON CONFLICT` hedefi AYNI.

ÖLÇÜLEN (HEAD ebf1c3fe, 2026-10-28): `apps/backend/database/README.md` zorunlu sıra `supabase_devices.sql → supabase_patients.sql →
supabase_secure_v2.sql`; bileşik anahtar yaması (`supabase/seans_kimligi_bilesik_anahtar.sql`) "Çoklu klinik kullanılacaksa" diye
KOŞULLU. Ama `supabase_patients.sql` tabloyu `id text primary key` ile kuruyor, `supabase_secure_v2.sql` `upsert_session`ı
`on conflict (device_id, id)` ile kuruyor → README'ye uyan YENİ bir kurulumda `(device_id, id)` üzerinde tekil kısıt YOK; PostgreSQL
her seans yazımında "there is no unique or exclusion constraint matching the ON CONFLICT specification" hatası verir (tek klinikte
de). Canlı proje yamalı: PK `(device_id, id)` (SAHIP-CEVAPLARI "Canlı servis değişiklikleri" 2026-10-21).

Düzeltme: kanonik `supabase_patients.sql` tabloyu canlıyla aynı `(device_id, id)` anahtarıyla kurar (v1 RPC'si de aynı hedefi
kullanır); README eski `(id)` anahtarlı projeler için yamayı ZORUNLU gösterir. Canlıya hiçbir şey UYGULANMAZ.
Kapı yalnız dosya okur (SQL yorumları atılarak ayrıştırılır); veritabanı / ağ YOK.
"""

from __future__ import annotations

import re
from pathlib import Path

KOK = Path(__file__).resolve().parents[1]
DB = KOK / "apps" / "backend" / "database"
README = DB / "README.md"
YAMA_ADI = "seans_kimligi_bilesik_anahtar.sql"


def _yorumsuz(sql: str) -> str:
    sql = re.sub(r"/\*.*?\*/", " ", sql, flags=re.S)
    return re.sub(r"--[^\n]*", " ", sql).lower()


def _sutunlar(metin: str) -> frozenset[str]:
    return frozenset(s.strip().strip('"') for s in metin.split(",") if s.strip())


def _tablo_satirlari(bolum: str) -> list[list[str]]:
    satirlar = []
    for s in bolum.splitlines():
        if s.startswith("|") and not re.match(r"^\|\s*-", s):
            satirlar.append([h.strip() for h in s.strip().strip("|").split("|")])
    return satirlar


def _bolum(metin: str, baslik: str) -> str:
    i = metin.find(baslik)
    assert i != -1, f"README'de '{baslik}' bölümü yok — kapıyı yeniden ölçün"
    j = metin.find("\n#", i + len(baslik))
    return metin[i : j if j != -1 else len(metin)]


def _kosulsuz_evet(hucre: str) -> bool:
    return re.sub(r"[*_`]", "", hucre).strip().lower().startswith("evet")


def _zorunlu_dosyalar() -> list[Path]:
    """README'ye göre HER yeni kurulumda çalışan dosyalar, sırasıyla (koşullu satırlar HARİÇ)."""
    metin = README.read_text(encoding="utf-8")
    dosyalar: list[Path] = []
    for s in _tablo_satirlari(_bolum(metin, "## Supabase şeması")):
        if len(s) >= 4 and s[0].isdigit() and _kosulsuz_evet(s[3]):
            dosyalar.append(DB / s[1].strip("`"))
    for s in _tablo_satirlari(_bolum(metin, "### Kurulumdan SONRA elle uygulanan yamalar")):
        if len(s) >= 3 and s[0].startswith("`") and _kosulsuz_evet(s[2]):
            dosyalar.append((DB / s[0].strip("`")).resolve())
    assert dosyalar, "README'de zorunlu SQL dosyası bulunamadı — kapı boşa düşer"
    return dosyalar


TABLO = re.compile(r"create\s+table\s+(?:if\s+not\s+exists\s+)?public\.treatment_sessions\s*\((.*?)\)\s*;", re.S)
PK_EKLE = re.compile(
    r"alter\s+table\s+public\.treatment_sessions\s+add\s+constraint\s+\w+\s+primary\s+key\s*\(([^)]*)\)"
)
PK_DUSUR = re.compile(
    r"alter\s+table\s+public\.treatment_sessions\s+drop\s+constraint\s+(?:if\s+exists\s+)?treatment_sessions_pkey"
)
UPSERT = re.compile(r"create\s+or\s+replace\s+function\s+public\.upsert_session\s*\((.*?)\$\$\s*;", re.S)


def _tablo_pk(govde: str) -> frozenset[str] | None:
    m = re.search(r"primary\s+key\s*\(([^)]*)\)", govde)
    if m:
        return _sutunlar(m.group(1))
    for satir in govde.split(","):
        m = re.match(r"\s*(\w+)\s+\w[^,]*\bprimary\s+key\b", satir)
        if m:
            return frozenset({m.group(1)})
    return None


def _birlesik_sema_olaylari():
    """(dosya, olay, değer) — dosyalar README sırasıyla, olaylar dosya içi sırasıyla."""
    for yol in _zorunlu_dosyalar():
        assert yol.exists(), f"README'deki zorunlu dosya yok: {yol}"
        sql = _yorumsuz(yol.read_text(encoding="utf-8"))
        olaylar = []
        for m in TABLO.finditer(sql):
            olaylar.append((m.start(), "tablo", _tablo_pk(m.group(1))))
        for m in PK_DUSUR.finditer(sql):
            olaylar.append((m.start(), "pk_dusur", None))
        for m in PK_EKLE.finditer(sql):
            olaylar.append((m.start(), "pk_ekle", _sutunlar(m.group(1))))
        for m in UPSERT.finditer(sql):
            c = re.search(r"on\s+conflict\s*\(([^)]*)\)", m.group(1))
            olaylar.append((m.start(), "upsert", _sutunlar(c.group(1)) if c else None))
        for _, olay, deger in sorted(olaylar, key=lambda o: o[0]):
            yield yol.name, olay, deger


def test_KRITIK_zorunlu_kurulum_sirasinda_PK_ile_upsert_session_ON_CONFLICT_ESLESIR():
    pk = None
    tablo_var = False
    upsert_sayisi = 0
    for dosya, olay, deger in _birlesik_sema_olaylari():
        if olay == "tablo" and not tablo_var:  # `create table if not exists` — yalnız İLKİ etkili
            tablo_var, pk = True, deger
        elif olay == "pk_dusur":
            pk = None
        elif olay == "pk_ekle":
            pk = deger
        elif olay == "upsert":
            upsert_sayisi += 1
            assert tablo_var, f"{dosya}: upsert_session tablodan ÖNCE tanımlanıyor"
            assert deger is not None, f"{dosya}: upsert_session'da ON CONFLICT hedefi yok"
            assert deger == pk, (
                f"{dosya}: upsert_session ON CONFLICT {sorted(deger)} ama README'nin zorunlu sırasıyla kurulan "
                f"treatment_sessions birincil anahtarı {sorted(pk) if pk else pk} → yeni kurulumda HER seans yazımı hata verir"
            )
    assert tablo_var and upsert_sayisi >= 2, "aparat: zorunlu sırada tablo / v1 + v2 upsert_session bulunamadı"
    assert pk == frozenset({"device_id", "id"}), f"zorunlu sıra sonunda PK canlıyla aynı değil: {pk}"


def test_bilesik_anahtar_yamasi_ESKI_id_anahtarli_projelerde_ZORUNLU_yazilir():
    metin = README.read_text(encoding="utf-8")
    satir = [
        s for s in _tablo_satirlari(_bolum(metin, "### Kurulumdan SONRA elle uygulanan yamalar")) if YAMA_ADI in s[0]
    ]
    assert len(satir) == 1, f"README'de bileşik anahtar yaması satırı tek olmalı: {len(satir)}"
    zorunlu = satir[0][2]
    assert not re.sub(r"[*_`]", "", zorunlu).strip().lower().startswith("çoklu klinik"), (
        "README bileşik anahtar yamasını yalnız 'çoklu klinik' için zorunlu diyor; PK'si (id) olan HER projede "
        "secure_v2 upsert_session hata verir"
    )
    assert _kosulsuz_evet(zorunlu) and "`(id)`" in zorunlu, (
        "README yamanın PK'si `(id)` olan her projede ZORUNLU olduğunu söylemiyor"
    )
    ikinci = [s for s in _tablo_satirlari(_bolum(metin, "## Supabase şeması")) if s and s[0] == "2"]
    assert ikinci and "(device_id, id)" in ikinci[0][2], (
        "README 2. dosyanın seans anahtarını (device_id, id) diye anmıyor"
    )


def test_bilesik_anahtar_yamasi_YENI_kurulumda_da_GUVENLI_PK_kisit_adi_AYNI_D6_12():
    """Tur 2 (çürütücü): kanonik tablo PK'sini yamanın DÜŞÜRDÜĞÜ adla kurmalı — yama (yanlışlıkla) YENİ kurulumda da koşulursa
    `drop constraint if exists <ad>` eşleşmez ve `add constraint … primary key` "multiple primary keys" ile DÜŞER. Eskiden kısıt
    adı hiçbir kapıda ölçülmüyordu (ad değişse SQL kapılarının hepsi yeşil kalıyordu)."""
    m = TABLO.search(_yorumsuz((DB / "supabase_patients.sql").read_text(encoding="utf-8")))
    assert m, "aparat: supabase_patients.sql'de treatment_sessions tablosu yok"
    ad = re.search(r"constraint\s+(\w+)\s+primary\s+key", m.group(1))
    yama_yolu = (DB / "../../../supabase" / YAMA_ADI).resolve()
    assert yama_yolu.is_file(), f"aparat: README'deki yama dosyası yok: {yama_yolu}"
    yama = _yorumsuz(yama_yolu.read_text(encoding="utf-8"))
    dusen = re.findall(r"drop\s+constraint\s+(?:if\s+exists\s+)?(\w+)", yama)
    eklenen = re.findall(r"add\s+constraint\s+(\w+)\s+primary\s+key", yama)
    assert ad and ad.group(1) in dusen and ad.group(1) in eklenen, (
        f"kanonik PK kısıt adı {ad.group(1) if ad else None!r} yamanın düşürüp kurduğu adla aynı değil "
        f"(düşen {dusen}, kurulan {eklenen}) → yama yeni kurulumda 'multiple primary keys' ile düşer"
    )
