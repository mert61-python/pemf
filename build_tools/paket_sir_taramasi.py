# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""PAKETE SIR GİRMESİN (18K K4 · D3.26 + D3.43 · Y38) — yayın paketlerinin TEK sır taraması.

Yayın dosyaları (base-app / base-deps / profil zip'leri, Inno kurulum ağacı) herkese açık GitHub Releases'e çıkar — yayımlanan bir sır
GERİ ALINAMAZ. Spec'in ad tabanlı süzgeci (`config/credentials` atlanır, `config.json` gömülmez) bir gün sırlı dosyayı geçirirse eskiden
hiçbir kapı tutmuyordu: Inno Adım 6.5 yalnız UYARIYORDU (ve uyarı her derlemede iki `mosquitto.conf` yüzünden zaten yanıyordu), katmanlı
kanal (make_base_zip / make_manifest) hiç bakmıyordu.

Kural (bulgu → çıkış ≠ 0; DEĞER YAZDIRILMAZ, yalnız konum ve tür):
  * yasak dosya ADI (büyük / küçük harf duyarsız): `pemf_secrets*.json`, `credentials*.json`, `.env` / `.env.*`, `secrets*.h` (ESP
    `Secrets.h`, `secrets_coil_*.h`), `cloud_mqtt_provision*` (Y38: bulut E-stop aynasının kimliği pakete GÖMÜLMEZ), `hivemq_users*`,
    `mosquitto_passwords*`, `bridge_hivemq*`; yol parçası `credentials` (spec'in atladığı `config/credentials/` dizini); yol soneki
    `_internal/config/config.json` (gerçek yapılandırma) ve `_internal/data/config.json` (ESP provizyonu).
  * metin dosyası İÇERİĞİNDE belirteç deseni: Hugging Face (`hf_…`), GitHub (`ghp_` / `gho_` / `ghu_` / `ghs_` / `ghr_` / `github_pat_`).
İzin listesi (Y38, gerekçeli — eski Inno uyarı listesinde olup SIR OLMAYAN, bilerek sevk edilen dosyalar) `IZINLI`: ad kuralına girmez,
içerik taraması yine yapılır.
Sınır: PyInstaller'ın EXE içindeki sıkıştırılmış PYZ arşivi açılmaz — kaynak koddaki sabit belirteci commit anında gitleaks yakalar.

Kullanım:  python build_tools/paket_sir_taramasi.py <dizin | .zip> [...]
Çağıranlar: build_tools/make_base_zip.py (doğrulama, yerleştirmeden ÖNCE) · scripts/make_manifest.py (mühürlemeden ÖNCE) ·
build_tools/build_installer.ps1 Adım 6.5.
"""

from __future__ import annotations

import fnmatch
import os
import re
import sys
import zipfile

YASAK_ADLAR = (
    ("pemf_secrets*.json", "SecretsManager sır deposu"),
    ("credentials*.json", "broker / bulut kimlikleri"),
    (".env", "dotenv sırları"),
    (".env.*", "dotenv sırları"),
    ("secrets*.h", "ESP Secrets.h (Wi-Fi / MQTT parolası)"),
    ("cloud_mqtt_provision*", "Y38: bulut E-stop aynasının kimliği pakete GÖMÜLMEZ"),
    ("hivemq_users*", "HiveMQ kullanıcı / parola listesi"),
    ("mosquitto_passwords*", "broker parola dosyası"),
    ("bridge_hivemq*", "HiveMQ köprüsü — uzak broker kimliği"),
)
YASAK_DIZINLER = (("credentials", "config/credentials — GERÇEK MQTT / HiveMQ / ESP parolaları (spec atlar)"),)
#: Adı yaygın ama BU yolda sır taşıyan dosyalar (sonek eşleşmesi; spec yorumları): gerçek `config.json` Gmail uygulama parolası,
#: `data/config.json` ESP provizyon sırları (Wi-Fi / MQTT). Üçüncü taraf paketlerin kendi `config.json`'ları ad kuralına SOKULMAZ.
YASAK_YOLLAR = (
    (
        "_internal/config/config.json",
        "gerçek config.json (Gmail uygulama parolası) — yalnız config.json.template gömülür",
    ),
    ("_internal/data/config.json", "ESP provizyon sırları (Wi-Fi / MQTT parolası)"),
)

#: Y38 izin listesi — eski Inno uyarı listesinde olup SIR OLMAYAN, bilerek sevk edilen dosyalar (ad kuralına girmez; içerik yine taranır).
IZINLI = {
    "mosquitto.conf": "yerel broker yapılandırması (bin/mosquitto, config/mosquitto): kimlik / parola YOK — parola dosyası çalışma anında"
    " conf.d'ye yazılır; eski Inno uyarı listesinde her derlemede yanıp gerçek isabeti gürültüde boğuyordu",
    "mosquitto_acl.conf": "yalnız konu (topic) erişim kuralları — kullanıcı adı / parola içermez",
}

#: Belirteç biçimleri: Hugging Face `hf_` + 34 · GitHub klasik `ghp_` / `gho_` / `ghu_` / `ghs_` / `ghr_` + 36 · ince `github_pat_` + 82.
#: Eşikler gerçek uzunluğun ALTINDA (kırpılmış kopya da yakalansın); HF eşiği eski Inno kapısınınkiyle AYNI (20). Ölçülen tek yanlış
#: pozitif (18K, son derleme çıktısı 7226 dosya: pip `RECORD`'unda `sha256=hf_…` ile başlayan base64url hash) `metin_mi`'de çözülür.
BELIRTECLER = (
    ("Hugging Face belirteci", re.compile(rb"(?<![A-Za-z0-9_])hf_[A-Za-z0-9]{20,}")),
    ("GitHub belirteci", re.compile(rb"(?<![A-Za-z0-9_])gh[pousr]_[A-Za-z0-9]{30,}")),
    ("GitHub ince belirteci", re.compile(rb"(?<![A-Za-z0-9_])github_pat_[A-Za-z0-9_]{40,}")),
)
METIN_UZANTILARI = frozenset(
    ".py .pyi .json .txt .ini .conf .cfg .template .md .html .htm .js .mjs .cjs .css .qss .env .yaml .yml .toml .ps1 .psm1"
    " .bat .cmd .xml .h .csv .map .properties".split()
)
ICERIK_SINIRI = 5 * 1024 * 1024  # bayt — daha büyük metin dosyası taranmaz (ikili veri / model değil)


def ad_bulgusu(yol: str) -> str | None:
    """Yolun (`/` ya da `\\` ayraçlı) yasak ad / dizin nedeni; temizse None."""
    parcalar = [p for p in re.split(r"[\\/]+", yol) if p]
    if not parcalar:
        return None
    ad = parcalar[-1].lower()
    if ad not in IZINLI:
        for desen, neden in YASAK_ADLAR:
            if fnmatch.fnmatchcase(ad, desen):
                return f"yasak dosya adı '{parcalar[-1]}' ({neden})"
    for dizin, neden in YASAK_DIZINLER:
        if any(p.lower() == dizin for p in parcalar[:-1]):
            return f"yasak dizin '{dizin}/' ({neden})"
    duz = "/".join(parcalar).lower()
    for sonek, neden in YASAK_YOLLAR:
        if duz == sonek or duz.endswith("/" + sonek):
            return f"yasak yol '{sonek}' ({neden})"
    return None


def metin_mi(yol: str) -> bool:
    """İçeriği taranacak metin dosyası mı. `*.dist-info/RECORD` HARİÇ: kurucunun ürettiği base64url hash listesi (sır taşımaz;
    hash'ler belirteç desenine benzeyebilir — ölçüldü). Ad / yol kuralı bu dosyaya da uygulanır."""
    parcalar = [p.lower() for p in re.split(r"[\\/]+", yol) if p]
    ad = parcalar[-1] if parcalar else ""
    if ad == "record" and len(parcalar) > 1 and parcalar[-2].endswith(".dist-info"):
        return False
    uzanti = os.path.splitext(ad)[1]
    return uzanti in METIN_UZANTILARI or uzanti == "" or ad.startswith(".env")


def icerik_bulgulari(veri: bytes) -> list[str]:
    return [ad for ad, desen in BELIRTECLER if desen.search(veri)]


def tara_zip(yol: str) -> tuple[list[str], int]:
    bulgular, sayi = [], 0
    etiket = os.path.basename(yol)
    with zipfile.ZipFile(yol) as z:
        for bilgi in z.infolist():
            if bilgi.is_dir():
                continue
            sayi += 1
            konum = f"{etiket}:{bilgi.filename}"
            neden = ad_bulgusu(bilgi.filename)
            if neden:
                bulgular.append(f"{konum}: {neden}")
            if metin_mi(bilgi.filename) and bilgi.file_size <= ICERIK_SINIRI:
                for tur in icerik_bulgulari(z.read(bilgi)):
                    bulgular.append(f"{konum}: {tur} deseni (değer gizlendi)")
    return bulgular, sayi


def tara_dizin(kok: str) -> tuple[list[str], int]:
    bulgular, sayi = [], 0
    for ust, _dizinler, dosyalar in os.walk(kok):
        for ad in dosyalar:
            tam = os.path.join(ust, ad)
            goreli = os.path.relpath(tam, kok)
            sayi += 1
            neden = ad_bulgusu(goreli)
            if neden:
                bulgular.append(f"{goreli}: {neden}")
            if metin_mi(goreli):
                try:
                    if os.path.getsize(tam) <= ICERIK_SINIRI:
                        with open(tam, "rb") as f:
                            for tur in icerik_bulgulari(f.read()):
                                bulgular.append(f"{goreli}: {tur} deseni (değer gizlendi)")
                except OSError as e:  # okunamayan dosya TEMİZ sayılmaz
                    bulgular.append(f"{goreli}: okunamadı ({e.__class__.__name__}) — taranamadı")
    return bulgular, sayi


def tara_dosya(yol: str) -> tuple[list[str], int]:
    """Zip OLMAYAN tek dosya (ör. yayın dizinindeki ikili varlık): adı ve — sınır içindeyse — ham baytları taranır."""
    bulgular, etiket = [], os.path.basename(yol)
    neden = ad_bulgusu(etiket)
    if neden:
        bulgular.append(f"{etiket}: {neden}")
    try:
        if os.path.getsize(yol) <= ICERIK_SINIRI:
            with open(yol, "rb") as f:
                bulgular += [f"{etiket}: {tur} deseni (değer gizlendi)" for tur in icerik_bulgulari(f.read())]
    except OSError as e:
        bulgular.append(f"{etiket}: okunamadı ({e.__class__.__name__}) — taranamadı")
    return bulgular, 1


def tara(yollar) -> tuple[list[str], int]:
    """Dizin, .zip ya da tek dosya yollarını tarar → (bulgular, dosya sayısı). Var olmayan yol BULGUDUR (sessiz geçiş yok)."""
    bulgular, toplam = [], 0
    for yol in yollar:
        yol = os.fspath(yol)
        if os.path.isdir(yol):
            b, n = tara_dizin(yol)
        elif os.path.isfile(yol) and zipfile.is_zipfile(yol):
            b, n = tara_zip(yol)
        elif os.path.isfile(yol):
            b, n = tara_dosya(yol)
        else:
            b, n = [f"{yol}: taranacak dizin / zip / dosya YOK"], 0
        bulgular += b
        toplam += n
    return bulgular, toplam


def main(argv=None) -> int:
    for akis in (sys.stdout, sys.stderr):
        try:
            akis.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    yollar = list(sys.argv[1:] if argv is None else argv)
    if not yollar:
        print("kullanım: paket_sir_taramasi.py <dizin | .zip> [...]", file=sys.stderr)
        return 2
    bulgular, sayi = tara(yollar)
    for b in bulgular:
        print(f"[SIR] {b}", file=sys.stderr)
    if bulgular:
        print(f"SIR TARAMASI: FAIL — {len(bulgular)} bulgu ({sayi} dosya). Paket YAYINLANAMAZ.", file=sys.stderr)
        return 1
    print(f"SIR TARAMASI: TEMIZ ({sayi} dosya)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
