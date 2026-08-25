# Author: mertaygn, cglrgrkn
"""MAKİNE-ÖZEL SIRLARIN TAŞINABİLİR YEDEĞİ — "her makinede build" içindir.

PEMF'in git'e GİRMEYEN (public repo + gitleaks) sırları bu makinede yaşıyor; tek-nokta-arızası.
Bu araç hepsini TEK `.pemfsec` arşivine toplar. Yeni bir makinede: repoyu klonla, `restore` ile
arşivi aç → dosyalar yerine oturur → `scripts/build_backend_exe.ps1` çalışır.

⚠️ GÜVENLİK — PAROLA YOK (sahip kararı 2026-08-19): arşiv ŞİFRELİ DEĞİL, yalnız base64 ile
TOPLANMIŞtır. Dosyayı eline geçiren herkes içindeki sırları (ESP Secrets.h, release keystore,
bulut MQTT parolası) OKUYABİLİR. Maruziyet sınıfı yeni değil (aynı sırlar ESP flash'larında +
public `esp` dalında). Yine de:
  * `.pemfsec`'i git'e KOYMA (gitignore korur), e-postayla/genel buluta YOLLAMA.
  * USB + şifre-yöneticisi eki gibi ERİŞİMİ SINIRLI ortamda taşı.
Bu betik yalnızca dosya adı + bayt uzunluğunu yazdırır (değerleri değil).

Bağımlılık YOK (yalnız stdlib).

Kullanım:
  python build_tools/secrets_backup.py backup  [--out yol.pemfsec]   # sırları topla
  python build_tools/secrets_backup.py restore --in yol.pemfsec       # yeni makinede geri yükle
  python build_tools/secrets_backup.py list    --in yol.pemfsec       # içindekileri göster (değer YOK)
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import subprocess
import sys
from pathlib import Path

GUII = Path(__file__).resolve().parent.parent
HOME = Path(os.path.expanduser("~"))

# (mantıksal-ad, mutlak-yol, skip_worktree_gerekir_mi)
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

_MAGIC = "PEMFSEC2"  # v2 = parolasız (düz base64). v1 = scrypt+Fernet (artık üretilmiyor).
_SW_DOSYALAR = [  # restore sonrası tekrar skip-worktree yapılacaklar (git add -A koruması)
    "firmware/esp8266_pemf_coil/Secrets.h",
    "firmware/esps3_pemf_coil/Secrets.h",
    "firmware/esp8266_pemf_coil/data/config.json",
    "firmware/esps3_pemf_coil/data/config.json",
]


def cmd_backup(args) -> int:
    kalemler = []
    for ad, yol, _sw in _KALEMLER:
        if not yol.exists():
            print(f"  [ATLA] {ad}: dosya yok ({yol})")
            continue
        veri = yol.read_bytes()
        kalemler.append({"ad": ad, "b64": base64.b64encode(veri).decode("ascii"), "boyut": len(veri)})
        print(f"  [+] {ad} (<{len(veri)} B>)")
    if not kalemler:
        sys.exit("[HATA] yedeklenecek dosya bulunamadi.")

    arsiv = {"_magic": _MAGIC, "sifreli": False, "kalemler": kalemler}
    out = Path(args.out) if args.out else (HOME / "pemf-sirlar.pemfsec")
    out.write_text(json.dumps(arsiv, indent=2), encoding="utf-8")
    try:
        os.chmod(out, 0o600)
    except Exception:
        pass
    print(f"\n[OK] {len(kalemler)} sir toplandi -> {out}")
    print("⚠️ ŞİFRESİZ arsiv (parola YOK). Git'e KOYMA; genel bulut/e-postayla YOLLAMA;")
    print("   USB + sifre-yoneticisi gibi ERISIMI SINIRLI ortamda tasi.")
    return 0


def _yukle_arsiv(yol: Path) -> dict:
    d = json.loads(Path(yol).read_text(encoding="utf-8"))
    m = d.get("_magic")
    if m == "PEMFSEC1":
        sys.exit(
            "[HATA] bu arsiv ESKI parola-korumali surumle (PEMFSEC1) uretilmis. Parolasiz surum "
            "onu acamaz — eski surumle restore edip yeniden 'backup' alin."
        )
    if m != _MAGIC:
        sys.exit("[HATA] gecersiz .pemfsec dosyasi (magic uyusmuyor).")
    return d


def _git_sir_korumasi() -> None:
    """Restore SONRASI: izlenen sır dosyalarını git'in gözünden düşür (skip-worktree).

    2. tur denetimi [2.2] (2026-08-20): eski restore bu adımı KULLANICIYA bırakıyordu ve bastığı
    komut PowerShell'de ÇALIŞMAYAN bash-tarzı satır-devamlarıydı (` \\`). Adım atlanınca
    `git add -A` GERÇEK sırları PUBLIC repoya stage'liyordu — üstelik gitleaks'in varsayılan
    kuralları bu düşük-entropili WiFi/MQTT sınıfını yakalamıyor (ölçüldü; `.gitleaks.toml`a
    özel kurallar da eklendi, ikinci kemer). Artık araç korumayı KENDİSİ uygular:
      · dosya bu kökte İZLENMİYORSA (git yok / untracked) staging riski yoktur → sessiz geç;
      · git ÇALIŞTIRILAMAZSA ya da update-index DÜŞERSE → YÜKSEK SESLE uyar + tek satırlık,
        kabuk-bağımsız elle-komutu bas (restore'u DÜŞÜRMEZ — dosyalar yazıldı, iş bitmeli)."""
    # Kök gerçek bir git reposu DEĞİLSE staging riski yoktur (`git add -A` repo dışında no-op) →
    # sessiz geç, yanlış alarm üretme.
    if not (GUII / ".git").exists():
        return
    izlenenler = []
    git_dustu = False
    try:
        for rel in _SW_DOSYALAR:
            if not (GUII / rel).exists():
                continue
            r = subprocess.run(
                ["git", "-C", str(GUII), "ls-files", "--error-unmatch", "--", rel],
                capture_output=True,
                text=True,
            )
            if r.returncode == 0:
                izlenenler.append(rel)
            elif r.returncode != 1:
                # ⚠️ [2.2] DELİĞİ (denetim 2026-08-24, D3): `ls-files --error-unmatch` returncode 1 =
                # git ÇALIŞTI, dosya GERÇEKTEN izlenmiyor → staging riski yok, atla. Ama 128 (ve
                # diğer) = git DÜŞTÜ (dubious ownership / bozuk GIT_DIR — taze klonda yaygın), "izlenmiyor"
                # DEĞİL. Eski kod ikisini ayırt etmiyor, 128'i de sessiz geçiyordu; sonra safe.directory
                # düzeltilip `git add -A` yapılınca gerçek sırlar stage'leniyordu. Bunu yüksek sesle bildir.
                git_dustu = True
        if izlenenler:
            r = subprocess.run(
                ["git", "-C", str(GUII), "update-index", "--skip-worktree", "--", *izlenenler],
                capture_output=True,
                text=True,
            )
            if r.returncode == 0:
                for rel in izlenenler:
                    print(f"  [GIT] skip-worktree uygulandı: {rel}")
                return
            git_dustu = True  # update-index düştü (izlenen dosyalar KORUNAMADI)
        elif not git_dustu:
            # Repo var, hiçbir sır dosyası izlenmiyor VE her ls-files çalıştı → gerçek untracked, risk yok.
            return
    except FileNotFoundError:
        # git PATH'te yok — kökün gerçek repo olduğu makinede EN riskli durum: aşağıda bağır.
        git_dustu = True
    # Buraya gelindi = git düştü (128/PATH-yok) VEYA update-index düştü → izlenenler EKSİK olabilir.
    izlenenler = izlenenler or list(_SW_DOSYALAR)
    print("  [!!] GIT KORUMASI UYGULANAMADI — `git add -A` GERÇEK SIRLARI stage'leyebilir (repo PUBLIC)!")
    print("       Aşağıdaki komutu elle çalıştırın (TEK satır, PowerShell/bash fark etmez):")
    print("       git update-index --skip-worktree " + " ".join(izlenenler))


def cmd_restore(args) -> int:
    d = _yukle_arsiv(Path(args.inp))
    ad2yol = {ad: yol for ad, yol, _sw in _KALEMLER}
    yazilan = 0
    for k in d["kalemler"]:
        ad = k["ad"]
        if ad not in ad2yol:
            print(f"  [ATLA] tanimsiz kalem: {ad}")
            continue
        yol = ad2yol[ad]
        if yol.exists() and not args.force:
            print(f"  [VAR] {ad}: mevcut, atlandi (uzerine yazmak icin --force)")
            continue
        veri = base64.b64decode(k["b64"])
        yol.parent.mkdir(parents=True, exist_ok=True)
        yol.write_bytes(veri)
        try:
            os.chmod(yol, 0o600)
        except Exception:
            pass
        print(f"  [OK] {ad} -> {yol} (<{len(veri)} B>)")
        yazilan += 1

    print(f"\n[OK] {yazilan} sir geri yuklendi.")
    # 2. tur [2.2]: git korumasi artik OTOMATIK (eskiden kullaniciya birakilan adim + PowerShell'de
    # calismayan bash-tarzi komut, atlanınca `git add -A`nin gercek sirlari stage'lemesi demekti).
    _git_sir_korumasi()
    print("SIRADAKI ADIMLAR (yeni makinede):")
    print("  1) keystore.properties'teki storeFile yolu bu makinede DOGRU mu kontrol et")
    print("     (release-keystore geri yuklendiyse ~/.pemf-keys/ altina koy ya da yolu guncelle).")
    print("  2) scripts/build_backend_exe.ps1 -SkipWeb  (paket bulut-provizyonu icerecek)")
    return 0


def cmd_list(args) -> int:
    d = _yukle_arsiv(Path(args.inp))
    print(f"Arsiv: {args.inp}  (sifreli: {d.get('sifreli')})")
    for k in d["kalemler"]:
        print(f"  - {k['ad']}  (<{k['boyut']} B>)")
    print(f"Toplam {len(d['kalemler'])} sir.")
    return 0


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    ap = argparse.ArgumentParser(description="PEMF makine-ozel sir yedegi (parolasiz, tasinabilir)")
    sub = ap.add_subparsers(dest="komut", required=True)
    b = sub.add_parser("backup", help="sirlari topla")
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
