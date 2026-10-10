# -*- coding: utf-8 -*-
# Author: mertaygn
"""HASHICORP VAULT — HASTA ANAHTARI EMANETİ (yedek) yönetimi.

⚠️ BU VAULT UYGULAMANIN ÇALIŞMA-ANI KAYNAĞI **DEĞİLDİR** (sahip kararı 2026-09-13):
    "mevcut sistem çalışsın, anahtar yedeği Vault'ta olsun."

Yani backend hiçbir şekilde değişmedi; hasta veritabanını AÇAN anahtar hâlâ yerel
`pemf_secrets.json` içinde (DPAPI). Vault yalnız o anahtarın **makine-dışı kopyasını** tutar.

⚠️ ÇÖZDÜĞÜ RİSK (ölçüldü 2026-09-13): `auto.sqlcipher_key` yalnız bu makinede ve `DPAPI:`
ile makineye bağlı; `~/pemf-sirlar.pemfsec` onu TAŞIMIYOR. Disk/OS kaybında şifreli hasta
veritabanı KALICI OKUNAMAZ hâle gelirdi. Artık kurtarma token'ıyla anahtar geri alınabilir.

KULLANIM
--------
    python scripts/vault_emanet.py --durum          # mühürlü mü, emanet var mı
    python scripts/vault_emanet.py --ac             # yeniden baslatma SONRASI mühürü aç
    python scripts/vault_emanet.py --kur            # KV + denetim + kurtarma politikasi
    python scripts/vault_emanet.py --yaz            # yerel anahtarlari Vault'a YEDEKLE
    python scripts/vault_emanet.py --token-uret     # 10 yillik KURTARMA token'i uret
    python scripts/vault_emanet.py --dogrula        # Vault'taki kopya yerelle AYNI mi (parmak izi)
    python scripts/vault_emanet.py --tatbikat       # KURTARMA TATBIKATI (KURTARMA token'iyla; gizli istem)
    python scripts/vault_emanet.py --geri-al        # Vault'taki anahtari EKRANA yaz (kurtarma)

⚠️ `--tatbikat` KURTARMA token'iyla kosar (Y86) — felakette elinizde olacak olan odur, kok token DEGIL. Token
`--token` ile ya da (verilmezse) etkilesimli konsolda gizli istemle alinir; yoksa / kok token ise / gecersizse tatbikat
"BASARILI" DEMEZ. Tatbikat token'in kalan omrunu de soyler: bir yildan azsa `--token-uret` ile yenisini uretin (A-84).
Vault adresi varsayilan `http://127.0.0.1:8200`; `PEMF_VAULT_ADRES` ile degistirilebilir.

⚠️ `--dogrula` ile `--tatbikat` AYNI SEY DEGILDIR. İlki iki degerin ayni oldugunu soyler;
ikincisi zincirin tamamini (Vault -> anahtar -> SQLCipher -> okunabilir tablo) gercek DB'nin
bir KOPYASI uzerinde kosturur. Aradaki halkalar (binding surumu, PRAGMA tirnaklamasi, dosya
bicimi) sessizce bozulabilir ve `--dogrula` bunu GOREMEZ. Felaket aninda is gorecek olan
ikincisidir; ikisini de ara ara kosturun.

⚠️ Kök token ve unseal anahtarlari `~/pemf-vault-kurtarma.json` dosyasindadir. O dosya
KAYBOLURSA Vault bir daha ACILAMAZ — emanet de kurtarilamaz. Baska bir makineye kopyalayin.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path


# ── DEPO KÖKÜ + BACKEND YOLU (D0Ö.19/20 · B-10.57, B-9.25) ──────────────────
# ⚠️ F4 taşımasından beri `database` depo kökünde DEĞİL; yalnız kök eklendiği için `tatbikat`
#    `from database.sqlcipher_util import …` satırında ölüyordu (kurtarma tatbikatı hiç koşamadı).
#    Kök İŞARET DOSYASIYLA aranır (scripts/stm_firmware_kimligi.py deseni).
#    Kapı: tests/test_betikler_ACILIYOR.py::test_KRITIK_fonksiyon_ici_ilk_taraf_importlari_COZULUYOR
def _depo_koku(bas: Path) -> Path:
    for aday in (bas, *bas.parents):
        if (aday / "pyproject.toml").is_file() and (aday / "apps" / "backend").is_dir():
            return aday
    raise RuntimeError("depo kökü bulunamadı (işaret: pyproject.toml + apps/backend). Betik depo dışına mı taşındı?")


KOK = _depo_koku(Path(__file__).resolve())
for _yol in (KOK, KOK / "apps" / "backend"):
    if str(_yol) not in sys.path:
        sys.path.insert(0, str(_yol))

#: Vault adresi — varsayılan compose yayını; farklı port / sınama için `PEMF_VAULT_ADRES` (D2.E05).
ADRES = os.environ.get("PEMF_VAULT_ADRES", "").strip() or "http://127.0.0.1:8200"
KURTARMA_DOSYASI = Path.home() / "pemf-vault-kurtarma.json"

#: KV v2 mount + emanet yolu.
MOUNT = "pemf"
EMANET_YOLU = "klinik/hasta-anahtari"

#: Yedeklenecek alanlar — `scripts/hasta_anahtari_emanet.py` ile AYNI küme (tek tanım yeri orası).
from scripts.hasta_anahtari_emanet import ALANLAR, _parmak, _sirlari_oku, _veri_koku  # noqa: E402

POLITIKA_ADI = "pemf-kurtarma"
POLITIKA = f'''
# Hasta anahtari kurtarma — YALNIZ OKUMA.
# Bu politikayla uretilen token, emaneti okuyabilir ama DEGISTIREMEZ/SILEMEZ ve
# Vault'un baska hicbir yerine erisemez. Disk kaybinda kullanilacak olan budur.
path "{MOUNT}/data/{EMANET_YOLU}" {{
  capabilities = ["read"]
}}
path "{MOUNT}/metadata/{EMANET_YOLU}" {{
  capabilities = ["read", "list"]
}}
'''


def _adres_guvenli_mi(adres: str) -> bool:
    """⚠️ E2-3.3: kök token + hasta anahtarları DÜZ HTTP ile yalnız bu makineye (loopback) gider; uzak Vault yalnız https://.
    `PEMF_VAULT_ADRES` (D2.E05) denetimsizdi: `http://<uzak>` verilince `--yaz` kök token'ı ve iki anahtarı düz metin yolluyordu."""
    import ipaddress
    from urllib.parse import urlsplit

    try:
        u = urlsplit(adres)
        if u.scheme == "https":
            return True
        if u.scheme != "http":
            return False
        ana = (u.hostname or "").lower()
        return ana == "localhost" or ipaddress.ip_address(ana).is_loopback
    except ValueError:
        return False


def _istek(yol: str, yontem: str = "GET", govde=None, token: str | None = None, zaman: float = 20.0):
    if not _adres_guvenli_mi(ADRES):
        raise SystemExit(
            f"  HATA: Vault adresi GUVENSIZ ({ADRES}) -> istek GONDERILMEDI. Duz http yalniz bu makinede "
            "(127.0.0.1 / localhost); uzak Vault icin https:// kullanin (PEMF_VAULT_ADRES)."
        )
    veri = json.dumps(govde).encode() if govde is not None else None
    istek = urllib.request.Request(ADRES + yol, data=veri, method=yontem)
    istek.add_header("Content-Type", "application/json")
    if token:
        istek.add_header("X-Vault-Token", token)
    try:
        with urllib.request.urlopen(istek, timeout=zaman) as r:
            ham = r.read()
            return r.status, (json.loads(ham) if ham else {})
    except urllib.error.HTTPError as e:
        ham = e.read()
        try:
            return e.code, json.loads(ham)
        except Exception:
            return e.code, {"errors": [ham.decode("utf-8", "replace")[:200]]}
    except Exception as e:
        return 0, {"errors": [f"{type(e).__name__}: {e}"]}


def _kurtarma() -> dict:
    if not KURTARMA_DOSYASI.is_file():
        raise SystemExit(
            f"HATA: kurtarma dosyasi yok -> {KURTARMA_DOSYASI}\n"
            "  Vault init ciktisi orada olmali (unseal anahtarlari + root token)."
        )
    return json.loads(KURTARMA_DOSYASI.read_text(encoding="utf-8"))


def _kok_token() -> str:
    return _kurtarma()["root_token"]


#: Y86: tatbikatın kullanacağı KURTARMA token'ı — `main` `--token`dan koyar; verilmezse etkileşimli konsolda gizli istemle
#: alınır. Dosyaya / günlüğe yazılmaz.
_KURTARMA_TOKENI: str | None = None
#: A-84: kurtarma token'ı yenilenemez (renewable=False) — kalan ömrü bundan kısaysa tatbikat `--token-uret` ile YENİSİNİ
#: üretip saklamayı söyler (token yenileme adımı). Vault'un varsayılan kira süresi kısaltıldı (docker/vault/config/vault.hcl);
#: kurtarma token'ı kendi 10 yıllık TTL'iyle üretilir (`token_uret`).
_YENILEME_ESIGI_SN = 365 * 24 * 3600


def _kurtarma_tokeni() -> str:
    """⚠️ Y86 (sahip kararı · İG-9.86): tatbikat KURTARMA token'ıyla koşar — felakette elde olacak olan odur; kök token
    tatbikatta KULLANILMAZ. Eskiden `--tatbikat` `--token`ı yok sayıp kök token'la koşuyordu: kurtarma token'ı İPTAL edilmiş
    olsa bile "TATBIKAT BASARILI" diyordu (ölçüldü). Token yoksa / kök token ise / kurtarma politikasını taşımıyorsa /
    geçersizse tatbikat "BASARILI" DEMEZ (SystemExit). Token'ın kalan ömrü raporlanır; bir yıldan azsa yenileme söylenir."""
    tok = (_KURTARMA_TOKENI or "").strip()
    if not tok and sys.stdin is not None and sys.stdin.isatty():
        import getpass

        tok = getpass.getpass("  Kurtarma token'i (ekranda gorunmez): ").strip()
    if not tok:
        raise SystemExit(
            "  HATA: kurtarma token'i VERILMEDI -> kurtarma token'i SINANMADI, tatbikat YAPILMADI.\n"
            "  Felakette elinizde olacak olan kurtarma token'idir (kok token degil); onunla calistirin:\n"
            "    python scripts/vault_emanet.py --tatbikat --token <kurtarma-token>   (ya da etkilesimli konsolda)"
        )
    kod, bilgi = _istek("/v1/auth/token/lookup-self", token=tok)
    if kod == 0:
        raise SystemExit(
            f"  HATA: Vault'a ULASILAMIYOR ({ADRES}) -> tatbikat YAPILAMADI.\n"
            "  -> docker compose -f docker/docker-compose.vault.yml up -d   ve   python scripts/vault_emanet.py --ac"
        )
    if kod != 200:
        raise SystemExit(
            f"  HATA {kod}: kurtarma token'i GECERSIZ ({(bilgi or {}).get('errors')}) -> TATBIKAT BASARISIZ.\n"
            "  Token iptal edilmis / suresi dolmus olabilir: --token-uret ile yenisini uretip saklayin."
        )
    veri = (bilgi or {}).get("data") or {}
    politikalar = veri.get("policies") or []
    if "root" in politikalar or POLITIKA_ADI not in politikalar:
        raise SystemExit(
            f"  HATA: verilen token kurtarma token'i DEGIL (politikalar: {politikalar}) -> kurtarma token'i SINANMADI.\n"
            f"  --token-uret ile uretilen ('{POLITIKA_ADI}' politikali) token'i verin."
        )
    kalan = veri.get("ttl")
    if isinstance(kalan, int) and kalan > 0:
        print(f"  [0] kurtarma token'i gecerli; kalan omur ~{kalan // 86400} gun")
        if kalan < _YENILEME_ESIGI_SN:
            print(
                "      ⚠️ bir yildan AZ kaldi -> YENILEYIN: python scripts/vault_emanet.py --token-uret\n"
                "         (yeni token'i saklayin; sonra eskisini iptal edin)"
            )
    else:
        print("  [0] kurtarma token'i gecerli (suresiz)")
    return tok


def durum() -> int:
    kod, s = _istek("/v1/sys/health?uninitcode=200&sealedcode=200")
    if kod == 0:
        print(f"  Vault'a ULASILAMIYOR ({ADRES}) — konteyner kapali olabilir:")
        print("    docker compose -f docker/docker-compose.vault.yml up -d")
        return 1
    print(f"  adres       : {ADRES}")
    print(f"  surum       : {s.get('version')}")
    print(f"  kurulu      : {s.get('initialized')}")
    print(f"  MUHURLU     : {s.get('sealed')}  " + ("<- --ac ile acin" if s.get("sealed") else ""))
    if s.get("sealed"):
        return 1
    kod, m = _istek("/v1/sys/mounts", token=_kok_token())
    print(f"  KV mount    : {'VAR' if f'{MOUNT}/' in (m or {}) else 'YOK (--kur)'}")
    kod, d = _istek(f"/v1/{MOUNT}/data/{EMANET_YOLU}", token=_kok_token())
    if kod == 200:
        alanlar = sorted((d.get("data") or {}).get("data") or {})
        sur = ((d.get("data") or {}).get("metadata") or {}).get("version")
        print(f"  EMANET      : VAR (surum {sur}) alanlar={alanlar}")
    else:
        print("  EMANET      : YOK (--yaz)")
    return 0


def ac() -> int:
    """Yeniden başlatma sonrası mühürü aç. ⚠️ Vault her restart'ta MÜHÜRLÜ başlar."""
    k = _kurtarma()
    esik = None
    for anahtar in k["keys_base64"]:
        kod, s = _istek("/v1/sys/unseal", "PUT", {"key": anahtar})
        if kod != 200:
            print(f"  HATA: {s.get('errors')}")
            return 1
        esik = s
        if not s.get("sealed"):
            break
    print(f"  sealed={esik.get('sealed')}")
    return 0 if esik and not esik.get("sealed") else 1


def kur() -> int:
    """KV + denetim + kurtarma politikası. ⚠️ D2.E05 (İG-9.86): adım hataları SAYILIR; biri bile düşerse çıkış kodu 1.
    Eskiden her durumda 0 dönüyordu — Vault kapalıyken / kök token yetkisizken üç "HATA" basıp yine "başarılı" çıkıyordu
    (ölçüldü); otomasyon ve operatör kurulumu tamam sanıyordu."""
    t = _kok_token()
    hata = 0

    # 1) KV v2
    kod, m = _istek("/v1/sys/mounts", token=t)
    if f"{MOUNT}/" not in (m or {}):
        kod, s = _istek(f"/v1/sys/mounts/{MOUNT}", "POST", {"type": "kv", "options": {"version": "2"}}, t)
        hata += kod not in (200, 204)
        print(f"  KV v2 '{MOUNT}/' " + ("olusturuldu" if kod in (200, 204) else f"HATA {kod} {s.get('errors')}"))
    else:
        print(f"  KV v2 '{MOUNT}/' zaten var")

    # 2) Denetim kaydi — kim ne zaman emanete dokundu.
    # ⚠️ Vault, denetim hedefi YAZILAMAZSA istekleri REDDEDER (fail-closed). Hedef konteyner
    # icindeki kalici `vault-log` biriminde; birim silinirse Vault kullanilamaz hale gelir.
    kod, a = _istek("/v1/sys/audit", token=t)
    if "file/" not in (a or {}):
        kod, s = _istek(
            "/v1/sys/audit/file",
            "POST",
            {"type": "file", "options": {"file_path": "/vault/logs/denetim.log"}},
            t,
        )
        hata += kod not in (200, 204)
        print("  denetim kaydi " + ("acildi" if kod in (200, 204) else f"HATA {kod} {s.get('errors')}"))
    else:
        print("  denetim kaydi zaten acik")

    # 3) Kurtarma politikasi (YALNIZ OKUMA)
    kod, s = _istek(f"/v1/sys/policies/acl/{POLITIKA_ADI}", "PUT", {"policy": POLITIKA}, t)
    hata += kod not in (200, 204)
    print(f"  politika '{POLITIKA_ADI}' " + ("yazildi" if kod in (200, 204) else f"HATA {kod} {s.get('errors')}"))
    if hata:
        print(
            f"\nSONUC: KURULUM EKSIK — {hata} adim BASARISIZ (yukariya bakin; Vault kapali / muhurlu / kok token yetkisiz?)."
        )
        return 1
    return 0


def yaz() -> int:
    """Yerel anahtarları Vault'a YEDEKLE. Yereli DEĞİŞTİRMEZ/SİLMEZ."""
    t = _kok_token()
    cozulmus = _sirlari_oku()
    govde = {
        "data": {
            **cozulmus,
            "_veri_koku": str(_veri_koku()),
            "_not": (
                "PEMF Vet hasta verisi anahtarlari (YEDEK). Geri yukleme: bu degerleri hedef "
                "makinede <veri_koku>/pemf_secrets.json -> auto.<alan> alanlarina DUZ METIN "
                "yazin; backend ilk aciliste DPAPI ile yeniden sarar."
            ),
        }
    }
    kod, s = _istek(f"/v1/{MOUNT}/data/{EMANET_YOLU}", "POST", govde, t)
    if kod not in (200, 204):
        print(f"  HATA {kod}: {s.get('errors')}")
        return 1
    sur = ((s or {}).get("data") or {}).get("version")
    print(f"  emanet yazildi (surum {sur}):")
    for alan, _a in ALANLAR:
        if cozulmus.get(alan):
            print(f"    {alan:28s} parmak={_parmak(cozulmus[alan])}")
    print("\n  ⚠️ Yerel kopyaya DOKUNULMADI — uygulama eskisi gibi calisir.")
    return 0


def dogrula() -> int:
    """Vault'taki kopya yereldekiyle AYNI mı? (anahtar EKRANA yazılmaz)"""
    t = _kok_token()
    kod, d = _istek(f"/v1/{MOUNT}/data/{EMANET_YOLU}", token=t)
    if kod != 200:
        print(f"  HATA {kod}: emanet okunamadi ({(d or {}).get('errors')})")
        return 1
    uzak = (d.get("data") or {}).get("data") or {}
    yerel = _sirlari_oku()
    sorun = 0
    for alan, _a in ALANLAR:
        y, u = yerel.get(alan), uzak.get(alan)
        if y and not u:
            print(f"  ⚠️ {alan}: yerelde VAR, Vault'ta YOK")
            sorun += 1
        elif y and u and y != u:
            print(f"  ⚠️ {alan}: Vault kopyasi ESKI (parmak {_parmak(u)} != yerel {_parmak(y)})")
            sorun += 1
        elif y and u:
            print(f"  ✓ {alan}: guncel (parmak {_parmak(y)})")
    if sorun:
        print("\nSONUC: EMANET GECERSIZ — --yaz ile tazeleyin.")
        return 1
    print("\nSONUC: EMANET GUNCEL.")
    return 0


def tatbikat() -> int:
    """⚠️ KURTARMA TATBİKATI — emanetteki anahtar GERÇEKTEN hasta verisini açıyor mu?

    `--dogrula` yalnız iki değerin AYNI olduğunu söyler. Disk öldüğünde iş görecek olan şey
    ZİNCİRİN TAMAMI: Vault → anahtar → SQLCipher → okunabilir tablo. Aradaki her halka
    (binding sürümü, `PRAGMA key` tırnaklaması, dosya biçimi) sessizce bozulabilir ve
    `--dogrula` bunu GÖREMEZ. Bu yüzden ayrı bir adım.

    GÜVENLİK SÖZLEŞMESİ:
      · Anahtar hiçbir biçimde YAZDIRILMAZ (ne tam ne kısmi).
      · Gerçek DB'ye DOKUNULMAZ — geçici bir KOPYA açılır, sonunda silinir.
      · PII basılmaz; yalnız SATIR SAYISI.
      · ⚠️ KARŞIT KANIT zorunlu: YANLIŞ anahtarın reddedildiği de ölçülür. O olmadan
        "açıldı" sonucu hiçbir şey kanıtlamaz (binding anahtarı yok sayıyor olabilirdi).
      · ⚠️ Y86: zincirin İLK halkası KURTARMA token'ıdır — tatbikat onunla koşar; kök token KULLANILMAZ
        (`_kurtarma_tokeni`: yoksa / kök token ise / geçersizse "BASARILI" denmez).
    """
    import shutil
    import tempfile

    t = _kurtarma_tokeni()
    kod, d = _istek(f"/v1/{MOUNT}/data/{EMANET_YOLU}", token=t)
    if kod != 200:
        print(f"  HATA {kod}: emanet okunamadi ({(d or {}).get('errors')})")
        # ⚠️ Mesaj EYLEM soylemeli: en sik iki sebep konteynerin kapali ve Vault'un muhurlu
        # olmasidir; ikisi de tek satirlik komutla cozulur. Ham URLError'la birakmak,
        # operatoru "emanet bozuldu mu?" diye yanlis yone surukler.
        if kod == 0:
            print("  -> Vault konteyneri kapali olabilir:")
            print("     docker compose -f docker/docker-compose.vault.yml up -d")
        print("  -> Vault her yeniden baslatmada MUHURLU gelir:")
        print("     python scripts/vault_emanet.py --ac")
        return 1
    anahtar = ((d.get("data") or {}).get("data") or {}).get("auto.sqlcipher_key") or ""
    if not anahtar:
        print("  HATA: emanette `auto.sqlcipher_key` YOK -> --yaz ile yedekleyin")
        return 1
    print(f"  [1] Vault'tan anahtar alindi (uzunluk {len(anahtar)}; DEGER BASILMAZ)")

    try:
        import sqlcipher3 as sqlmod
    except Exception:
        try:
            from pysqlcipher3 import dbapi2 as sqlmod  # type: ignore
        except Exception as e:
            print(f"  HATA: SQLCipher binding yok ({e}) -> tatbikat YAPILAMADI")
            return 1
    from database.sqlcipher_util import open_encrypted_conn

    kok = _veri_koku()
    print(f"  [2] veri koku: {kok}")
    gecici = Path(tempfile.mkdtemp(prefix="pemf_tatbikat_"))
    try:
        sonuc = []
        for ad, tablo in (("patients.db", "patients"), ("pemf_treatment_history.db", "treatment_sessions")):
            kaynak = kok / ad
            if not kaynak.is_file():
                sonuc.append((ad, "DOSYA YOK", None))
                continue
            if kaynak.read_bytes()[:16].startswith(b"SQLite format 3"):
                sonuc.append((ad, "DUZ METIN (sifreli DEGIL)", None))
                continue
            kopya = gecici / ad
            shutil.copy2(kaynak, kopya)
            try:
                c = open_encrypted_conn(kopya, anahtar, sqlmod)
            except Exception as e:
                sonuc.append((ad, f"ACILAMADI: {type(e).__name__}", None))
                continue
            try:
                n_tablo = c.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table'").fetchone()[0]
                try:
                    n_satir = c.execute(f"SELECT COUNT(*) FROM {tablo}").fetchone()[0]
                except Exception as e:
                    n_satir = f"HATA {type(e).__name__}"
                sonuc.append((ad, f"ACILDI ({n_tablo} tablo)", f"{tablo}={n_satir}"))
            finally:
                c.close()

        print("  [3] emanet anahtariyla acma:")
        for ad, durum, satir in sonuc:
            print(f"      {ad:32s} {durum}" + (f"  {satir}" if satir else ""))

        print("  [4] KARSIT KANIT — yanlis anahtar reddedilmeli:")
        red = False
        kaynak = kok / "patients.db"
        if kaynak.is_file():
            kopya2 = gecici / "_yanlis_anahtar_testi.db"
            shutil.copy2(kaynak, kopya2)
            try:
                c2 = open_encrypted_conn(kopya2, "bu-KESINLIKLE-yanlis-bir-anahtar-0000", sqlmod)
                c2.close()
                print("      ⛔ YANLIS ANAHTARLA ACILDI -> sifreleme anlamsiz, tatbikat GECERSIZ")
            except Exception as e:
                red = True
                print(f"      ✓ reddedildi ({type(e).__name__})")
        else:
            print("      OLCULEMEDI (patients.db yok)")

        olculen = [s for s in sonuc if s[1] not in ("DOSYA YOK",)]
        acilan = [s for s in olculen if s[1].startswith("ACILDI")]
        tamam = bool(olculen) and len(acilan) == len(olculen) and red
        print(
            "\nSONUC: "
            + ("TATBIKAT BASARILI — emanet gercekten kurtariyor." if tamam else "TATBIKAT BASARISIZ — yukariya bakin.")
        )
        return 0 if tamam else 1
    finally:
        shutil.rmtree(gecici, ignore_errors=True)


def token_uret() -> int:
    """Sahibin saklayacağı 10 yıllık KURTARMA token'ı (yalnız okuma)."""
    t = _kok_token()
    kod, s = _istek(
        "/v1/auth/token/create",
        "POST",
        {
            "policies": [POLITIKA_ADI],
            "ttl": "87600h",  # 10 yıl — disk kaybı yıllar sonra da olabilir
            "renewable": False,
            "display_name": "pemf-kurtarma",
            "no_parent": True,  # kök token iptal edilse bile bu token YAŞAR
        },
        t,
    )
    if kod not in (200, 204):
        print(f"  HATA {kod}: {s.get('errors')}")
        return 1
    auth = s.get("auth") or {}
    print("  KURTARMA TOKEN'I (bunu saklayin):\n")
    print("    " + auth.get("client_token", ""))
    print(f"\n  politika : {auth.get('policies')}")
    print(f"  omur     : {auth.get('lease_duration')} sn (~10 yil)")
    print(
        "\n  ⚠️ Bu token YALNIZ emaneti OKUR; degistiremez/silemez ve Vault'un baska\n"
        "     hicbir yerine erisemez. Parola yoneticinize koyun.\n"
        "  ⚠️ Tek basina YETMEZ: Vault ayaga kalkmali ve MUHURU ACILMALI. Unseal\n"
        f"     anahtarlari {KURTARMA_DOSYASI} dosyasinda — onu da baska bir yerde saklayin."
    )
    return 0


def geri_al(token: str | None) -> int:
    """KURTARMA: Vault'taki anahtarı ekrana yaz (disk kaybı sonrası kullanılır)."""
    t = token or _kok_token()
    kod, d = _istek(f"/v1/{MOUNT}/data/{EMANET_YOLU}", token=t)
    if kod != 200:
        print(f"  HATA {kod}: {(d or {}).get('errors')}")
        return 1
    veri = (d.get("data") or {}).get("data") or {}
    print("  ⚠️ ASAGIDAKI DEGERLER HASTA VERISINI ACAR. Ekrani/gecmisi temizleyin.\n")
    for k in sorted(veri):
        print(f"    {k} = {veri[k]}")
    print(
        "\n  Geri yukleme: hedef makinede <_veri_koku>/pemf_secrets.json dosyasindaki\n"
        "  auto.sqlcipher_key ve auto.patient_fernet_key alanlarina bu degerleri DUZ METIN\n"
        "  yazin (DPAPI: oneki OLMADAN); backend ilk aciliste kendi sarar."
    )
    return 0


def main() -> int:
    global _KURTARMA_TOKENI
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--durum", action="store_true")
    g.add_argument("--ac", action="store_true", help="yeniden baslatma sonrasi muhuru ac")
    g.add_argument("--kur", action="store_true")
    g.add_argument("--yaz", action="store_true")
    g.add_argument("--dogrula", action="store_true", help="Vault kopyasi yerelle AYNI mi (parmak izi)")
    g.add_argument(
        "--tatbikat",
        action="store_true",
        help="KURTARMA TATBIKATI: emanet anahtari gercek DB'yi ACIYOR mu (deger basmaz)",
    )
    g.add_argument("--token-uret", action="store_true")
    g.add_argument("--geri-al", action="store_true", help="KURTARMA: anahtari ekrana yaz")
    ap.add_argument(
        "--token",
        help="kurtarma token'i: --tatbikat icin (verilmezse gizli istem; kok token KULLANILMAZ) ve --geri-al icin "
        "(yoksa kok token kullanilir)",
    )
    a = ap.parse_args()

    if a.durum:
        return durum()
    if a.ac:
        return ac()
    if a.kur:
        return kur()
    if a.yaz:
        return yaz()
    if a.dogrula:
        return dogrula()
    if a.tatbikat:
        _KURTARMA_TOKENI = a.token  # Y86: tatbikat KURTARMA token'ıyla (bkz. _kurtarma_tokeni)
        return tatbikat()
    if a.token_uret:
        return token_uret()
    return geri_al(a.token)


if __name__ == "__main__":
    sys.exit(main())
