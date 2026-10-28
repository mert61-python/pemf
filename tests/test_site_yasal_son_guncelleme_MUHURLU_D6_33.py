# -*- coding: utf-8 -*-
"""D6.33 (B-7.21) — yasal sayfaların "Son güncelleme" tarihi YAYINLANAN metnin son değişikliğiyle AYNI (içerik mührü).

🔴 ÖLÇÜLEN (HEAD ebf1c3fe): yedi yasal sayfa (`apps/web/src/pages/Legal.tsx:603` `t('yasal.kabuk.sonGuncelleme', { tarih: COMPANY.updated })`)
"Son güncelleme: 7 Ağustos 2026" diyordu (`config.ts:48` → `icerik.json` `sirket.guncelleme`). Oysa bağlayıcı Türkçe metin o tarihten sonra
değişti: 2026-08-22 iletişim e-postası (COMPANY.email), 2026-10-10 KVKK metni (`92e86e6c` D2.54 anonimleştirme onayı, `bc4469fb` D2.55 maskeleme
onayının süreye bağlılığı — `git show bc4469fb -- apps/web/src/pages/Legal.tsx`). 2026-10-21 i18n göçü (`f69b529e`) metni TR BAYT BAYT aynı taşıdı;
2026-10-22 `52a71d68` yalnız İNGİLİZCE çeviriyi düzeltti (bağlayıcı metin Türkçedir). → Bağlayıcı metnin son değişikliği 10 Ekim 2026.

ÖLÇÜT (git geçmişine BAĞIMLI DEĞİL — CI `actions/checkout` fetch-depth=1, orkestratör notu C2b): yayınlanan TR yasal içeriğin ÖZETİ (SHA-256:
`yasal.json` TR — sayfa kabuğu hariç · yasal belge başlıkları · COMPANY satıcı kimliği) bu dosyadaki MÜHÜRLE eşit olmalı ve ekrandaki tarih mührün
tarihine eşit olmalı. Metin değişip tarih / mühür değişmezse KIRMIZI. Geçmiş kolu (mührün kaynak commit'i gerçekten o gün yasal metni değiştirdi mi)
yalnız geçmiş varken koşar; geçmiş yoksa varsayılan kipte ATLAR, `PEMF_CAPRAZ_KAYNAK_ZORUNLU=1`de DÜŞER.

YASAL METİN DEĞİŞİNCE: (1) `icerik.sirket.guncelleme` TR + EN'i değişikliğin gününe getirin, (2) aşağıdaki `MUHUR`un `ozet`ini (kırmızı iletisindeki
değer), tarihlerini ve `kaynak_commit`ini yenileyin. Yalnız biçim / kod değişikliği (metin aynı) özeti DEĞİŞTİRMEZ.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

KOK = Path(__file__).resolve().parents[1]
if str(KOK) not in sys.path:
    sys.path.insert(0, str(KOK))

import capraz  # noqa: E402

MUHUR = {
    "ozet": "f14ddb36eb04d7a3790e137053457d86f6cb05cb358e2b3619d95f9025fc0a59",
    "tarih_tr": "10 Ekim 2026",
    "tarih_en": "October 10, 2026",
    "tarih_iso": "2026-10-10",
    #: Bağlayıcı TR metni son değiştiren commit (KVKK D2.55) — geçmiş kolu bunu doğrular.
    "kaynak_commit": "bc4469fb",
}

_WEB = KOK / "apps" / "web"
_YASAL_DOSYALARI = ("apps/web/src/pages/Legal.tsx", "apps/web/src/i18n/tr/yasal.json")


def _json(rel: str) -> dict:
    return json.loads((KOK / rel).read_text(encoding="utf-8"))


def _company_kimligi(config_src: str) -> dict[str, str]:
    """`config.ts` COMPANY bloğunun DEĞİŞMEZ alanları (`updated` getter'ı hariç) — satıcı kimliği yasal metnin parçasıdır."""
    m = re.search(r"export const COMPANY = \{(.*?)\n\} as const", config_src, re.S)
    assert m, "config.ts'de COMPANY bloğu bulunamadı — mühür kapısı bayat"
    alanlar = {}
    for k, v in re.findall(r"^\s{2}(\w+):\s*('(?:[^'\\]|\\.)*'|\d+)\s*,", m.group(1), re.M):
        alanlar[k] = v.strip("'")
    assert {"legalName", "address", "taxNo", "mersis", "email", "withdrawalDays"} <= alanlar.keys(), (
        f"COMPANY alanları okunamadı: {sorted(alanlar)}"
    )
    return alanlar


def yasal_icerik_ozeti(kok: Path = KOK) -> str:
    """Yayınlanan TÜRKÇE yasal içeriğin özeti: belgeler (`yasal.json` TR, `kabuk` hariç) + belge başlıkları + satıcı kimliği."""
    yasal = json.loads((kok / "apps/web/src/i18n/tr/yasal.json").read_text(encoding="utf-8"))
    yasal.pop("kabuk", None)
    icerik = json.loads((kok / "apps/web/src/i18n/tr/icerik.json").read_text(encoding="utf-8"))
    hesap = json.loads((kok / "apps/web/src/i18n/tr/hesap.json").read_text(encoding="utf-8"))
    basliklar = {
        **icerik["yasal"],
        "kvkk": hesap["kayit"]["kvkk"],
        "gizlilik": hesap["kayit"]["gizlilik"],
        "kullanimSartlari": hesap["kayit"]["kullanimSartlari"],
    }
    company = _company_kimligi((kok / "apps/web/src/config.ts").read_text(encoding="utf-8"))
    govde = json.dumps(
        {"belgeler": yasal, "basliklar": basliklar, "satici": company}, ensure_ascii=False, sort_keys=True
    )
    return hashlib.sha256(govde.encode("utf-8")).hexdigest()


def test_KRITIK_yasal_metin_DEGISTIYSE_son_guncelleme_ve_muhur_DEGISIR():
    ozet = yasal_icerik_ozeti()
    gorunen = _json("apps/web/src/i18n/tr/icerik.json")["sirket"]["guncelleme"]
    assert ozet == MUHUR["ozet"], (
        "Yayınlanan Türkçe yasal içerik MÜHÜRLENDİĞİ hâlden farklı (yasal.json TR / belge başlıkları / COMPANY satıcı kimliği) ama yasal sayfalar "
        f"'Son güncelleme: {gorunen}' diyor. `icerik.sirket.guncelleme` TR + EN'i değişikliğin gününe getirin ve bu dosyadaki MUHUR'u "
        f"yenileyin: ozet={ozet!r}, tarih_tr / tarih_en / tarih_iso / kaynak_commit."
    )


def test_KRITIK_ekrandaki_tarih_MUHUR_tarihi():
    tr = _json("apps/web/src/i18n/tr/icerik.json")["sirket"]["guncelleme"]
    en = _json("apps/web/src/i18n/en/icerik.json")["sirket"]["guncelleme"]
    assert tr == MUHUR["tarih_tr"], (
        f"yasal sayfalar 'Son güncelleme: {tr}' diyor; mühür {MUHUR['tarih_tr']} (bağlayıcı metnin son değişikliği)"
    )
    assert en == MUHUR["tarih_en"], f"EN 'Last updated: {en}' ↔ mühür {MUHUR['tarih_en']} (aynı gün, iki dil)"


def test_KRITIK_COMPANY_updated_KATALOGDAN():
    """Tarih TEK yerde: COMPANY.updated kataloğu okur (sabit tarih yazılırsa mühür kolu atlanırdı)."""
    src = (_WEB / "src" / "config.ts").read_text(encoding="utf-8")
    assert re.search(r"get updated\(\)\s*\{\s*return i18n\.t\('icerik\.sirket\.guncelleme'\)\s*\}", src), (
        "COMPANY.updated katalogdan okunmuyor"
    )


def _git(*arg: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *arg], cwd=KOK, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60
    )


def test_GECMIS_muhur_kaynak_commiti_O_GUN_yasal_metni_degistirdi():
    """Geçmiş varken: mührün kaynak commit'i tarihle AYNI gün ve yasal metin dosyasına dokunuyor; ondan SONRA bağlayıcı TR metni değiştiren
    commit'ler yalnız bilinen BAYT-EŞİT göç (`f69b529e`, i18n — TR görünüm aynı) olabilir."""
    if _git("cat-file", "-e", f"{MUHUR['kaynak_commit']}^{{commit}}").returncode != 0:
        capraz.atla(
            f"git geçmişinde {MUHUR['kaynak_commit']} yok (sığ klon / CI fetch-depth=1) — mühür geçmiş kolu koşamaz"
        )
    gun = _git("show", "-s", "--format=%cs", MUHUR["kaynak_commit"]).stdout.strip()
    assert gun == MUHUR["tarih_iso"], f"mührün kaynak commit'i {gun} tarihli, mühür {MUHUR['tarih_iso']}"
    dokunan = _git("show", "--name-only", "--format=", MUHUR["kaynak_commit"]).stdout.split()
    assert any(d in _YASAL_DOSYALARI for d in dokunan), f"kaynak commit yasal metne dokunmuyor: {dokunan}"
    sonra = _git("log", "--format=%h", f"{MUHUR['kaynak_commit']}..HEAD", "--", *_YASAL_DOSYALARI).stdout.split()
    bilinmeyen = [h for h in sonra if not "f69b529e".startswith(h[:7])]
    assert not bilinmeyen, (
        f"mühürden SONRA TR yasal metin dosyasına dokunan commit(ler): {bilinmeyen} — metin değiştiyse tarih + mühür yenilenmeli "
        "(yalnız biçim değiştiyse mührün kaynak commit'ini değil bu listeyi gerekçeyle genişletin)"
    )


def test_KARSIT_KANIT_ozet_METNE_duyarli_bicime_duyarsiz(tmp_path):
    """Özet bir cümle eklenince DEĞİŞİR; JSON girinti / anahtar sırası değişince DEĞİŞMEZ."""
    for rel in (
        "apps/web/src/i18n/tr/yasal.json",
        "apps/web/src/i18n/tr/icerik.json",
        "apps/web/src/i18n/tr/hesap.json",
        "apps/web/src/config.ts",
    ):
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_bytes((KOK / rel).read_bytes())
    asil = yasal_icerik_ozeti(tmp_path)
    yol = tmp_path / "apps/web/src/i18n/tr/yasal.json"
    veri = json.loads(yol.read_text(encoding="utf-8"))
    yol.write_text(json.dumps(dict(reversed(list(veri.items()))), ensure_ascii=False, indent=4), encoding="utf-8")
    assert yasal_icerik_ozeti(tmp_path) == asil, (
        "özet yalnız biçim değişikliğine (girinti / anahtar sırası) duyarlı olmamalı"
    )
    veri["kvkk"]["01"] = veri["kvkk"]["01"] + " Ek cümle."
    yol.write_text(json.dumps(veri, ensure_ascii=False), encoding="utf-8")
    assert yasal_icerik_ozeti(tmp_path) != asil, "özet metne eklenen cümleyi GÖRMÜYOR"
    veri["kabuk"]["sonGuncelleme"] = "Değişti: {{tarih}}"
    veri["kvkk"]["01"] = veri["kvkk"]["01"].removesuffix(" Ek cümle.")
    yol.write_text(json.dumps(veri, ensure_ascii=False), encoding="utf-8")
    assert yasal_icerik_ozeti(tmp_path) == asil, "sayfa kabuğu (`kabuk`) yasal metin sayılmamalı"
