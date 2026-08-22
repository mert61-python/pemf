# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""KULLANICI ANAHTARIYLA YAPILAN HER OKUMA RPC UZERINDEN OLMALI (sahip karari 2026-08-21).

ARKA PLAN. Canliya ilk SQL erisimi acildiginda su olculdu: `public` semasindaki tablolarin
tamaminda `anon`/`authenticated` rollerine DOGRUDAN tablo yetkisi duruyordu (Supabase'in yeni
tabloya verdigi VARSAYILAN). Sertlestirme turunda hepsi geri alindi; geriye TEK bir istisna
kaldi: `subscriptions` / `token_balances` / `token_ledger` uzerinde `authenticated SELECT`.
O yetki kaldirilamiyordu, cunku okuma yolu "RLS ile kendi satirini oku" desenine dayaniyordu ve
Postgres'te RLS politikasi TEK BASINA yetmez — rolun ayrica tablo SELECT yetkisi de gerekir.

⚠️ SAHIP KARARI: "okumalari RPC'ye tasi." Yani desen degisti — kullanici anahtariyla (anon key
+ kullanici JWT'si) yapilan okumalar artik SECURITY DEFINER RPC uzerinden yapilir; hicbir tabloda
rol yetkisi kalmaz. Boylece:
  · varsayilan yetkiler kaynagindan kapatilabilir (`alter default privileges ... revoke`),
  · yeni bir tablo eklendiginde "yetki verilmis mi?" sorusu HIC dogmaz,
  · dondurulen alan kumesi RPC imzasinda SABITLENIR (istemci `select=*` ile fazla sutun cekemez).

BU DOSYA NEYI KILITLER. Depo genelinde `/rest/v1/<tablo>` bicimli her cagri bir SAPMADIR —
`/rest/v1/rpc/<fonksiyon>` disinda. TEK istisna `service_role` ile yapilan sunucu-ici yazma
yollaridir: service_role RLS'i ve rol yetkilerini zaten baypas eder, RPC'ye tasimak guvenlik
kazanci saglamaz. O cagrilar asagida ACIKCA listelenir; liste disina cikan her sey kirmizidir.
"""

from __future__ import annotations

import re
from pathlib import Path

_KOK = Path(__file__).resolve().parent.parent

# Taranan kaynak agaclari (uretim kodu; testler ve dokumanlar haric).
_AGACLAR = ("pemf-vet-web/api", "pemf-vet-web/src", "pf/src", "servers", "services")
_UZANTI = (".ts", ".tsx", ".py")

# ⚠️ SERVICE_ROLE ISTISNALARI — dosya bazinda. Bu dosyalardaki dogrudan tablo cagrilari
# service_role anahtariyla yapilir (odeme geri-cagrisi / yonetim islemleri). service_role RLS ve
# GRANT'lari baypas ettigi icin RPC'ye tasinmasi guvenlik kazandirmaz.
# ⚠️ LISTEYE EKLEME YAPMADAN ONCE SOR: dosya GERCEKTEN service_role mu kullaniyor? Kullanici
# JWT'si ya da anon anahtariyla yapilan bir okuma buraya YAZILAMAZ — o okuma RPC'ye tasinmalidir.
_SERVICE_ROLE_DOSYALARI = {
    "pemf-vet-web/api/_lib/util.ts",
}

_REST = re.compile(r"rest/v1/(?!rpc\b)([A-Za-z_][A-Za-z_0-9]*)")

# ⚠️ YORUMLAR SOYULUR — yoksa test KENDI BELGESINI hata sanar. Bu tasinma sirasinda tam olarak
# oyle oldu: "eskiden /rest/v1/token_balances okunuyordu" diye yazilan ACIKLAMA satirlari sapma
# olarak raporlandi. Eski yolu yorumda anlatmak dogru ve gereklidir; kapinin gormesi gereken sey
# CALISAN KODDUR. (17. partide C tarafinda ogrenilen dersin aynisi — bkz. tests/c_soyucu.py.)
# Python icin `#` satir yorumu ayrica soyulur; `c_soy` yalnizca // ve /* */ bilir.
_PY_YORUM = re.compile(r"(?m)^([^#\n\"']*?)#[^\n]*$")


def _soy(p: Path, govde: str) -> str:
    from c_soyucu import c_soy  # TS/TSX: string-bilincli // ve /* */ soyucusu (depo deseni)

    if p.suffix == ".py":
        # Docstring'ler de metin tasir; uc-tirnakli bloklari bosalt, sonra # yorumlarini sok.
        govde = re.sub(r'"""[\s\S]*?"""|\'\'\'[\s\S]*?\'\'\'', lambda m: "\n" * m.group(0).count("\n"), govde)
        return _PY_YORUM.sub(r"\1", govde)
    return c_soy(govde)


def _kaynaklar():
    for agac in _AGACLAR:
        kok = _KOK / agac
        if not kok.exists():
            continue
        for p in kok.rglob("*"):
            if p.suffix in _UZANTI and "__tests__" not in p.parts and "node_modules" not in p.parts:
                yield p


def test_KRITIK_kullanici_anahtariyla_DOGRUDAN_tablo_okunmaz():
    sapma = []
    for p in _kaynaklar():
        rel = p.relative_to(_KOK).as_posix()
        if rel in _SERVICE_ROLE_DOSYALARI:
            continue
        soyulmus = _soy(p, p.read_text(encoding="utf-8", errors="replace"))
        for satir_no, satir in enumerate(soyulmus.splitlines(), 1):
            for m in _REST.finditer(satir):
                sapma.append(f"{rel}:{satir_no} -> rest/v1/{m.group(1)}")

    assert not sapma, (
        "Kullanici anahtariyla DOGRUDAN tablo erisimi bulundu. Bu yol artik kapali (sahip karari "
        "2026-08-21): okuma SECURITY DEFINER RPC uzerinden yapilmali, cunku tablolarda hicbir role "
        "GRANT birakilmiyor.\n  " + "\n  ".join(sapma)
    )


def test_KARSIT_KANIT_service_role_istisnasi_GERCEKTEN_service_role_kullaniyor():
    """Asiri-genisleme korumasi: istisna listesi bir arka kapiya donusmesin. Listedeki her dosya
    service_role anahtarini GERCEKTEN kullanmali; kullanmiyorsa istisna gecersizdir."""
    for rel in _SERVICE_ROLE_DOSYALARI:
        p = _KOK / rel
        assert p.exists(), f"istisna listesinde olmayan dosya: {rel}"
        govde = p.read_text(encoding="utf-8", errors="replace")
        assert "SERVICE_ROLE" in govde.upper(), (
            f"{rel} service_role istisnasinda ama service_role anahtarini KULLANMIYOR — "
            "istisna gecersiz, cagri RPC'ye tasinmali"
        )


def test_KRITIK_okuma_RPC_leri_semada_TANIMLI_ve_sertlestirilmis():
    """Istemciler yeni RPC'leri cagiriyorsa, sema onlari SECURITY DEFINER + sabit search_path ile
    tanimlamali ve YALNIZ `authenticated`a acmali (anon'un kullanici satirinda isi yok)."""
    sema = (_KOK / "database" / "supabase_okuma_rpc.sql").read_text(encoding="utf-8", errors="replace")
    for fn in ("abonelik_getir", "jeton_bakiyem", "jeton_defterim"):
        assert f"function public.{fn}" in sema, f"{fn} semada tanimli degil"

    # Her fonksiyon SECURITY DEFINER + sabit search_path (ayricalik yukseltmesi kapisi).
    govdeler = re.split(r"create or replace function", sema)[1:]
    assert len(govdeler) >= 3, "beklenen fonksiyon sayisi bulunamadi"
    for g in govdeler:
        ad = re.match(r"\s*public\.(\w+)", g)
        assert ad, "fonksiyon adi ayristirilamadi"
        assert "security definer" in g.lower(), f"{ad.group(1)}: SECURITY DEFINER degil"
        assert "set search_path" in g.lower(), f"{ad.group(1)}: sabit search_path YOK"

    # anon'a grant verilmemeli.
    for m in re.finditer(r"grant execute on function public\.(\w+)[^;]*to ([a-z_, ]+)", sema):
        assert "anon" not in m.group(2), (
            f"{m.group(1)} anon'a acilmis — bu RPC'ler `auth.uid()` ile calisir, anon'da uid YOK; "
            "acmak yalnizca saldiri yuzeyi ekler"
        )
