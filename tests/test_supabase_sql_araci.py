# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""`scripts/supabase_sql.py` YAZMA KAPISI.

Bu arac CANLI Supabase projesine baglanir. Tek koruma, "salt okunur sandigim bir cagri semayi
degistirmesin" kapisidir: `--yaz` verilmeden DDL/DML iceren SQL calistirilmaz.

Kapi sessizce gevserse arac hicbir uyari vermeden uretim semasina yazar. Bu yuzden kapinin kendisi test altinda: hem
yakalamasi GEREKENLER hem de yakalamaMASI gerekenler (salt-okunur sorgular bosuna reddedilmemeli) olculur.
D3.12 · D3.24 · D3.28 (B-3.18 · B-9.12 · B-10.26): kapi satir basi regex'i iken `select 1; drop table x` (tek satir),
`explain analyze delete`, CTE-DML, `/* */ drop`, `select into`, `merge`, yan etkili RPC ve `--dosya` geciyordu (40 girdiden 21) →
deyim duzeyinde varsayilan-ret kapisi (`_yazma_nedeni`) + `--yaz`siz her istekte `read_only: true`. Sahte yalniz EN ALT katta:
`urllib.request.urlopen` (ag yok) ve PAT okuyucu.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_KOK = Path(__file__).resolve().parent.parent


def _arac():
    yol = _KOK / "scripts" / "supabase_sql.py"
    spec = importlib.util.spec_from_file_location("supabase_sql_araci", yol)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


YAZMA_SQL = [
    "drop table public.token_ledger",
    "DROP TABLE public.token_ledger",
    "  delete from public.token_balances",
    "update public.token_balances set aylik_hak = 0",
    "insert into public.token_ledger (user_id) values (null)",
    "alter table public.devices add column x int",
    "truncate public.token_ledger",
    "grant all on public.token_balances to anon",
    "revoke select on public.devices from authenticated",
    "create or replace function public.jeton_tuket() returns void as $$ begin end $$;",
    # Coklu deyim: ilk satir masum, ikinci satir yikici. MULTILINE kapisi bunu gormeli.
    "select 1;\ndrop table public.token_balances;",
    # D3.12 / D3.24 / D3.28 — eski satir basi regex'inin kacirdiklari:
    "select 1; drop table public.token_balances",
    "explain analyze delete from public.token_ledger",
    "with d as (delete from public.devices returning 1) select 1",
    "/* bakim */ drop table public.token_ledger",
    "select * into public.yedek from public.token_ledger",
    "merge into public.token_balances b using x on true when matched then delete",
    "select public.jeton_tuket()",
    "select jeton_donem_yenile('0', 1)",
    "lock table public.token_ledger",
    "select * from public.token_balances for update",
    "analyze public.token_ledger",
    "set role postgres",
    # deyim bölme: ikinci deyim okuma ile BAŞLAMIYOR (analyze içte yazma sözcüğü değil — yalnız deyim başı kuralı yakalar)
    "select 1; analyze public.token_ledger",
]

OKUMA_SQL = [
    "select count(*) from public.devices",
    "select * from pg_stat_activity",
    "  select tablo from bilgi",
    "with x as (select 1) select * from x",
    "explain select * from public.token_ledger",
    # Yorum icindeki 'drop' bir deyim degildir; bosuna reddetmek araci kullanilamaz kilar.
    "-- drop table public.x\nselect 1",
    "select 'drop table x; delete' as metin",
    "select 1 /* ; drop table x */",
    "select now(), coalesce(a, 0)::numeric(10,2) from t where id in (1, 2)",
    "show search_path",
    "select has_table_privilege('anon', 'public.devices', 'select')",
]


@pytest.mark.parametrize("sql", YAZMA_SQL)
def test_KRITIK_yazma_SQL_i_kapiya_takilir(sql):
    """Kapi gevserse arac, salt-okunur sanilan bir cagriyla URETIM semasini degistirir."""
    assert _arac()._yazma_nedeni(sql), f"YAZMA olan SQL kapiya TAKILMADI -> `--yaz` olmadan calisirdi: {sql!r}"


@pytest.mark.parametrize("sql", OKUMA_SQL)
def test_KARSIT_KANIT_salt_okunur_SQL_bosuna_reddedilmez(sql):
    """Asiri-genisleme korumasi: her sorguyu reddeden bir kapi, araci kullanilamaz kilar
    ve kullaniciyi her seferinde `--yaz` yazmaya alistirir (kapinin amacini yok eder)."""
    assert not _arac()._yazma_nedeni(sql), f"salt-okunur SQL yanlislikla YAZMA sayildi: {sql!r}"


def test_KRITIK_arac_token_i_ASLA_yazdirmaz():
    """Depo PUBLIC. Arac ciktisinin gunluge/ekrana dusmesi olagan; token oraya sizmamali."""
    import re as _re

    kaynak = (_KOK / "scripts" / "supabase_sql.py").read_text(encoding="utf-8")

    # ⚠️ TEST GUCLENDIRILDI (M21 ilk turda KACTI): once "her `_pat()` satirinda 'Authorization'
    # gecsin" deniyordu. Ayni SATIRA ikinci bir baslik eklemek (X-Debug: _pat()) kapiyi asiyordu.
    # Dogru olcu SAYIMDIR: token okuyucu TEK bir yerde cagrilmali, o da Bearer basligi olmali.
    # `def _pat()` tanimin kendisidir, cagri degil — sayimdan dusulur.
    cagri = [m for m in _re.finditer(r"(?<!def )_pat\(\)", kaynak)]
    assert cagri, "token okuyucu hic cagrilmiyor (test kor kalmis)"
    assert len(cagri) == 1, (
        f"token okuyucu {len(cagri)} yerde cagriliyor; tek cagri (Authorization) olmali — "
        "ikinci kullanim token'i baska bir baslik/gunluk/ciktiya sizdirabilir"
    )
    assert _re.search(r'"Authorization":\s*f"Bearer \{_pat\(\)\}"', kaynak), (
        "tek `_pat()` cagrisi Authorization: Bearer basligi DEGIL"
    )
    assert "print(_pat" not in kaynak and "print(tok" not in kaynak, "token yazdiriliyor"


# ── D3.24: GERCEK main() — reddedilen SQL'de AG'A HIC CIKILMAZ; --dosya ayni kapidan; --yaz'siz istek read_only ──
@pytest.fixture
def ana(monkeypatch, tmp_path):
    import json as _json

    arac = _arac()
    istekler: list[dict] = []

    class _Yanit:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return b"[]"

    def _urlopen(istek, timeout=None):
        istekler.append(_json.loads(istek.data.decode("utf-8")))
        return _Yanit()

    monkeypatch.setattr(arac.urllib.request, "urlopen", _urlopen)
    monkeypatch.setattr(arac, "_pat", lambda: "sahte-pat")

    def kos(*argv: str) -> int:
        monkeypatch.setattr("sys.argv", ["supabase_sql.py", "--ref", "abcdefghijklmnopqrst", *argv])
        return arac.main()

    return kos, istekler, tmp_path


@pytest.mark.parametrize("sql", YAZMA_SQL[-12:])
def test_KRITIK_D3_24_reddedilen_SQL_rc3_ve_AGA_CIKILMAZ_sql_ve_dosya(ana, sql):
    kos, istekler, tmp = ana
    assert kos("--sql", sql) == 3 and istekler == [], f"--sql ile gitti: {sql!r}"
    f = tmp / "x.sql"
    f.write_text(sql, encoding="utf-8")
    assert kos("--dosya", str(f)) == 3 and istekler == [], f"--dosya ile gitti: {sql!r}"


def test_KRITIK_D3_24_yazsiz_istek_READ_ONLY_yazli_degil(ana):
    kos, istekler, tmp = ana
    assert kos("--sql", "select count(*) from public.devices") == 0
    assert istekler[-1] == {"query": "select count(*) from public.devices", "read_only": True}
    assert kos("--sql", "drop table public.x", "--yaz") == 0
    assert istekler[-1]["read_only"] is False
