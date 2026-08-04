"""Denetim 2026-08-04 (P3): Supabase SQL şemasının güvenlik değişmezleri.

Bulut tarafı bu üründe kimlik doğrulama, cihaz kaydı ve (secure_v2 ile) hasta/seans verisi
taşır; istemciler `anon` anahtarıyla bağlanır. Güvenlik tamamen ÜÇ değişmeze dayanıyor:

  1. Her tabloda RLS AÇIK olmalı. Kapalıysa `anon` anahtarı — ki mobil uygulamanın içinde,
     yani saldırganın elinde — tabloyu doğrudan okur/yazar.
  2. `anon`/`authenticated` rollerine TABLO üzerinde doğrudan GRANT verilmemeli; erişim yalnız
     SECURITY DEFINER RPC'leri üzerinden olmalı (device_id sunucu tarafında zorlanır).
  3. Her SECURITY DEFINER fonksiyonu SABİT `search_path` ile tanımlanmalı. Aksi halde arayan,
     `search_path`'ini değiştirip fonksiyonun çağırdığı adları KENDİ şemasındaki sahte
     nesnelere yönlendirebilir ve kodu tablo-sahibi yetkisiyle çalıştırır (klasik Postgres
     ayrıcalık yükseltmesi).

Denetim sırasında ÜÇÜ DE sağlanıyordu — bu test bir düzeltme değil, SÜRÜKLENME KAPISIDIR:
yeni bir tablo RLS'siz eklenirse ya da yeni bir RPC search_path'siz yazılırsa burada patlar.
SQL'i çalıştırmaz (canlı Postgres gerektirmez); metinsel/yapısal denetim yapar.
"""

import re
from pathlib import Path

import pytest

_SQL_DIR = Path(__file__).resolve().parent.parent / "database"


def _sql_files() -> list[Path]:
    return sorted(_SQL_DIR.glob("*.sql"))


def _strip_comments(text: str) -> str:
    """`--` satır yorumlarını at (yorumdaki 'SECURITY DEFINER' gibi ifadeler yanlış-pozitif yapar)."""
    return "\n".join(l for l in text.split("\n") if not l.strip().startswith("--"))


@pytest.fixture(scope="module")
def sql_bodies() -> dict[str, str]:
    files = _sql_files()
    if not files:
        pytest.skip(f"SQL şeması yok: {_SQL_DIR}")
    return {f.name: _strip_comments(f.read_text(encoding="utf-8", errors="replace")) for f in files}


def test_her_tabloda_rls_acik(sql_bodies):
    """RLS kapalı bir tablo, uygulamaya gömülü `anon` anahtarıyla doğrudan okunur/yazılır."""
    for name, body in sql_bodies.items():
        low = body.lower()
        tables = set(
            re.findall(r"create\s+table\s+(?:if\s+not\s+exists\s+)?(?:public\.)?([a-z_0-9]+)", low)
        )
        rls = set(
            re.findall(
                r"alter\s+table\s+(?:public\.)?([a-z_0-9]+)\s+enable\s+row\s+level\s+security", low
            )
        )
        eksik = tables - rls
        assert not eksik, (
            f"{name}: RLS ACILMAMIS tablo(lar): {sorted(eksik)} — uygulamaya gomulu anon "
            f"anahtariyla dogrudan erisilebilir."
        )


def test_anon_rollerine_dogrudan_tablo_yetkisi_verilmiyor(sql_bodies):
    """Erişim yalnız SECURITY DEFINER RPC'lerinden olmalı (device_id sunucuda zorlanır)."""
    for name, body in sql_bodies.items():
        low = body.lower()
        tables = set(
            re.findall(r"create\s+table\s+(?:if\s+not\s+exists\s+)?(?:public\.)?([a-z_0-9]+)", low)
        )
        for perms, obj, roles in re.findall(
            r"grant\s+([a-z, ]+?)\s+on\s+(?:table\s+)?(?:public\.)?([a-z_0-9.]+)\s+to\s+([a-z_, ]+)",
            low,
        ):
            if obj in tables and ("anon" in roles or "authenticated" in roles):
                pytest.fail(
                    f"{name}: `{obj}` tablosuna DOGRUDAN grant ({perms.strip()} -> {roles.strip()}). "
                    f"RPC disi erisim RLS/device_id zorlamasini baypas eder."
                )


def test_security_definer_fonksiyonlari_sabit_search_path_kullanir(sql_bodies):
    """search_path sabitlenmezse arayan, fonksiyonun cozdugu adlari kacirabilir (yetki yukseltme)."""
    bulunan = 0
    for name, body in sql_bodies.items():
        low = body.lower()
        for m in re.finditer(r"security\s+definer", low):
            bulunan += 1
            # Tanım satırının devamında (aynı ifade içinde) `set search_path` gelmeli.
            pencere = low[m.start() : m.start() + 240]
            satir_bas = low.rfind("\n", 0, m.start()) + 1
            satir = body[satir_bas : body.find("\n", m.start())].strip()
            assert "search_path" in pencere, (
                f"{name}: SABIT search_path'siz SECURITY DEFINER -> {satir[:100]!r}"
            )
    assert bulunan >= 6, (
        f"beklenenden az SECURITY DEFINER bulundu ({bulunan}) — dosyalar tasinmis/silinmis olabilir, "
        f"bu test sessizce anlamsizlasir."
    )
