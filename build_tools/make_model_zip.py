# Author: mertaygn, cglrgrkn
"""make_model_zip.py — Profil model paketlerini (`home/vet/research.zip`) üretir.

NEDEN VAR (2026-08-10). Bu paketler daha önce ELLE üretiliyordu; içerikleri hiçbir yerde
yazılı değildi. `inference_cat_organ` modellerinin `home.zip` içinde olduğu ancak yayındaki
zip'in merkezî dizini uzaktan okunarak keşfedildi ve "Veteriner profili Ev Sahibi'ne
bağımlı" hatasının kaynağı buydu. İçerik artık KODDA tek-kaynak.

ÇEKİRDEK MODEL KURALI. `inference_cat_organ` (AI Pro organ lokalizasyonu) ÇEKİRDEĞE alındı
(`make_base_zip.py::CORE_MODELS` → deps katmanı → frozen bundle). Bu yüzden profil
paketlerinde YER ALMAZ — aksi hâlde ev sahibi kullanıcı aynı ~209 MB'ı İKİ KEZ indirir.
Çözüm sırası dosya-başınadır (`utils/model_downloader.find_installed_model`), yani paketten
çıkarmak hiçbir profilde özelliği bozmaz; bkz. `tests/test_cekirdek_model_cozumu.py`.

Kullanım:  python build_tools/make_model_zip.py [home|vet|research] ...
           (argümansız → hepsi)
"""

from __future__ import annotations

import hashlib
import os
import sys
import zipfile
from pathlib import Path

KOK = Path(__file__).resolve().parent.parent
KAYNAK = KOK / "release_assets" / "ai_models"
# ⚠️ DENETİM 2026-08-17 (`make_base_zip.py` ile AYNI gerekçe ve AYNI değişken adı): çıktı dizini
# SABİTTİ, bu yüzden bu betiği test etmek GERÇEK yayın varlığını ezerdi — 318 MB'lık
# `pemf-app-packages/home.zip`, manifest'te `client-app-v1.9.11` etiketine PİNLİ. Ezilen/sha'sı
# değişen dosyada `make_manifest.py` URL'yi YENİ etikete taşır, ama BUILD.md yükleme listesinde
# `home.zip` YOK → "Ev Sahibi" profilinde deterministik 404.
# `PEMF_PKG_OUT` ile testler tmp'ye yazar, yayın dosyalarına HİÇ dokunmaz.
# ⚠️ VARSAYILAN DAVRANIŞ DEĞİŞMEDİ: env yoksa bugünkü dizin (boş string de varsayılana düşer).
# ⚠️ `mkdir` BİLEREK `zip_yaz` İÇİNDE kalıyor; `make_base_zip.py`nin modül-seviyesi `makedirs`i
# KOPYALANMAZ — `tests/test_cekirdek_model_cozumu.py` bu modülü düz import ediyor ve import'un
# dosya sistemi yan etkisi OLMAMALI.
CIKTI = Path(os.environ.get("PEMF_PKG_OUT") or (KOK / "pemf-app-packages"))

# Deterministik zip: aynı girdi → aynı sha256. make_base_zip.py ile AYNI sabit.
SABIT_TARIH = (1980, 1, 1, 0, 0, 0)

# ⚠️ ÇEKİRDEKTE olan modeller — hiçbir profil paketine GİRMEZ (bkz. modül docstring'i).
CEKIRDEK_HARIC = ("ai_hub/inference_cat_organ/",)

# Profil → paket içeriği. Yollar `release_assets/ai_models` köküne GÖRELİ ve zip içinde
# `ai_models/<yol>` olarak yer alır (launcher `install_root/ai_models` altına açar;
# bkz. launcher/core/src/install.rs::models_dir).
PROFILLER: dict[str, tuple[str, ...]] = {
    # 2026-08-10 öncesi yayındaki home.zip 11 dosyaydı; 3 cat_organ ONNX'i ÇEKİRDEĞE taşındı.
    # 2026-08-26 (XAI Faz 2): EfficientNet_Lite0.pt eklendi — ses Grad-CAM ısı haritası
    # PT ikizi ister (Faz-0 karar #2: klinik makinelerde de; download_model_sync YEREL çözer).
    "home": (
        "ai_hub/cat_landmark/thresholds_calibrated.json",
        "ai_hub/cat_landmark/yolo26m-pose.onnx",
        "ai_hub/cat_segmentation/yolov8m-seg.onnx",
        "ai_hub/inference_cat_sound/EfficientNet_Lite0.onnx",
        "ai_hub/inference_cat_sound/EfficientNet_Lite0.pt",
        "ai_hub/cat_disease/label_encoder.pkl",
        "ai_hub/cat_disease/scaler_X.pkl",
        "ai_hub/cat_disease/XGBoost.onnx",
        "ai_hub/cat_disease/XGBoost.pkl",
    ),
    # 2026-08-26: vet/research listeleri YAYINDAKİ zip merkez-dizinlerinden keşfedilip koda
    # alındı (home ile AYNI gerekçe — içerik elle/yazısızdı, v1.8.0'a pinliydi) + XAI PT
    # ikizleri eklendi. Sıra ve mevcut girdiler BİREBİR korunmuştur.
    "vet": (
        "ai_hub/em_kedi/BiLSTM_XXL_Raw.onnx",
        "ai_hub/em_kedi/scaler_extra.pkl",
        "ai_hub/em_kedi/scaler_X.pkl",
        "ai_hub/em_kedi/scaler_y.pkl",
        "ai_hub/em_kedi_legacy/ResNet_kedi_v2.onnx",
        "ai_hub/em_kedi_legacy/scaler_extra_kedi.pkl",
        "ai_hub/em_kedi_legacy/scaler_X_kedi_v2.pkl",
        "ai_hub/em_kedi_legacy/scaler_y_kedi_v2.pkl",
        "ai_hub/cat_thermal/GhostNetV2.onnx",
        # XAI Faz 2: termal Grad-CAM PT ikizi. (xai_ref_stats.npz'ler BİLEREK YOK:
        # modül dizinlerinde commit'li → app katmanıyla/EXE-gömülü giderler.)
        "ai_hub/cat_thermal/GhostNetV2.pt",
    ),
    "research": (
        "ai_hub/inference_renal_histopath_kmc/v22_kmc_classictrio_kmc.onnx",
        # ⚠️ RENAL PT (v22_...pt ~858MB) BILEREK LISTEDE DEGIL (2026-08-26, OLCULDU):
        # GitHub release asset siniri 2 GiB (2147483648 B) — PT'li research.zip 2.51GB
        # HTTP 422 'size must be less than 2147483648' ile REDDEDILDI. PT release_assets
        # tek-kaynaginda durur: GPU mikroservis (/models mount) renal XAI'yi CALISTIRIR;
        # klinik tek-EXE'de PT yoksa zarif 'Aciklama uretilemedi' dususu. Sahaya inis
        # LAUNCHER COKLU-MODEL-ZIP destegi (research'u bolme) isine bagli — plan notu.
        # ⚠️ SCRATCH PT (ginoro ~872MB) da ayni sebeple ana listede DEGIL.
        # FAZ 4.5 COZUMU (2026-08-26): iki buyuk PT artik `PARCALAR['research-2']`
        # ile AYRI zip'te gider (launcher 1.9.39 model_parts destegi); eski
        # launcher'larda davranis degismez (PT'siz research, zarif dusus).
        "ai_hub/inference_em_petri/BaggingRegressor.onnx",
        "ai_hub/em_petri/PetriNet_v3.onnx",
        "ai_hub/em_petri/scaler_D_petri_v3.pkl",
        "ai_hub/em_petri/scaler_extra_petri_v3.pkl",
        "ai_hub/em_petri/scaler_E_petri_v3.pkl",
        "ai_hub/em_petri/scaler_X_petri_v3.pkl",
        "ai_hub/em_phantom/PhantomNet_v3.onnx",
        "ai_hub/em_phantom/scaler_D_phantom_v3.pkl",
        "ai_hub/em_phantom/scaler_extra_phantom_v3.pkl",
        "ai_hub/em_phantom/scaler_E_phantom_v3.pkl",
        "ai_hub/em_phantom/scaler_X_phantom_v3.pkl",
        "ai_hub/inference_em_fantom/BiLSTM_XXL_Raw.onnx",
        "ai_hub/inference_em_fantom/scaler_extra.pkl",
        "ai_hub/inference_em_fantom/scaler_X.pkl",
        "ai_hub/inference_em_fantom/scaler_y.pkl",
        "ai_hub/inference_human_kidney_ct/yolov8s.onnx",
        "ai_hub/petri_dish/yolo11m-seg.onnx",
        "ai_hub/inference_petri_dish/yolo11m-seg.onnx",
        "ai_hub/feline_reticulocytes/yolov8s.onnx",
        # XAI Faz 2 kuyruğu: EigenCAM PT ikizleri (CT — Faz-0 #4 AGPL onaylı; feline).
        # (xai_ref_stats.npz'ler app katmanında — bkz. vet notu.)
        "ai_hub/inference_human_kidney_ct/yolov8s.pt",
        "ai_hub/feline_reticulocytes/yolov8s.pt",
    ),
}


# ── FAZ 4.5 (2026-08-26, docs/scratch-entegrasyon-plani.md): PROFIL EK PARCALARI ─────
# GitHub release asset siniri 2 GiB (OLCULDU: HTTP 422 'size must be less than
# 2147483648'). research'un iki buyuk PT'si (renal 858MB + scratch CPN 872MB) ana
# zip'e SIGMAZ → ayri parca zip'i. Manifest'te OPSIYONEL `model_parts` alaninda
# gider (launcher 1.9.39): eski launcher'lar alani gormez → bugunku davranislari
# (PT'siz research, zarif dusus) bit degismeden surer; yeni launcher ana zip'ten
# SONRA parcalari da indirir/acar. Ad sozlesmesi: `<profil>-<n>.zip` (n>=2).
PARCALAR: dict[str, tuple[str, ...]] = {
    "research-2": (
        "ai_hub/inference_renal_histopath_kmc/v22_kmc_classictrio_kmc.pt",
        "ai_hub/inference_paper_dilek_hoca/ginoro_CpnResNeXt101UNet-fbe875f1a3e5ce2c.pt",
    ),
}

# GitHub tek-asset ust siniri — bir paket bunu asarsa hata YAYIN ANINDA (422) degil
# URETIM ANINDA patlar (olculen tuzagi one cek; zip_yaz icinde denetlenir).
GITHUB_ASSET_SINIRI = 2_147_483_648


def dosyalari_topla(profil: str, tablo: dict[str, tuple[str, ...]] = PROFILLER) -> list[tuple[Path, str]]:
    ciftler: list[tuple[Path, str]] = []
    for rel in tablo[profil]:
        if rel.startswith(CEKIRDEK_HARIC):
            raise SystemExit(
                f"[HATA] '{rel}' CEKIRDEKTE — profil paketine konulamaz (cift indirme). "
                "Cekirdek modeller make_base_zip.py::CORE_MODELS ile paketlenir."
            )
        src = KAYNAK / rel
        if not src.is_file():
            raise SystemExit(f"[HATA] kaynak yok: {src}")
        ciftler.append((src, f"ai_models/{rel}"))
    return ciftler


def zip_yaz(profil: str, tablo: dict[str, tuple[str, ...]] = PROFILLER) -> Path:
    ciftler = dosyalari_topla(profil, tablo)
    CIKTI.mkdir(parents=True, exist_ok=True)
    hedef = CIKTI / f"{profil}.zip"
    # ⚠️ ATOMİK YAZIM (DENETİM 2026-08-17; `make_base_zip.py::_yaz` ile AYNI desen). Hedef eskiden
    # DOĞRUDAN 'w' ile açılıp KIRPILIYORDU: yazım ortasında bir hata olursa (okunamayan kaynak,
    # disk dolması, Ctrl-C) `zipfile`ın `__exit__`i merkezi dizini YAZDIĞI için diskte "GEÇERLİ
    # ama EKSİK" bir `home.zip` kalıyordu — ölçüldü: 3 girdi yerine 1, `testzip()` yine None.
    # `make_manifest.py` `home.zip` için bütünlük kontrolü YAPMAZ, sha'yı MÜHÜRLER ve EXIT=0 verir.
    # ⚠️ '.tmp' UZANTISI BİLEREK: `make_manifest.py` SABİT ad tablosu kullanır ve
    # `gh release upload ... *.zip` joker'i bu adı GÖRMEZ. '.new.zip' gibi bir ad yarım dosyayı
    # yayına sokabilirdi (testle kilitli).
    gecici = str(hedef) + ".tmp"
    try:
        with open(gecici, "wb") as cikis:
            # ⚠️ BAYT BİÇİMİ AYNEN KORUNUYOR: `writestr` + `PROFILLER` BEYAN SIRASI (sorted DEĞİL)
            # + SABIT_TARIH + ZIP_STORED. Ölçüldü: `z.open(..., force_zip64=True)` akış yolu girdi
            # başına +20 bayt (zip64 ek alanı) ekliyor ve `sorted()` sırayı değiştiriyor; ikisi de
            # sha'yı kaydırır → `make_manifest` URL'yi home.zip'in YÜKLENMEDİĞİ etikete taşır → 404.
            # Bu yüzden `make_base_zip._yaz` ORTAK YARDIMCI YAPILMADI (o `sorted` + `force_zip64`
            # kullanıyor); iki paketleyici bilerek bağımsız kaldı.
            # ⚠️ Dosya nesnesine yazmak baytları DEĞİŞTİRMEZ (ölçüldü: aynı sha) — akış SEEK
            # EDİLEBİLİR olduğu için veri-tanımlayıcı biti yazılmıyor.
            with zipfile.ZipFile(cikis, "w", zipfile.ZIP_STORED, allowZip64=True) as z:
                for src, arc in ciftler:
                    zi = zipfile.ZipInfo(arc, date_time=SABIT_TARIH)
                    zi.compress_type = zipfile.ZIP_STORED
                    zi.external_attr = 0o644 << 16
                    with open(src, "rb") as fh:
                        z.writestr(zi, fh.read())
            cikis.flush()
            os.fsync(cikis.fileno())  # elektrik kesintisinde rename'den ONCE veri diskte olsun
        # FAZ 4.5 BEKCISI: 2 GiB'i asan paket yayina HIC cikmasin (research+PT'de
        # HTTP 422 OLCULDU) — hata uretim aninda, gecici dosya silinerek verilir.
        boyut = os.path.getsize(gecici)
        if boyut >= GITHUB_ASSET_SINIRI:
            raise SystemExit(
                f"[HATA] {hedef.name} {boyut} bayt — GitHub asset siniri "
                f"{GITHUB_ASSET_SINIRI} bayti asiyor; iceriği yeni bir PARCALAR "
                "girdisine bol (docs/scratch-entegrasyon-plani.md Faz 4.5)."
            )
        os.replace(gecici, hedef)
    finally:
        if os.path.exists(gecici):
            os.remove(gecici)  # basarisiz kosudan artik birakma (git status temiz kalir)
    return hedef


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def dogrula(profil: str, hedef: Path, tablo: dict[str, tuple[str, ...]] = PROFILLER) -> bool:
    with zipfile.ZipFile(hedef) as z:
        adlar = z.namelist()
    kapilar = {
        "cekirdek model YOK (cift indirme onlendi)": not any("inference_cat_organ" in n for n in adlar),
        "dosya sayisi beklenen": len(adlar) == len(tablo[profil]),
        "hepsi ai_models/ onekli": all(n.startswith("ai_models/") for n in adlar),
    }
    ok = True
    for ad, gecti in kapilar.items():
        print(f"  [{'OK' if gecti else 'HATA'}] {ad}")
        ok = ok and gecti
    return ok


def main(argv: list[str]) -> int:
    tum = {**PROFILLER, **PARCALAR}
    istenen = argv or list(tum)
    bilinmeyen = [p for p in istenen if p not in tum]
    if bilinmeyen:
        print(f"[HATA] tanimsiz profil: {', '.join(bilinmeyen)}  (var: {', '.join(tum)})")
        return 2
    tamam = True
    for profil in istenen:
        tablo = PROFILLER if profil in PROFILLER else PARCALAR
        hedef = zip_yaz(profil, tablo)
        boyut = hedef.stat().st_size
        print(f"\n{profil}.zip : {boyut} bayt ({boyut / 1e6:.1f} MB)  sha256 {sha256(hedef)}")
        tamam = dogrula(profil, hedef, tablo) and tamam
    print(f"\nVALIDATION: {'PASS' if tamam else 'FAIL'}")
    return 0 if tamam else 1


if __name__ == "__main__":
    raise SystemExit(main([a for a in sys.argv[1:] if not a.startswith("-")]))
