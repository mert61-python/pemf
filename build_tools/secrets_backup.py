# Author: mertaygn, cglrgrkn
"""MAKİNE-ÖZEL SIRLARIN TAŞINABİLİR ŞİFRELİ YEDEĞİ — "her makinede build" içindir.

PEMF'in git'e GİRMEYEN (public repo + gitleaks) sırları bu makinede yaşıyor; tek-nokta-arızası.
Bu araç hepsini TEK parola-korumalı `.pemfsec` arşivine toplar. Yeni bir makinede: repoyu klonla,
`restore` ile arşivi aç → dosyalar yerine oturur → `scripts/build_backend_exe.ps1` çalışır.

⚠️ GÜVENLİK:
  * Arşivi git'e KOYMA, e-postayla YOLLAMA. Şifre-yöneticisi + çevrimdışı USB gibi TAŞI.
  * Parolayı .pemfsec ile AYNI kanaldan gönderme.
  * Bu betik hiçbir sır DEĞERİNİ ekrana yazmaz (yalnız dosya adı + bayt uzunluğu).

Şifreleme: scrypt(parola, tuz, N=2**15) → Fernet anahtarı → her dosya ayrı Fernet token.
Bağımlılık: `cryptography` (repoda zaten var).

Kullanım:
  python build_tools/secrets_backup.py backup  [--out yol.pemfsec]   # sırları topla+şifrele
  python build_tools/secrets_backup.py restore --in yol.pemfsec       # yeni makinede geri yükle
  python build_tools/secrets_backup.py list    --in yol.pemfsec       # içindekileri göster (değer YOK)
Parola: PEMF_SECBAK_PASSPHRASE ortam değişkeninden (yoksa gizli getpass ile sorulur).
"""

from __future__ import annotations

import argparse
import base64
import getpass
import json
import os
import sys
from pathlib import Path

GUII = Path(__file__).resolve().parent.parent
HOME = Path(os.path.expanduser("~"))

# (mantıksal-ad, mutlak-yol, geri-yükleme-hedefi, skip_worktree_gerekir_mi)
# Yol repo-göreli ya da ev-göreli olabilir; restore ederken dizin yoksa oluşturulur.
_KALEMLER: list[tuple[str, Path, bool]] = [
    ("esp8266/Secrets.h", GUII / "firmware/esp8266_pemf_coil/Secrets.h", True),
    ("esps3/Secrets.h", GUII / "firmware/esps3_pemf_coil/Secrets.h", True),
    ("esp8266/data/config.json", GUII / "firmware/esp8266_pemf_coil/data/config.json", True),
    ("esps3/data/config.json", GUII / "firmware/esps3_pemf_coil/data/config.json", True),
    ("data/cloud_mqtt_provision.json", GUII / "data/cloud_mqtt_provision.json", False),
    ("pf/android/keystore.properties", GUII / "pf/android/keystore.properties", False),
    # Repo DIŞI: Android release imza anahtarı (keystore.properties bunun YOLUNU işaret eder).
    ("release-keystore/pemf-release.jks", HOME / ".pemf-keys/pemf-release.jks", False),
]

_MAGIC = "PEMFSEC1"
_SW_DOSYALAR = [  # restore sonrası tekrar skip-worktree yapılacaklar (git add -A koruması)
    "firmware/esp8266_pemf_coil/Secrets.h",
    "firmware/esps3_pemf_coil/Secrets.h",
    "firmware/esp8266_pemf_coil/data/config.json",
    "firmware/esps3_pemf_coil/data/config.json",
]


def _parola(dogrula: bool) -> bytes:
    p = os.environ.get("PEMF_SECBAK_PASSPHRASE")
    if p:
        return p.encode("utf-8")
    p1 = getpass.getpass("Yedek parolasi: ")
    if dogrula:
        p2 = getpass.getpass("Parola (tekrar): ")
        if p1 != p2:
            sys.exit("[HATA] parolalar uyusmuyor.")
    if len(p1) < 8:
        sys.exit("[HATA] parola en az 8 karakter olmali.")
    return p1.encode("utf-8")


def _anahtar(parola: bytes, tuz: bytes):
    from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

    ham = Scrypt(salt=tuz, length=32, n=2**15, r=8, p=1).derive(parola)
    return base64.urlsafe_b64encode(ham)


def cmd_backup(args) -> int:
    from cryptography.fernet import Fernet

    parola = _parola(dogrula=True)
    tuz = os.urandom(16)
    f = Fernet(_anahtar(parola, tuz))

    kalemler = []
    for ad, yol, _sw in _KALEMLER:
        if not yol.exists():
            print(f"  [ATLA] {ad}: dosya yok ({yol})")
            continue
        veri = yol.read_bytes()
        token = f.encrypt(veri).decode("ascii")
        kalemler.append({"ad": ad, "token": token, "boyut": len(veri)})
        print(f"  [+] {ad} (<{len(veri)} B>)")
    if not kalemler:
        sys.exit("[HATA] yedeklenecek dosya bulunamadi.")

    arsiv = {
        "_magic": _MAGIC,
        "kdf": {"algo": "scrypt", "n": 2**15, "r": 8, "p": 1, "tuz": base64.b64encode(tuz).decode()},
        "kalemler": kalemler,
    }
    out = Path(args.out) if args.out else (HOME / "pemf-sirlar.pemfsec")
    out.write_text(json.dumps(arsiv, indent=2), encoding="utf-8")
    try:
        os.chmod(out, 0o600)
    except Exception:
        pass
    print(f"\n[OK] {len(kalemler)} sir sifrelendi -> {out}")
    print("⚠️ Bu dosyayi git'e KOYMA; parolayla AYNI kanaldan gonderme. Sifre-yoneticisi + cevrimdisi USB.")
    return 0


def _yukle_arsiv(yol: Path) -> dict:
    d = json.loads(Path(yol).read_text(encoding="utf-8"))
    if d.get("_magic") != _MAGIC:
        sys.exit("[HATA] gecersiz .pemfsec dosyasi (magic uyusmuyor).")
    return d


def cmd_restore(args) -> int:
    from cryptography.fernet import Fernet, InvalidToken

    d = _yukle_arsiv(Path(args.inp))
    tuz = base64.b64decode(d["kdf"]["tuz"])
    parola = _parola(dogrula=False)
    f = Fernet(_anahtar(parola, tuz))

    ad2yol = {ad: (yol, sw) for ad, yol, sw in _KALEMLER}
    yazilan = 0
    for k in d["kalemler"]:
        ad = k["ad"]
        if ad not in ad2yol:
            print(f"  [ATLA] tanimsiz kalem: {ad}")
            continue
        yol, _sw = ad2yol[ad]
        try:
            veri = f.decrypt(k["token"].encode("ascii"))
        except InvalidToken:
            sys.exit("[HATA] parola yanlis (cozulemedi).")
        if yol.exists() and not args.force:
            print(f"  [VAR] {ad}: mevcut, atlandi (uzerine yazmak icin --force)")
            continue
        yol.parent.mkdir(parents=True, exist_ok=True)
        yol.write_bytes(veri)
        try:
            os.chmod(yol, 0o600)
        except Exception:
            pass
        print(f"  [OK] {ad} -> {yol} (<{len(veri)} B>)")
        yazilan += 1

    print(f"\n[OK] {yazilan} sir geri yuklendi.")
    print("SIRADAKI ADIMLAR (yeni makinede):")
    print("  1) Tracked sir dosyalarini git-korumasina al (add -A onlari stage'lemesin):")
    print("     git update-index --skip-worktree \\")
    for p in _SW_DOSYALAR:
        print(f"       {p} \\")
    print("  2) keystore.properties'teki storeFile yolu bu makinede DOGRU mu kontrol et")
    print("     (release-keystore geri yuklendiyse ~/.pemf-keys/ altina koy ya da yolu guncelle).")
    print("  3) scripts/build_backend_exe.ps1 -SkipWeb  (paket bulut-provizyonu icerecek)")
    return 0


def cmd_list(args) -> int:
    d = _yukle_arsiv(Path(args.inp))
    print(f"Arsiv: {args.inp}  (kdf: scrypt N={d['kdf']['n']})")
    for k in d["kalemler"]:
        print(f"  - {k['ad']}  (<{k['boyut']} B sifreli>)")
    print(f"Toplam {len(d['kalemler'])} sir. (Icerik parolasiz GORULEMEZ.)")
    return 0


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    ap = argparse.ArgumentParser(description="PEMF makine-ozel sir yedegi (sifreli, tasinabilir)")
    sub = ap.add_subparsers(dest="komut", required=True)
    b = sub.add_parser("backup", help="sirlari topla + sifrele")
    b.add_argument("--out", default=None, help="cikti .pemfsec (varsayilan ~/pemf-sirlar.pemfsec)")
    b.set_defaults(fn=cmd_backup)
    r = sub.add_parser("restore", help="yeni makinede geri yukle")
    r.add_argument("--in", dest="inp", required=True, help=".pemfsec dosyasi")
    r.add_argument("--force", action="store_true", help="mevcut dosyalarin uzerine yaz")
    r.set_defaults(fn=cmd_restore)
    ls = sub.add_parser("list", help="icindekileri goster (deger YOK)")
    ls.add_argument("--in", dest="inp", required=True)
    ls.set_defaults(fn=cmd_list)
    args = ap.parse_args()
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
