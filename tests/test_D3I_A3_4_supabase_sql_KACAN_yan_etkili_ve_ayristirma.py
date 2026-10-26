# -*- coding: utf-8 -*-
"""D3I-A3.4 KAPI ADAYI (kapsam 7 sondası) — `scripts/supabase_sql.py` (D3.12 / D3.24 / D3.28, `12ca5599`) yazma kapısı: KENDİ kötü deyim derlemem, GERÇEK
`main()` (argv), sahte EN ALT katta (`urllib.request.urlopen` kaydeder, ağ YOK; PAT ortamdan sahte). Ölçüt: `--yaz`sız istek GİTTİ mi
(rc 3 = RET) ve gidenlerde gövdede `read_only: true` var mı.

D3I doğrulayıcı (F): `pg_` öneki / sistem şeması TEK BAŞINA izin vermez — salt-okur `pg_` yerleşikleri BEYAZ listede (varsayılan ret).
Kara liste yaması `pg_catalog."pg_terminate_backend"()` (tırnaklı ad + sistem şeması), `pg_stat_statements_reset()`,
`pg_copy_*_replication_slot()`, `pg_read_file()` … kaçırıyordu (aşağıda). Beyaz listenin AŞIRI ret riski `OKUMA_KABUL`daki günlük
`pg_` okumalarıyla ölçülür (sahip reddedilen okumada `--yaz`a yönelmesin)."""

from __future__ import annotations

import importlib.util
import io
import json
import sys
from pathlib import Path

import pytest

_KOK = Path(__file__).resolve().parent.parent


def _arac():
    spec = importlib.util.spec_from_file_location("supabase_sql_sonda", _KOK / "scripts" / "supabase_sql.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def kos(monkeypatch, tmp_path):
    m = _arac()
    giden: list = []

    class _Yanit(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def _urlopen(istek, timeout=None):
        giden.append(json.loads(istek.data.decode("utf-8")))
        return _Yanit(b"[]")

    monkeypatch.setattr(m.urllib.request, "urlopen", _urlopen)
    monkeypatch.setenv("SUPABASE_PAT", "sahte-pat-yok")

    def _kos(*argv):
        giden.clear()
        monkeypatch.setattr(sys, "argv", ["supabase_sql.py", "--ref", "sahteref", *argv])
        rc = m.main()
        return rc, list(giden)

    return _kos, tmp_path


#: istem listesi (kapsam 7) — beklenen: --yaz'sız RET (rc 3, istek YOK)
RET_BEKLENEN = [
    "select 1; drop table public.devices",
    "with d as (delete from public.devices returning *) select * from d",
    "explain analyze delete from public.token_ledger",
    "explain (analyze) update public.token_balances set aylik_hak = 0",
    "/* yorum /* ic ice */ */ drop table public.token_ledger",
    "/* a */ select 1; /* b */ drop table x",
    "select * into public.yedek from public.devices",
    "select public.jeton_tuket()",
    "select set_config('default_transaction_read_only', 'off', false)",
    "select lo_import('/etc/passwd')",
    "select dblink_exec('dbname=x', 'drop table y')",
    "select nextval('public.seq')",
    "lock table public.devices",
    "copy public.devices to program 'calc.exe'",
    "do $$ begin delete from public.devices; end $$",
    "call public.temizle()",
    "notify kanal, 'x'",
    "prepare p as delete from public.devices; execute p",
    "vacuum public.devices",
    "select 1 -- yorum ; \n; drop table x",
    "select * from public.devices for update",
    "select * from public.devices for no key update",
    # --- aşağıdakiler: HEAD kapısının KAÇIRDIKLARI (sonda) ---
    'select public."jeton_tuket"()',
    'select "jeton_donem_yenile"(\'0\', 1)',
    'select public.U&"jeton\\005ftuket"()',
    "select pg_terminate_backend(pid) from pg_stat_activity where pid <> pg_backend_pid()",
    "select pg_catalog.pg_cancel_backend(123)",
    "select pg_reload_conf()",
    "select pg_notify('kanal', 'x')",
    "select pg_advisory_lock(1)",
    "select pg_catalog.set_config('search_path', 'evil', false)",
    "select 1 as a$b$; drop table public.devices",
    # --- F: kara liste yamasının da KAÇIRDIKLARI (ve kapsadıklarından örnek) ---
    'select pg_catalog."pg_terminate_backend"(123)',
    "select pg_catalog.\"set_config\"('default_transaction_read_only', 'off', false)",
    'select pg_catalog."pg_reload_conf"()',
    'select pg_catalog."lo_unlink"(1)',
    "select pg_stat_statements_reset()",
    "select pg_copy_logical_replication_slot('a', 'b')",
    "select pg_copy_physical_replication_slot('a', 'b')",
    "select pg_read_file('postgresql.auto.conf')",
    "select pg_ls_dir('.')",
    "select pg_temp.f()",
    # D3I orkestratör: beyaz listedeki AD, sistem dışı şemada (geçici şemaya tanımlanmış gölge işlev) yine RET — `pg_` önekli şemaya
    # genel izin veren mutant ancak bu satırla KIRMIZI olur.
    "select pg_temp.pg_size_pretty(1)",
    'select "pg_catalog".pg_terminate_backend(1)',
    "select pg_catalog . pg_terminate_backend /* x */ (1)",
    "select * from pg_terminate_backend(1)",
    "select PG_RELOAD_CONF()",
    "select pg_switch_wal()",
    "select pg_sleep(600)",
    "select E'\\''; drop table public.devices; -- '",
]

OKUMA_KABUL = [
    "select count(*) from public.devices",
    "table public.devices",
    "values (1), (2)",
    'select "drop" from public.devices',
    "select $etiket$drop table x; delete$etiket$ as metin",
    "select U&'\\0041' as a",
    "select E'it\\'s' as a",
    "select * from pg_stat_activity",
    "select pid, pg_blocking_pids(pid) from pg_stat_activity",
    "with x as (select 1) select * from x",
    # --- F: günlük salt-okur `pg_` yerleşikleri (beyaz liste AŞIRI ret etmesin) ---
    'select "id", "kod" from "public"."devices" where "id" in (1, 2)',
    'select count("id") from public.devices',
    "select pg_size_pretty(pg_database_size(current_database()))",
    "select pg_relation_size('public.devices'), pg_table_size('public.devices'), pg_indexes_size('public.devices')",
    "select pg_get_functiondef('public.jeton_tuket'::regproc)",
    "select pg_get_constraintdef(oid) from pg_constraint where conrelid = 'public.devices'::regclass",
    "select pg_get_userbyid(relowner) from pg_class",
    "select pg_catalog.format_type(atttypid, atttypmod) from pg_attribute",
    "select pg_catalog.pg_get_function_identity_arguments(p.oid) from pg_proc p",
    "select pg_typeof(1), pg_column_size('abc')",
    "select pg_postmaster_start_time(), pg_is_in_recovery(), pg_conf_load_time()",
    "select pg_has_role('anon', 'member'), pg_table_is_visible(oid) from pg_class",
    "select pg_stat_get_live_tuples(oid) from pg_class",
    "select pg_backend_pid(), pg_current_wal_lsn()",
    "select * from pg_stat_statements order by total_exec_time desc limit 5",
    "select * from information_schema.tables where table_schema = 'public'",
]


@pytest.mark.parametrize("sql", RET_BEKLENEN)
def test_YAZ_SIZ_RET(kos, sql):
    k, _ = kos
    rc, giden = k("--sql", sql)
    assert rc == 3 and not giden, f"--yaz'sız GİTTİ (rc={rc}, read_only={[g.get('read_only') for g in giden]}): {sql!r}"


@pytest.mark.parametrize("sql", RET_BEKLENEN[:6])
def test_YAZ_SIZ_RET_dosya_yolu_da(kos, sql):
    k, tmp = kos
    f = tmp / "q.sql"
    f.write_text(sql, encoding="utf-8")
    rc, giden = k("--dosya", str(f))
    assert rc == 3 and not giden


@pytest.mark.parametrize("sql", OKUMA_KABUL)
def test_OKUMA_kabul_ve_read_only_TRUE(kos, sql):
    k, _ = kos
    rc, giden = k("--sql", sql)
    assert rc == 0 and len(giden) == 1 and giden[0]["read_only"] is True and giden[0]["query"] == sql


@pytest.mark.parametrize("arg", ["--canli", "--sema", "--denetim"])
def test_hazir_sorgular_read_only_TRUE(kos, arg):
    k, _ = kos
    rc, giden = k(arg)
    assert rc == 0 and giden and all(g["read_only"] is True for g in giden)


def test_YAZ_ile_read_only_FALSE(kos):
    k, _ = kos
    rc, giden = k("--sql", "drop table x", "--yaz")
    assert rc == 0 and giden[0]["read_only"] is False
