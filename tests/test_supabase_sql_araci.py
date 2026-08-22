# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""`scripts/supabase_sql.py` YAZMA KAPISI.

Bu arac CANLI Supabase projesine baglanir. Tek koruma, "salt okunur sandigim bir cagri semayi
degistirmesin" kapisidir: `--yaz` verilmeden DDL/DML iceren SQL calistirilmaz.

Kapi bir REGEX'e dayaniyor; regex sessizce gevserse arac hicbir uyari vermeden uretim semasina
yazar. Bu yuzden kapinin kendisi test altinda: hem yakalamasi GEREKENLER hem de yakalamaMASI
gerekenler (salt-okunur sorgular bosuna reddedilmemeli) olculur.
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
]

OKUMA_SQL = [
    "select count(*) from public.devices",
    "select * from pg_stat_activity",
    "  select tablo from bilgi",
    "with x as (select 1) select * from x",
    "explain select * from public.token_ledger",
    # Yorum icindeki 'drop' bir deyim degildir; bosuna reddetmek araci kullanilamaz kilar.
    "-- drop table public.x\nselect 1",
]


@pytest.mark.parametrize("sql", YAZMA_SQL)
def test_KRITIK_yazma_SQL_i_kapiya_takilir(sql):
    """Kapi gevserse arac, salt-okunur sanilan bir cagriyla URETIM semasini degistirir."""
    assert _arac()._YAZMA.search(sql), f"YAZMA olan SQL kapiya TAKILMADI -> `--yaz` olmadan calisirdi: {sql!r}"


@pytest.mark.parametrize("sql", OKUMA_SQL)
def test_KARSIT_KANIT_salt_okunur_SQL_bosuna_reddedilmez(sql):
    """Asiri-genisleme korumasi: her sorguyu reddeden bir kapi, araci kullanilamaz kilar
    ve kullaniciyi her seferinde `--yaz` yazmaya alistirir (kapinin amacini yok eder)."""
    assert not _arac()._YAZMA.search(sql), f"salt-okunur SQL yanlislikla YAZMA sayildi: {sql!r}"


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
