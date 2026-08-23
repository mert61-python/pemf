#!/usr/bin/env python3
# Author: mertaygn, cglrgrkn
"""manifest.json üretici — elle düzenlemeyi bitirir.

NEDEN: manifest bugüne kadar elle güncelleniyordu ve `publish.ps1` yorumunda kayda
geçtiği üzere bir kez `base_linux` eksik kalıp Linux istemcisi sessizce Windows
paketini indirmişti. Digest/boyut da elle yazılıyordu → yanlış sha256 = kullanıcıda
"doğrulama başarısız". Bu betik ikisini de dosyalardan ÜRETİR.

Şema v2 yazar, v1 alanlarını da GERİYE UYUM için korur (sahadaki v1.8.0 istemcileri
`base`/`base_linux`/`base_mac` okur; yeni launcher `runtimes`/`models` okur).

Kullanım:
  python scripts/make_manifest.py \
      --dir pemf-app-packages \
      --version 1.8.0 \
      --tag client-app-v1.8.0 \
      --repo mert61-python/pemf-update
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

# ⚠️ CIKTI KODLAMASI SABITLENIR (denetim 2026-08-18): betigin Turkce mesajlari (`Yazıldı:` vb.)
# konsol kod sayfasi `ı`yi kodlayamayan bir Windows makinesinde `UnicodeEncodeError` firlatiyordu.
# Manifest DOSYASI yazildiktan SONRA, yalnizca yazdirma sirasinda cokuyordu → dosya diskte dogru
# ama cikis kodu 1: yayin otomasyonu adimi "basarisiz" sanip durur. Sahibin makinesinde kod sayfasi
# cp1254 oldugu icin hic gorunmedi; GitHub Windows runner'inda (cp1252) `test_manifest_degismeyen_
# paket_url.py` bunu yakaladi. `bootstrap.ps1`in vaadi "herhangi bir laptopta build+publish" oldugu
# icin bu tasinabilirlik hatasidir.
for _akis in (sys.stdout, sys.stderr):
    try:
        _akis.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    except Exception:  # noqa: BLE001 — eski/yonlendirilmis akisda reconfigure yoksa sessizce gec
        pass

# dosya adı -> (v2 bölümü, v2 anahtarı, v1 anahtarı)
ASSETS = {
    "base.zip": ("runtimes", "win-x64", "base"),
    "base-linux.zip": ("runtimes", "linux-x64", "base_linux"),
    "base-mac.zip": ("runtimes", "mac-arm64", "base_mac"),
    "home.zip": ("models", "home", None),
    "vet.zip": ("models", "vet", None),
    "research.zip": ("models", "research", None),
}

# ── KATMANLI PAKETLER (v1.9.13+) ─────────────────────────────────────────────────────────
# ⚠️ DENETİM 2026-08-09 (ENGEL): bu betik `layers`i ne ÜRETİYOR ne de TAŞIYORDU. Manifest her
# yeniden üretildiğinde bölüm DÜŞÜYOR ve client >=1.9.13 tek-parça `runtimes`e geri dönüyordu:
# sıradan bir sürümde 71 MB yerine 1,25 GB indirme. Sessiz, çünkü her şey "çalışmaya" devam eder.
# dosya adı -> (platform anahtarı, katman adı)
LAYER_ASSETS = {
    "base-app.zip": ("win-x64", "app"),
    "base-deps.zip": ("win-x64", "deps"),
    "base-linux-app.zip": ("linux-x64", "app"),
    "base-linux-deps.zip": ("linux-x64", "deps"),
    "base-mac-app.zip": ("mac-arm64", "app"),
    "base-mac-deps.zip": ("mac-arm64", "deps"),
}

# Bu betiğin ÜRETEMEYECEĞİ, yalnızca ÖNCEKİ manifest'ten TAŞINAN bloklar. Hepsi ayrı bir yayın
# kanalında (launcher-v* tag'i) üretilir; burada dosyaları YOKTUR. Taşınmazlarsa sessizce ölürler.
#   launcher → client'ın kendi oto-güncellemesi
#   mobile   → APK'nın kendi oto-güncellemesi (versionCode karşılaştırması)
CARRY_ONLY = ("launcher", "mobile")


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True, type=Path, help="paketlerin bulunduğu klasör")
    ap.add_argument("--version", required=True)
    ap.add_argument("--tag", required=True)
    ap.add_argument("--repo", required=True, help="örn. mert61-python/pemf-update")
    ap.add_argument("--out", type=Path, default=None, help="varsayılan: <dir>/manifest.json")
    ap.add_argument(
        "--drop-missing",
        action="store_true",
        help="Yerelde olmayan paketleri manifest'ten DÜŞÜR (varsayılan: mevcut manifest'ten taşı)",
    )
    ap.add_argument(
        "--allow-missing-launcher",
        action="store_true",
        help="'launcher' blogu olmadan manifest yazmaya IZIN VER (varsayilan: HATA). Blok "
        "duserse sahadaki tum client'larin oto-guncellemesi sessizce olur.",
    )
    ap.add_argument(
        "--allow-missing-mobile",
        action="store_true",
        help="'mobile' blogu olmadan manifest yazmaya IZIN VER (varsayilan: onceki manifest'te "
        "VARSA hata). Blok duserse sahadaki tum APK'larin oto-guncellemesi sessizce olur.",
    )
    ap.add_argument(
        "--rollout",
        type=int,
        default=None,
        metavar="0-100",
        help="Dagitim yuzdesi (layers.<platform>.rollout). SAHIP KARARI 2026-08-19: kademeli "
        "dagitim KALDIRILDI — verilmezse 100. Istisna: onceki manifest 0 (geri cekme) ise "
        "SESSIZCE 100'e donmez, acikca --rollout 100 gerekir. 0 = acil fren (hala gecerli).",
    )
    ap.add_argument(
        "--min-supported-version",
        default=None,
        metavar="X.Y.Z",
        help="GERI CAGIRMA: bu surumden ESKI kurulumlar destek disi → guncelleme rollout "
        "dilimine BAKILMAKSIZIN uygulanir. `--rollout 0` yalniz YENI dagitimi durdurur, "
        "sahadaki cihaza dokunmaz; bir bobin-guvenligi hatasinda asil gereken budur. "
        "Bos string ('') vererek KALDIRILIR.",
    )
    ap.add_argument(
        "--drop-platform",
        action="append",
        default=[],
        metavar="PLATFORM",
        help="Bu platformu manifest'ten TAMAMEN cikar (runtimes + layers + v1 anahtari). "
        "Ornek: --drop-platform mac-arm64 --drop-platform linux-x64. "
        "SEBEP: paketi bayat/desteklenmeyen bir platformu manifest'te tutmak, o platformda "
        "ESKI ve KENDINI GUNCELLEYEMEYEN bir cihaz kurulmasina yol acar; client 'paket yok' "
        "deyip DURMASI daha iyidir. `--drop-missing`ten farki: yalnizca SECILEN platformu "
        "kaldirir, digerlerinin tasinmasini bozmaz.",
    )
    ap.add_argument(
        "--launcher-rollout",
        type=int,
        default=None,
        metavar="0-100",
        help="LAUNCHER self-update yuzdesi (launcher.rollout). Bozuk bir client yayinindan "
        "donmenin TEK yolu budur: yeni launcher kurulduktan sonra eskisi calistirilamaz. "
        "0 = yayini ANINDA durdur. Runtime rollout'undan AYRI bir karardir.",
    )
    args = ap.parse_args()

    if args.rollout is not None and not (0 <= args.rollout <= 100):
        print("[HATA] --rollout 0-100 araliginda olmali.", file=sys.stderr)
        return 1
    if args.launcher_rollout is not None and not (0 <= args.launcher_rollout <= 100):
        print("[HATA] --launcher-rollout 0-100 araliginda olmali.", file=sys.stderr)
        return 1

    base_url = f"https://github.com/{args.repo}/releases/download/{args.tag}"
    out_path = args.out or (args.dir / "manifest.json")

    manifest: dict = {
        "schema": 2,
        "version": args.version,
        "tag": args.tag,
        "runtimes": {},
        # Katmanlı paketler (client >=1.9.13 bunu TERCİH EDER; `runtimes` eski client'lar için kalır).
        "layers": {},
        "models": {},
        # v1 geriye uyum: profiles + base/base_linux/base_mac aşağıda doldurulur.
        "profiles": {},
    }

    # Önceki manifest TEK KEZ okunur: taşıma, rollout korunumu ve "sessizce kaybetme" denetiminin
    # üçü de ona bakar. (Eskiden iki ayrı yerde okunuyordu.)
    prev_path = out_path if out_path.exists() else (args.dir / "manifest.json")
    prev: dict = {}
    if prev_path.exists():
        try:
            prev = json.loads(prev_path.read_text(encoding="utf-8"))
        except Exception as e:  # bozuk önceki manifest sessizce yutulmamalı
            print(f"[HATA] mevcut manifest okunamadı ({prev_path}): {e}", file=sys.stderr)
            return 1

    found, missing, url_korundu = [], [], []
    for name, (section, key, v1_key) in ASSETS.items():
        path = args.dir / name
        if not path.exists():
            missing.append(name)
            continue
        _sha = sha256(path)
        _url = f"{base_url}/{name}"
        # ══════════════════════════════════════════════════════════════════════════════════════
        # ICERIK DEGISMEDIYSE URL'yi TASIMA (DENETIM 2026-08-17) — SESSIZ 404.
        #
        # Burada URL kosulsuz `--tag`ten yeniden kuruluyordu. Ama BUILD.md bolum 6'nin yukleme
        # listesi yalniz base-app.zip / base-deps.zip / manifest.json iceriyor: `home.zip` paket
        # klasorunde DURUYOR ve yayindakiyle BIREBIR AYNI. Siradan bir app yayininda
        # `--tag client-app-v1.9.16` verilince `models.home`/`profiles.home` URL'si o etikete
        # tasiniyor, o etikete home.zip YUKLENMIYOR → 404. Sonuc: "Ev Sahibi" profilini secen her
        # YENI kurulum ve her "Onar" hata ile duser (net.rs 404'u deterministik sayar, tekrar
        # denemez). vet.zip/research.zip yerelde olmadigi icin TASINIR ve URL'leri korunur →
        # uc profilden TAM OLARAK BIRI kirilir.
        #
        # HICBIR MEVCUT KAPI GOREMEZ: `sha256` DEGISMEDIGI icin test_manifest_consistency,
        # manifest.rs::depodaki_gercek_manifest_ayristirilir ve URL-pin kontrolu yesil kalir.
        # `--drop-missing` de ise yaramaz — dosya *var*.
        #
        # DOGRU DAVRANIS: sha onceki manifest'tekiyle AYNIYSA URL KORUNUR (asset o eski etikette
        # zaten yayinda ve bayt-bayt ayni). sha DEGISTIYSE URL yeni etikete tasinir.
        # Kilit: tests/test_manifest_degismeyen_paket_url.py
        # ══════════════════════════════════════════════════════════════════════════════════════
        _onceki = (prev.get(section) or {}).get(key) or {}
        _onceki_url = str(_onceki.get("url") or "")
        if _onceki_url and str(_onceki.get("sha256") or "") == _sha and _onceki_url != _url:
            _url = _onceki_url
            # ⚠️ ASCII: bu betigin cikisi cp1254 konsola yaziliyor; ok karakteri (→)
            # UnicodeEncodeError ile SUREC COKMESINE yol acar (olculdu).
            # ⚠️ Etiket cikarimi SAVUNMALI: elle duzenlenmis/bozuk bir URL'de `rsplit('/', 2)[-2]`
            # IndexError verir ve manifest uretimini COKERTIRDI — oysa bu yalnizca bir LOG etiketi.
            _parca = _onceki_url.rsplit("/", 2)
            _etiket = _parca[-2] if len(_parca) >= 2 else "?"
            url_korundu.append(f"{name} (sha ayni, etiket: {_etiket})")
        entry = {
            "url": _url,
            "sha256": _sha,
            "size": path.stat().st_size,
            "kind": "zip",
        }
        manifest[section][key] = entry
        # v1 alanları
        if section == "models":
            manifest["profiles"][key] = entry
        elif v1_key:
            manifest[v1_key] = entry
        found.append(f"{name} -> {section}.{key}")

    # --- Eksikleri mevcut manifest'ten TAŞI (varsayılan davranış) ----------------
    # Paketler farklı runner'larda üretilip doğrudan release'e yüklenir (ör. base-linux.zip
    # Linux CI'da üretilir, bu makinede HİÇ bulunmaz). Yerelde yok diye düşürülürse o
    # platformun istemcisi kurulum yapamaz hale gelir — sessiz regresyon. Bu yüzden
    # varsayılan MERGE'dir; kasten silmek için --drop-missing gerekir.
    carried = []
    if missing and not args.drop_missing and prev:
        for name in list(missing):
            section, key, v1_key = ASSETS[name]
            # v2'den, yoksa v1 alanından al.
            entry = (prev.get(section) or {}).get(key)
            if entry is None and v1_key:
                entry = prev.get(v1_key)
            if entry is None and section == "models":
                entry = (prev.get("profiles") or {}).get(key)
            if entry is not None:
                manifest[section][key] = entry
                if section == "models":
                    manifest["profiles"][key] = entry
                elif v1_key:
                    manifest[v1_key] = entry
                missing.remove(name)
                carried.append(f"{name} -> {section}.{key} (mevcut manifest'ten)")

    # ── KATMANLAR: yereldeki app/deps paketlerinden ÜRET, eksikleri ÖNCEKİNDEN taşı ──────────
    for name, (plat, katman) in LAYER_ASSETS.items():
        path = args.dir / name
        if not path.exists():
            continue
        _sha = sha256(path)
        _url = f"{base_url}/{name}"
        # ICERIK DEGISMEDIYSE URL'yi TASIMA — yukaridaki ASSETS kuralinin KATMANLARA uyarlanmasi
        # (2026-08-19 yayininda yakalandi): deps sha'si paket-belirlenimciligi sayesinde yayinlar
        # arasi SABIT kaliyor; URL kosulsuz yeni etikete tasininca iki kotu secenek doguyordu:
        # deps yeni etikete YUKLENMEZSE her taze kurulum 404 alir; YUKLENIRSE her yayinda 1,4 GB
        # gereksiz yukleme. sha onceki manifest'tekiyle AYNIYSA asset eski etikette bayt-bayt
        # ayni yayindadir -> URL korunur. Kilit: tests/test_manifest_degismeyen_paket_url.py
        _onceki = ((prev.get("layers") or {}).get(plat) or {}).get(katman) or {}
        _onceki_url = str(_onceki.get("url") or "")
        if _onceki_url and str(_onceki.get("sha256") or "") == _sha and _onceki_url != _url:
            _url = _onceki_url
            _parca = _onceki_url.rsplit("/", 2)
            _etiket = _parca[-2] if len(_parca) >= 2 else "?"
            url_korundu.append(f"{name} (sha ayni, etiket: {_etiket})")
        manifest["layers"].setdefault(plat, {})[katman] = {
            "url": _url,
            "sha256": _sha,
            "size": path.stat().st_size,
            "kind": "zip",
        }
        found.append(f"{name} -> layers.{plat}.{katman}")

    # `--drop-missing` "öncekinden HİÇBİR ŞEY taşıma" demektir. Katmanlar yerelde ÜRETİLEBİLDİĞİ
    # için diğer varlıklarla aynı sınıftadır ve bu bayrağa uyar. (`launcher`/`mobile` uymaz:
    # onlar burada üretilemez, taşınmazlarsa hiç var olamazlar.)
    for plat, onceki in ({} if args.drop_missing else (prev.get("layers") or {})).items():
        if not isinstance(onceki, dict):
            continue
        yeni = manifest["layers"].setdefault(plat, {})
        # Bir katman yerelde üretildiyse DİĞERİ de aynı yayından olmalı: karışık bir set
        # (yeni `app` + eski `deps`) tutarsız kurulum demektir — app yeni koda, deps eski
        # kütüphanelere bakar. Bu yüzden taşıma YALNIZ bu platform için yerelde HİÇBİR katman
        # üretilmediğinde yapılır. Karar döngüden ÖNCE alınmalı: `app` taşındıktan sonra
        # sözlük dolduğu için aynı koşul `deps`i sessizce atlıyordu.
        yerelde_uretildi = bool(yeni)
        if not yerelde_uretildi:
            for katman in ("app", "deps"):
                if katman in onceki:
                    yeni[katman] = onceki[katman]
                    carried.append(f"layers.{plat}.{katman} (mevcut manifest'ten)")
        if not yeni:
            manifest["layers"].pop(plat, None)

    # rollout: dosyalardan TÜRETİLEMEZ, bir YAYIN KARARIDIR.
    # SAHİP KARARI (2026-08-19 gece): KADEMELİ DAĞITIM KALDIRILDI — bayrak verilmezse VARSAYILAN
    # ARTIK 100 (eskiden önceki değer korunuyordu; %10'da unutulmuş yayınlar oluyordu, bkz.
    # pemf-yayin-2026-08-18 "ROLLOUT %10'DA AÇIK KALDI").
    # ⚠️ TEK İSTİSNA — GERİ ÇEKME FRENİ KORUNUR: önceki manifest'te rollout=0 (bilinçli geri
    # çekme; bozuk yayından dönüşün TEK yolu) ise bayraksız yeniden-üretim onu SESSİZCE 100'e
    # DÖNDÜREMEZ — 0 korunur ve yüksek sesle uyarılır. %100'e dönüş ancak açıkça `--rollout 100`
    # ile olur. Kilit: tests/test_make_manifest.py::test_KRITIK_geri_cekilmis_rollout_SIFIRLANMAZ.
    for plat, katmanlar in manifest["layers"].items():
        if args.rollout is not None:
            katmanlar["rollout"] = args.rollout
        else:
            onceki_r = ((prev.get("layers") or {}).get(plat) or {}).get("rollout")
            if onceki_r == 0:
                katmanlar["rollout"] = 0
                print(
                    f"[UYARI] layers.{plat}.rollout=0 KORUNDU (geri cekilmis yayin) — "
                    "%100'e donmek icin acikca --rollout 100 verin."
                )
            else:
                katmanlar["rollout"] = 100

    # ── AÇIKÇA ÇIKARILAN PLATFORMLAR ────────────────────────────────────────────────────────
    # ⚠️ 2026-08-09 (Tier 1): bayat/desteklenmeyen bir platformu manifest'te tutmak, o platformda
    # ESKİ ve KENDİNİ GÜNCELLEYEMEYEN bir cihaz kurulmasına yol açar (self-update Windows'a özel;
    # `layers` yoksa rollout freni de yok → bozuk yayın geri çekilemez). Client'ın "bu platform
    # için paket yok" deyip DURMASI, sessizce kilitli bir cihaz kurmasından iyidir.
    dusurulen = []
    for plat in args.drop_platform or []:
        vardi = plat in manifest["runtimes"] or plat in manifest["layers"]
        manifest["runtimes"].pop(plat, None)
        manifest["layers"].pop(plat, None)
        for _name, (_sec, _key, _v1) in ASSETS.items():
            if _sec == "runtimes" and _key == plat and _v1:
                manifest.pop(_v1, None)
        if vardi:
            dusurulen.append(plat)

    # ── GERİ ÇAĞIRMA EŞİĞİ ──────────────────────────────────────────────────────────────────
    # Verilmezse ÖNCEKİ değer korunur: yeniden üretim, yürürlükteki bir geri çağırmayı sessizce
    # kaldırmamalı (rollout geri-çekmesiyle aynı gerekçe).
    if args.min_supported_version is not None:
        if args.min_supported_version.strip():
            manifest["min_supported_version"] = args.min_supported_version.strip()
    elif prev.get("min_supported_version"):
        manifest["min_supported_version"] = prev["min_supported_version"]

    # ── Açıklama notları (_*) ve YALNIZCA-TAŞINAN bloklar ───────────────────────────────────
    for k, v in prev.items():
        if k.startswith("_") and k not in manifest:
            manifest[k] = v

    # ── launcher bloğu: ÜRETİLMEZ, TAŞINIR (denetim 2026-08-04, P2) ──────────────
    # `launcher{version,url,installer_url,sha256,size}` client'ın KENDİ oto-güncellemesini
    # besler: launcher/app/src/main.rs `manifest.launcher.as_ref().and_then(...)` — alan
    # Option olduğu için YOKSA kontrol SESSİZCE atlanır, hiçbir hata görünmez.
    # Bu blok ASSETS tablosunda YOK ve yukarıdaki taşıma döngüsü yalnız ASSETS'i geziyor →
    # manifest her yeniden üretildiğinde launcher bloğu DÜŞÜYORDU. Sonuç: sahadaki TÜM
    # client'lar oto-güncellemeyi kalıcı olarak kaybeder. Setup.exe ayrı bir yayın kanalı
    # (launcher-v* tag'i) olduğundan burada üretilemez → mevcut manifest'ten AYNEN taşınır.
    # ⚠️ 2026-08-09: `mobile` de aynı sınıfa eklendi (bkz. CARRY_ONLY) — o da ayrı bir tag'de
    # yayınlanır, burada üretilemez ve taşınmazsa sahadaki TÜM APK'lar güncellemeyi kaybeder.
    for _blok in CARRY_ONLY:
        _deger = prev.get(_blok)
        if _deger:
            manifest[_blok] = _deger
            # ⚠️ 2026-08-09 (Tier 1): launcher self-update'inin geri-çekme anahtarı. Runtime'da
            # bu fren vardı ama güncellemeyi YÖNETEN bileşende yoktu; bozuk bir client yayını
            # sahadaki her cihaza gidiyor ve dönüş yolu kalmıyordu.
            if _blok == "launcher":
                if args.launcher_rollout is not None:
                    manifest[_blok] = {**_deger, "rollout": args.launcher_rollout}
                else:
                    # SAHİP KARARI (2026-08-19): kademeli dağıtım yok — bayraksız üretimde
                    # launcher.rollout da 100'e çekilir; TEK istisna bilinçli geri çekme (0),
                    # o SESSİZCE dirilmez (uyarıyla korunur; dönüş ancak --launcher-rollout 100).
                    _onceki_lr = _deger.get("rollout")
                    if _onceki_lr == 0:
                        print(
                            "[UYARI] launcher.rollout=0 KORUNDU (geri cekilmis yayin) — "
                            "%100'e donmek icin acikca --launcher-rollout 100 verin."
                        )
                    else:
                        manifest[_blok] = {**_deger, "rollout": 100}
            _s = _deger.get("version") or (_deger.get("android") or {}).get("version") or "?"
            carried.append(f"{_blok} v{_s} (mevcut manifest'ten)")
        elif prev_path.exists():
            print(
                f"[UYARI] mevcut manifest'te '{_blok}' bloğu YOK → ilgili oto-güncelleme "
                f"ÇALIŞMAYACAK. İlgili yayından sonra bloğu elle ekleyin.",
                file=sys.stderr,
            )
    if not prev_path.exists():
        print(
            "[UYARI] önceki manifest bulunamadı → 'launcher'/'mobile' blokları taşınamadı; "
            "client ve APK oto-güncellemesi ÇALIŞMAYACAK.",
            file=sys.stderr,
        )

    if not manifest["runtimes"]:
        print("[HATA] hiçbir base paketi bulunamadı — manifest yazılmadı.", file=sys.stderr)
        return 1

    # ⚠️ DENETİM 2026-08-04 (P3): `launcher` bloğu düşerse yalnızca stderr'e UYARI basılıp ÇIKIŞ
    # KODU 0 ile manifest yazılıyordu. Yayın akışı (publish_release.ps1 / CI) sıfır çıkışı
    # "başarılı" sayar → sahadaki TÜM client'lar için oto-güncelleme SESSİZCE ölür ve bu ancak
    # kimse güncelleme alamayınca fark edilir. Uyarı, sessiz bir üretim arızasını durdurmaz.
    # Bilerek launcher'sız manifest üretmek isteyen açıkça `--allow-missing-launcher` demeli.
    if not manifest.get("launcher") and not args.allow_missing_launcher:
        print(
            "[HATA] 'launcher' bloğu YOK — client oto-güncellemesi ÇALIŞMAZDI, manifest "
            "yazılmadı. Bilerek istiyorsanız --allow-missing-launcher verin.",
            file=sys.stderr,
        )
        return 1

    # ── ⚠️ DENETİM 2026-08-09 (ENGEL): SESSİZ KAYIP KAPISI ──────────────────────────────────
    # Yukarıdaki `launcher` kontrolü doğru fikrin TEK bir bölüme uygulanmış hâliydi. Asıl kural
    # şudur: ÖNCEKİ manifest'te olan bir bölüm, yenisinde SEBEPSİZ kaybolmamalı. `layers` ve
    # `mobile` tam olarak böyle düştü — ikisi de betiğe hiç eklenmemişti ve kayıp, herkes
    # 1,25 GB indirmeye başlayana / kimse APK güncellemesi almayana kadar GÖRÜNMEZ.
    # `--drop-missing` bunu bilerek yapmanın açık yoludur.
    if prev and not args.drop_missing:
        kayip = []
        if (
            (prev.get("layers") or {})
            and not manifest["layers"]
            and not any(p in (args.drop_platform or []) for p in (prev.get("layers") or {}))
        ):
            kayip.append("layers (client >=1.9.13 tek-parça base.zip'e düşer: ~71 MB yerine 1,25 GB)")
        # ⚠️ DENETİM 2026-08-23 (Y5): bu kapı ULAŞILAMAZDI. Yukarıdaki CARRY_ONLY taşıması
        # `manifest["mobile"]`ı `prev`ten zaten dolduruyor → `not manifest.get("mobile")` hiçbir
        # zaman doğru olamıyordu; `--allow-missing-mobile` bayrağı da fiilen işlevsizdi (testi
        # bile bayrağı hiç geçirmeden EXIT=0 bekliyordu). Yayıncı çalışan bir koruma sandı.
        # Doğru ölçüm: `prev`te VARDI ama çıktıya GEÇMEDİYSE — taşıma kodu bozulursa yakalanır.
        if prev.get("mobile") and not manifest.get("mobile"):
            if args.allow_missing_mobile:
                print("[manifest] UYARI: mobile bloğu bilerek düşürüldü (--allow-missing-mobile)")
            else:
                kayip.append("mobile (sahadaki tüm APK'lar oto-güncellemeyi kaybeder)")
        for plat in prev.get("layers") or {}:
            if plat in manifest["layers"] or plat in (args.drop_platform or []):
                continue
            kayip.append(f"layers.{plat}")
        if kayip:
            print("[HATA] önceki manifest'te olan bölümler kayboluyor — manifest YAZILMADI:", file=sys.stderr)
            for k in kayip:
                print(f"  - {k}", file=sys.stderr)
            print("  Bilerek siliyorsanız --drop-missing (ya da --allow-missing-mobile) verin.", file=sys.stderr)
            return 1

    # ── YARIM KATMAN SETI: app VAR, deps YOK (ya da tersi) ─────────────────────────────────
    # Karisik set (yeni app + ESKI deps) URETMEME karari DEGISMEDI; burada yalnizca SONUCU
    # gorunur kiliyoruz. Yarim set SESSIZ bir eksiklik degil: launcher tarafinda RuntimeLayers'in
    # `app`/`deps` alanlari ZORUNLU (Option da default da yok) ve ayristirma hatasi yukari tasiniyor
    # -> client TUM manifest'i "missing field" ile reddeder. Kayip o platformla da sinirli degil:
    # `layers` bir harita oldugu icin mac icin yazilmis yarim set WINDOWS istemcisini de kirar.
    # Sonuc: kurulum, guncelleme ve min_supported_version geri cagirmasi TOPYEKUN durur.
    # Bu yuzden UYARI YETMEZ -> cikis kodu 1 ve manifest YAZILMAZ.
    yarim = [
        (plat, [k for k in ("app", "deps") if k not in katmanlar]) for plat, katmanlar in manifest["layers"].items()
    ]
    yarim = [(plat, eksik) for plat, eksik in yarim if eksik]
    if yarim:
        print("[HATA] YARIM KATMAN SETI - manifest YAZILMADI:", file=sys.stderr)
        for plat, eksik in yarim:
            print(f"  - layers.{plat}: {', '.join(eksik)} EKSIK", file=sys.stderr)
        print(
            "  Karisik set (yeni app + eski deps) BILEREK uretilmez; ama yarim set de YAYINLANAMAZ:\n"
            "  client ZORUNLU 'deps'/'app' alanini bulamayinca TUM manifest'i reddeder\n"
            "  (her platformda kurulum, guncelleme ve geri cagirma durur).\n"
            "  Cozum: eksik katmani da uretip pakete koyun ya da --drop-platform ile o platformu\n"
            "  manifestten tamamen cikarin.",
            file=sys.stderr,
        )
        return 1

    # ── ⚠️ DENETİM 2026-08-09 (ENGEL): TEK SÜRÜM, TEK YAZILIM ───────────────────────────────
    # Katmanlar bu yayında YENİ üretilmiş ama tek-parça `runtimes` ÖNCEKİ manifest'ten taşınmışsa,
    # ikisi FARKLI build'lerdendir. Sahada ölçüldü: 53 dosya farklı, `PEMF_Backend.exe` dahil →
    # client <=1.9.12 base.zip'ten ESKİ backend'i, >=1.9.13 layers'tan YENİ backend'i kuruyordu.
    # Aynı sürüm numarası altında iki farklı yazılım: bir arızanın hangi kodda olduğu bilinemez.
    # Çözüm build tarafında (make_base_zip artık base.zip'i DAİMA üretir); burası yayın kapısıdır.
    taze_katman = {p for p, _ in ((plat, k) for name, (plat, k) in LAYER_ASSETS.items() if (args.dir / name).exists())}
    bayat_ciftler = []
    for plat in taze_katman:
        for name, (section, key, _v1) in ASSETS.items():
            if section == "runtimes" and key == plat and not (args.dir / name).exists():
                bayat_ciftler.append((plat, name))
    if bayat_ciftler and not args.drop_missing:
        print(
            "[HATA] katmanlar YENİ ama tek-parça base ESKİ manifest'ten taşınıyor — aynı sürüm "
            "altında İKİ FARKLI yazılım yayınlanırdı. Manifest YAZILMADI:",
            file=sys.stderr,
        )
        for plat, name in bayat_ciftler:
            print(f"  - layers.{plat} taze, runtimes.{plat} ({name}) bayat", file=sys.stderr)
        print(
            "  Çözüm: `python build_tools/make_base_zip.py` (base.zip'i de üretir) ve "
            f"{', '.join(n for _, n in bayat_ciftler)} dosyasını da bu klasöre koyun.",
            file=sys.stderr,
        )
        return 1

    # ── TEK SÜRÜM, TEK YAZILIM — İÇERİK SAĞLAMASI (2026-08-09, Tier 1 eki) ──────────────────
    # Yukarıdaki kapı "katmanlar taze ama base bayat" durumunu yakalar. ÜÇÜ DE yerelde varken
    # yine de İÇERİK olarak ayrışmış olabilirler — gerçek durum tam olarak buydu: yayındaki
    # base.zip ile base-app+base-deps 53 dosyada farklıydı, `PEMF_Backend.exe` dahil.
    #
    # ⚠️ BİLEREK UYARI, HATA DEĞİL. Asıl kapı build tarafındadır (`make_base_zip.py` uyuşmazsa
    # DURUR). Bu betik ise ACİL DURUM aracıdır: bozuk bir yayını `--launcher-rollout 0` ile geri
    # çekmek, paketlerin yeniden üretilmesini BEKLEYEMEZ. Emniyet kontrolünü acil çıkışın önüne
    # koymak, korumaya çalıştığı şeyden daha büyük zarar verirdi.
    try:
        import zipfile

        _b, _a, _d = (args.dir / "base.zip", args.dir / "base-app.zip", args.dir / "base-deps.zip")
        if _b.exists() and _a.exists() and _d.exists():

            def _crc(z):
                with zipfile.ZipFile(z) as f:
                    return {i.filename: i.CRC for i in f.infolist() if not i.is_dir()}

            _mono, _kat = _crc(_b), _crc(_a)
            _kat.update(_crc(_d))
            if _mono != _kat:
                _fark = len([n for n in set(_mono) & set(_kat) if _mono[n] != _kat[n]])
                print(
                    f"\n[UYARI] base.zip ile base-app+base-deps AYNI DEGIL: {_fark} dosyanin "
                    f"icerigi farkli, {len(set(_kat) - set(_mono))} dosya yalniz katmanlarda, "
                    f"{len(set(_mono) - set(_kat))} dosya yalniz base.zip'te.\n"
                    "  Eski client'lar (<=1.9.12) base.zip'i, yeniler layers'i kurar → AYNI surum "
                    "numarasi altinda FARKLI yazilim dagitilir.\n"
                    "  Duzeltme: `python build_tools/make_base_zip.py` (ucunu birden yeniden "
                    "uretir) ve UCUNU DE yayina yukleyin.",
                    file=sys.stderr,
                )
    except Exception as e:
        print(f"[UYARI] paket icerik saglamasi yapilamadi: {e}", file=sys.stderr)

    out_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print(f"Yazıldı: {out_path}")
    for line in found:
        print(f"  + {line}")
    for line in carried:
        print(f"  = {line}")
    # SESSİZ OLMAZ: yayıncı, hangi paketin URL'sinin ESKİ etikette bırakıldığını görmeli — aksi
    # halde diff'te "neden bu URL değişmedi?" sorusu cevapsız kalır (bkz. URL taşıma notu).
    for line in url_korundu:
        print(f"  ~ URL KORUNDU: {line} - bu etikete yeniden YUKLEMEK GEREKMEZ")
    for plat in dusurulen:
        print(f"  - {plat} MANIFEST'TEN CIKARILDI (--drop-platform)")
    if missing:
        # SESSİZ ATLAMA YOK: eksik base = o platformun istemcisi kurulum yapamaz.
        # Yeni launcher sert hata verir (sessizce yanlış paketi İNDİRMEZ), ama
        # yayıncının bunu bilerek yapması gerekir.
        print("\n[UYARI] Bu paketler bulunamadı, manifest'e GİRMEDİ:", file=sys.stderr)
        for m in missing:
            print(f"  - {m}", file=sys.stderr)
        print("  Eksik platformun istemcisi 'paket yayınlanmamış' hatası verecek.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
