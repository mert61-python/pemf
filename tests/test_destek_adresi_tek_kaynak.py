# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""DESTEK E-POSTA ADRESI TEK KAYNAKTAN (sahip karari 2026-08-22).

NEDEN. Sitede ve mobil kunyede destek adresi `destek@v-pemf.com` yaziyordu. 2026-08-22 yayin
dogrulamasinda olculdu: o alan adi KAYITLI DEGIL — bagimsiz cozumleyiciyle `v-pemf.com` ve
`www.v-pemf.com` icin A ve MX kayitlari **NXDOMAIN**, Vercel hesabinda 0 alan adi tanimli.
Yani sitedeki her "bize yazin" baglantisi ve KVKK/Mesafeli Satis/On Bilgilendirme
sayfalarindaki YASAL ZORUNLU iletisim bilgisi calismiyordu; gonderilen mail bounce ederdi.

Adres `ibiatechnology@gmail.com` ile degistirildi. Ama asil kusur adresin YANLIS olmasi degil,
9 ayri yerde ELLE yazilmis olmasiydi — biri degisince otekiler sessizce eski kaliyordu.

Bu dosya iki seyi kilitler:
  1. Olu alan adi hicbir kullanici-goren metne geri donmez.
  2. Adres tek kaynaktan (`config.ts::COMPANY.email`) okunur; kacinilmaz istisnalar ise
     ADIYLA kayitlidir ve tek kaynakla AYNI degeri tasidiklari olculur.

⚠️ IKI DOSYADA ADRES BILEREK STATIK: `DownloadButtons.tsx` ve `Download.tsx`.
`download-gate-wiring.test.ts` o dosyalarda dinamik `href={...}` YASAKLAR — indirme kapisini
atlayan bir baglanti oyle sizabilir. `COMPANY.email`i sablona koymak o guvenlik kapisini
gevsetirdi; bu yuzden onceki yazarin kararina uyulup adres statik birakildi. Karsiligi: bu test
onlarin tek kaynakla ayrismasini yakalar.
"""

from __future__ import annotations

import re
from pathlib import Path

_KOK = Path(__file__).resolve().parents[1]

# Artik kullanilmayan, DNS'te var OLMAYAN alan adi.
_OLU_ALAN = "v-pemf.com"

# Adresi elle tasimasina IZIN VERILEN dosyalar (yukaridaki gerekce).
_STATIK_IZINLI = (
    "pemf-vet-web/src/components/DownloadButtons.tsx",
    "pemf-vet-web/src/pages/Download.tsx",
)

_ARANAN_AGACLAR = ("pemf-vet-web/src", "pf/src", "servers", "launcher/app/ui")
_UZANTI = (".ts", ".tsx", ".py", ".html")
_EPOSTA = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")


def _tek_kaynak() -> str:
    src = (_KOK / "pemf-vet-web" / "src" / "config.ts").read_text(encoding="utf-8", errors="replace")
    m = re.search(r"^\s*email:\s*'([^']+)'", src, re.M)
    assert m, "config.ts icinde COMPANY.email bulunamadi"
    return m.group(1)


def _kaynaklar():
    for agac in _ARANAN_AGACLAR:
        kok = _KOK / agac
        if not kok.exists():
            continue
        for p in kok.rglob("*"):
            if p.suffix in _UZANTI and "node_modules" not in p.parts:
                yield p


def test_KRITIK_olu_alan_adi_KULLANICI_METNINDE_yok():
    """`v-pemf.com` bir daha kullanici-goren metne donmemeli (mail bounce eder)."""
    kalinti = []
    for p in _kaynaklar():
        for no, satir in enumerate(p.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            if _OLU_ALAN not in satir:
                continue
            # Yorum satirlari TARIHCEDIR (neden degistigini anlatir) — kullaniciya gosterilmez.
            kirpik = satir.strip()
            if kirpik.startswith(("//", "*", "/*", "#", "<!--")):
                continue
            kalinti.append(f"{p.relative_to(_KOK).as_posix()}:{no}  {kirpik[:90]}")
    assert not kalinti, (
        f"Kayitli OLMAYAN alan adi ({_OLU_ALAN}) hala kullanici metninde — o adrese gonderilen "
        "mail ULASMAZ:\n  " + "\n  ".join(kalinti)
    )


def test_KRITIK_statik_izinli_dosyalar_tek_kaynakla_AYNI_adresi_tasiyor():
    """Guvenlik kapisi yuzunden adresi elle tasiyan iki dosya, tek kaynaktan AYRISAMAZ."""
    beklenen = _tek_kaynak()
    for rel in _STATIK_IZINLI:
        p = _KOK / rel
        assert p.exists(), f"izin listesindeki dosya yok: {rel}"
        metin = p.read_text(encoding="utf-8", errors="replace")
        adresler = {a for a in _EPOSTA.findall(metin) if not a.endswith((".png", ".svg"))}
        assert adresler, f"{rel} icinde e-posta adresi bulunamadi (kapi kor kalmis olabilir)"
        ayrik = adresler - {beklenen}
        assert not ayrik, (
            f"{rel} tek kaynaktan AYRISMIS: {sorted(ayrik)} != COMPANY.email ({beklenen}). "
            "Adres degistiyse bu dosyalar da elle guncellenmelidir."
        )


def test_KRITIK_mobil_kunye_web_ile_AYNI():
    """`pf/src/config/firma.ts` ayri bir tek-kaynaktir (mobil kunyesi); web ile ayrisamaz."""
    beklenen = _tek_kaynak()
    firma = (_KOK / "pf" / "src" / "config" / "firma.ts").read_text(encoding="utf-8", errors="replace")
    m = re.search(r'eposta:\s*"([^"]+)"', firma)
    assert m, "firma.ts icinde eposta alani bulunamadi"
    assert m.group(1) == beklenen, (
        f"mobil kunye ({m.group(1)}) ile site ({beklenen}) ayristi — kullanici hangisine "
        "yazacagini bilemez ve biri olu olabilir"
    )


def test_KARSIT_KANIT_web_metinleri_adresi_TEK_KAYNAKTAN_okuyor():
    """Asiri-genisleme korumasi: izin listesi buyuyerek 'her yerde elle yazilir'a donmesin.
    Kapiyi gecmenin yolu adresi her dosyaya kopyalamak OLMAMALI."""
    assert len(_STATIK_IZINLI) <= 2, (
        "adresi elle tasiyan dosya sayisi artmis — yeni yerler `COMPANY.email` okumali; "
        "istisna yalnizca indirme-kapisi kurali yuzunden vardir"
    )
