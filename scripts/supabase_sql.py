# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""Supabase'e SQL calistirma + canli sorgu izleme (Management API uzerinden).

NEDEN BU ARAC: depoda Supabase'e SQL uygulamanin tek yolu panele elle yapistirmakti
(`docs/JETON-SISTEMI.md` Adim 1). Bu, (a) sema goc kaydi birakmaz, (b) "su an hangi sorgu
kosuyor / hangi tablo kilitli" sorusunu hic cevaplayamaz.

⚠️ NEDEN service_role ANAHTARI YETMEZ: `service_role` REST/RPC icindir; DDL calistiramaz ve
`pg_stat_activity` okuyamaz. Bunun icin **Personal Access Token (PAT)** gerekir:
    Supabase panel → sag ust profil → Account → Access Tokens → Generate new token

TOKEN NEREYE KONUR (biri yeterli, sirayla aranir):
  1. ortam degiskeni  SUPABASE_PAT
  2. dosya            %USERPROFILE%\\pemf-supabase-pat.txt      (tek satir, sadece token)
  3. dosya            <PEMF_DATA_DIR>/pemf_secrets.json  →  operator.supabase_pat

⚠️ TOKEN DEPOYA GIRMEZ. Depo PUBLIC. Yukaridaki yollarin ucu de git disidir; bu dosya token'i
ASLA yazdirmaz ve diske kopyalamaz.

PROJE REF: `pemf_secrets.json` icindeki `embedded.supabase_url` adresinden cikarilir
(https://<ref>.supabase.co -> <ref>). `--ref` ile elle de verilebilir.

KULLANIM
--------
  # Canli sorgular + kilitler (SALT OKUNUR)
  python scripts/supabase_sql.py --canli

  # Sema ozeti (tablolar, RLS durumu, RPC'ler)
  python scripts/supabase_sql.py --sema

  # Serbest SORGU (salt okunur; yazma denemesi REDDEDILIR)
  python scripts/supabase_sql.py --sql "select count(*) from public.devices"

  # GOC UYGULA (yazma) — acikca istenmeli
  python scripts/supabase_sql.py --dosya database/supabase_jetonlar.sql --yaz

⚠️ YAZMA KAPISI: `--yaz` verilmeden SQL icinde DDL/DML gorulurse arac CALISTIRMAZ. Amac,
"okuyacagim" diye acilan bir oturumun yanlislikla semayi degistirmesini onlemektir.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

API = "https://api.supabase.com/v1"

# Yazma sayilan ilk anahtar kelimeler. `--yaz` yoksa bunlardan biri gorulurse durulur.
_YAZMA = re.compile(
    r"^\s*(insert|update|delete|drop|alter|create|truncate|grant|revoke|comment|"
    r"refresh|reindex|vacuum|call|do|copy|security\s+label)\b",
    re.I | re.M,
)


def _pat() -> str:
    tok = (os.getenv("SUPABASE_PAT") or "").strip()
    if tok:
        return tok
    dosya = Path(os.path.expanduser("~")) / "pemf-supabase-pat.txt"
    if dosya.exists():
        tok = dosya.read_text(encoding="utf-8", errors="replace").strip()
        if tok:
            return tok
    for aday in _sir_dosyalari():
        try:
            d = json.loads(aday.read_text(encoding="utf-8", errors="replace"))
        except Exception:
            continue
        tok = str((d.get("operator") or {}).get("supabase_pat") or "").strip()
        if tok:
            return tok
    sys.exit(
        "HATA: Supabase Personal Access Token bulunamadi.\n"
        "  Panel -> Account -> Access Tokens -> Generate new token, sonra:\n"
        "    setx SUPABASE_PAT <token>        (yeni kabuk gerekir)\n"
        "  ya da tek satir olarak:  %USERPROFILE%\\pemf-supabase-pat.txt"
    )


def _sir_dosyalari():
    yollar = []
    veri = (os.getenv("PEMF_DATA_DIR") or "").strip()
    if veri:
        yollar.append(Path(veri) / "pemf_secrets.json")
    yollar.append(Path(r"C:\ProgramData\PEMF_System\PEMF_GUI\pemf_secrets.json"))
    return [p for p in yollar if p.exists()]


def _ref(elle: str | None) -> str:
    if elle:
        return elle
    for aday in _sir_dosyalari():
        try:
            d = json.loads(aday.read_text(encoding="utf-8", errors="replace"))
        except Exception:
            continue
        url = str((d.get("embedded") or {}).get("supabase_url") or "")
        m = re.search(r"https://([a-z0-9]+)\.supabase\.co", url)
        if m:
            return m.group(1)
    sys.exit("HATA: proje ref'i bulunamadi. `--ref <proje-ref>` ile verin.")


def calistir(ref: str, sql: str) -> list:
    istek = urllib.request.Request(
        f"{API}/projects/{ref}/database/query",
        data=json.dumps({"query": sql}).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {_pat()}",
            "Content-Type": "application/json",
            # ⚠️ User-Agent ZORUNLU: Management API'nin onundeki Cloudflare, urllib'in varsayilan
            # kimligini (Python-urllib/3.x) reddediyor → HTTP 403 "error code: 1010" (olculdu).
            # Token dogru olsa bile istek API'ye HIC ulasmiyor; hata mesaji da bunu soylemiyor.
            "User-Agent": "pemf-supabase-sql/1.0",
            "Accept": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(istek, timeout=120) as y:
            return json.loads(y.read().decode("utf-8") or "[]")
    except urllib.error.HTTPError as e:
        govde = e.read().decode("utf-8", errors="replace")
        sys.exit(f"HATA {e.code}: {govde[:800]}")


def yazdir(satirlar) -> None:
    if not isinstance(satirlar, list) or not satirlar:
        print("(satir yok)")
        return
    basliklar = list(satirlar[0].keys())
    gen = {b: max(len(b), *(len(str(s.get(b, ""))) for s in satirlar)) for b in basliklar}
    print(" | ".join(b.ljust(gen[b]) for b in basliklar))
    print("-+-".join("-" * gen[b] for b in basliklar))
    for s in satirlar:
        print(" | ".join(str(s.get(b, "")).ljust(gen[b]) for b in basliklar))
    print(f"\n{len(satirlar)} satir")


CANLI = """
select pid,
       state,
       round(extract(epoch from (now() - query_start))::numeric, 1) as saniye,
       wait_event_type as bekleme,
       usename as kullanici,
       left(regexp_replace(query, '\\s+', ' ', 'g'), 110) as sorgu
  from pg_stat_activity
 where datname = current_database()
   and pid <> pg_backend_pid()
   and state <> 'idle'
 order by query_start
"""

KILIT = """
select bekleyen.pid as bekleyen_pid,
       left(regexp_replace(bekleyen.query, '\\s+', ' ', 'g'), 70) as bekleyen_sorgu,
       engelleyen.pid as engelleyen_pid,
       left(regexp_replace(engelleyen.query, '\\s+', ' ', 'g'), 70) as engelleyen_sorgu
  from pg_stat_activity bekleyen
  join lateral unnest(pg_blocking_pids(bekleyen.pid)) as engel(pid) on true
  join pg_stat_activity engelleyen on engelleyen.pid = engel.pid
 where cardinality(pg_blocking_pids(bekleyen.pid)) > 0
"""

SEMA = """
select c.relname as tablo,
       c.relrowsecurity as rls_acik,
       (select count(*) from pg_policy p where p.polrelid = c.oid) as politika,
       pg_size_pretty(pg_total_relation_size(c.oid)) as boyut
  from pg_class c
  join pg_namespace n on n.oid = c.relnamespace
 where n.nspname = 'public' and c.relkind = 'r'
 order by c.relname
"""


# ── CANLI GUVENLIK DENETIMI ──────────────────────────────────────────────────────
# `tests/test_supabase_sql_invariants.py` ayni uc degismezi DOSYALAR uzerinde olcuyor. Ama
# Supabase, dashboard/SQL ile olusturulan HER tabloya anon+authenticated yetkisini VARSAYILAN
# olarak verir — yani depoda tek bir `grant` olmasa bile canlida yetki DURUR. Sapma 2026-08-21'de
# tam boyle bulundu. Dosya testi canliyi goremez; bu mod canliyi olcer.
DENETIM = {
    "1. RLS kapali tablo": """
        select c.relname as tablo
          from pg_class c join pg_namespace n on n.oid = c.relnamespace
         where n.nspname = 'public' and c.relkind = 'r' and not c.relrowsecurity
    """,
    "2. anon/authenticated DOGRUDAN tablo yetkisi": """
        select table_name as tablo, grantee as rol,
               string_agg(privilege_type, ',' order by privilege_type) as yetkiler
          from information_schema.role_table_grants
         where table_schema = 'public' and grantee in ('anon', 'authenticated')
         group by table_name, grantee order by table_name, grantee
    """,
    "3. SECURITY DEFINER + sabit search_path YOK": """
        select p.proname as fonksiyon
          from pg_proc p join pg_namespace n on n.oid = p.pronamespace
         where n.nspname = 'public' and p.prosecdef
           and (p.proconfig is null
                or not exists (select 1 from unnest(p.proconfig) k where k like 'search_path=%'))
    """,
    "5. anon CAGIRABILDIGI SECURITY DEFINER fonksiyon (beklenmeyen)": """
        select p.proname as fonksiyon,
               pg_get_function_identity_arguments(p.oid) as parametreler
          from pg_proc p join pg_namespace n on n.oid = p.pronamespace
         where n.nspname = 'public' and p.prosecdef
           and (p.proacl is null
                or has_function_privilege('anon', p.oid, 'EXECUTE'))
         order by p.proname
    """,
    # BILGI (bulgu DEGIL): RLS acik + sifir politika = her sey reddedilir. Bu, yalnizca
    # SECURITY DEFINER RPC ile erisilen tablolarin ISTENEN sertlestirilmis halidir.
    "BILGI: RLS acik, politika yok (yalniz RPC ile erisilir)": """
        select c.relname as tablo
          from pg_class c join pg_namespace n on n.oid = c.relnamespace
         where n.nspname = 'public' and c.relkind = 'r' and c.relrowsecurity
           and not exists (select 1 from pg_policy p where p.polrelid = c.oid)
    """,
}

# 2 numarali maddede BEKLENEN (kasitli) istisnalar: kullanici kendi abonelik satirini okur.
# 5. madde icin BEKLENEN anon-cagrilabilir fonksiyonlar. Depo NIYETI ile birebir:
#   · resolve_device  → eslestirme (kod ile cihaz bulma), tasarim geregi anon
#   · upsert_device / upsert_patient / upsert_session / resolve_patients / resolve_sessions
#     → cihaz kendi SIRRIYLA kimliklenir (p_secret); anon anahtari tek basina ise yaramaz
#   · usage_counts    → sitedeki sayaclar (yalnizca toplamlar)
# ⚠️ BU LISTEYE EKLEME YAPMADAN ONCE SOR: SECURITY DEFINER + anon = sahibin yetkisiyle calisan,
# herkesin cagirabildigi kod demektir. Sir parametresi YOKSA yeri burasi degildir.
# 2026-08-21'de tam bu yuzden ikisi kapatildi:
#   · jeton_donem_yenile(uuid,int) → anon kendine SINIRSIZ jeton yazabilirdi (fatura baypasi)
#   · _pemf_verify_device(text,text) → cihaz sirri icin DOGRULAMA ORAKULU (kaba kuvvet)
_BEKLENEN_ANON_RPC = {
    "resolve_device",
    "upsert_device",
    "upsert_patient",
    "upsert_session",
    "resolve_patients",
    "resolve_sessions",
    "usage_counts",
}

# ⚠️ BOS OLMASI KASITLIDIR (sahip karari 2026-08-21: "okumalari RPC'ye tasi").
# Burada bir donem su uc istisna vardi:
#     ("subscriptions" | "token_balances" | "token_ledger", "authenticated", "SELECT")
# Cunku okuma "RLS ile kendi satirini oku" desenine dayaniyordu ve Postgres'te RLS politikasi
# TEK BASINA yetmez — rolun tablo SELECT yetkisi de gerekir. Okumalar
# `database/supabase_okuma_rpc.sql` ile SECURITY DEFINER fonksiyonlara tasindi; artik HICBIR
# tabloda rol yetkisi yok ve `alter default privileges` sayesinde yenisi de olusmuyor.
# ⚠️ BURAYA ISTISNA EKLEMEK, denetimin kendi kendine arka kapi acmasi demektir. Yeni bir tabloya
# dogrudan erisim gerekiyorsa once "neden RPC olmasin?" sorusu cevaplanmalidir.
_BEKLENEN_YETKI: set = set()


def denetim(ref: str) -> int:
    bulgu = 0
    for baslik, sorgu in DENETIM.items():
        satirlar = calistir(ref, sorgu)
        bilgi = baslik.startswith("BILGI")
        if baslik.startswith("5."):
            satirlar = [s for s in satirlar if s.get("fonksiyon") not in _BEKLENEN_ANON_RPC]
        if baslik.startswith("2."):
            satirlar = [s for s in satirlar if (s.get("tablo"), s.get("rol"), s.get("yetkiler")) not in _BEKLENEN_YETKI]
        print(f"\n=== {baslik} ===")
        if not satirlar:
            print("  temiz")
            continue
        if not bilgi:
            bulgu += len(satirlar)
        yazdir(satirlar)
    print(f"\n{'TEMIZ' if not bulgu else str(bulgu) + ' BULGU'}")
    if bulgu:
        print("Sertlestirme: python scripts/supabase_sql.py --dosya database/supabase_sertlestirme.sql --yaz")
    return 0


def main() -> int:
    a = argparse.ArgumentParser(description="Supabase SQL / canli sorgu araci")
    a.add_argument("--ref", help="proje ref (varsayilan: pemf_secrets.json'dan)")
    a.add_argument("--sql", help="calistirilacak SQL")
    a.add_argument("--dosya", help="calistirilacak .sql dosyasi")
    a.add_argument("--canli", action="store_true", help="calisan sorgular + kilitler")
    a.add_argument("--sema", action="store_true", help="tablolar + RLS durumu")
    a.add_argument("--denetim", action="store_true", help="CANLI guvenlik degismezleri denetimi")
    a.add_argument("--yaz", action="store_true", help="YAZMA izni (DDL/DML icin ZORUNLU)")
    n = a.parse_args()

    ref = _ref(n.ref)

    if n.canli:
        print("=== CALISAN SORGULAR ===")
        yazdir(calistir(ref, CANLI))
        print("\n=== KILITLER (birbirini bekleyenler) ===")
        yazdir(calistir(ref, KILIT))
        return 0

    if n.denetim:
        print(f"=== CANLI GUVENLIK DENETIMI (proje {ref}) ===")
        return denetim(ref)

    if n.sema:
        print(f"=== SEMA (proje {ref}) ===")
        yazdir(calistir(ref, SEMA))
        return 0

    sql = n.sql
    if n.dosya:
        sql = Path(n.dosya).read_text(encoding="utf-8")
    if not sql:
        a.print_help()
        return 2

    if _YAZMA.search(sql) and not n.yaz:
        yasak = _YAZMA.search(sql)
        return _durdur(yasak.group(1) if yasak else "?")

    sonuc = calistir(ref, sql)
    yazdir(sonuc)
    return 0


def _durdur(kelime: str) -> int:
    print(
        f"REDDEDILDI: SQL '{kelime}' iceriyor (yazma islemi) ama `--yaz` verilmedi.\n"
        "Bu kapi kasitlidir: okuma amaciyla acilan bir oturum semayi yanlislikla degistirmesin.\n"
        "Gercekten yazacaksan komutu `--yaz` ile tekrarla.",
        file=sys.stderr,
    )
    return 3


if __name__ == "__main__":
    raise SystemExit(main())
