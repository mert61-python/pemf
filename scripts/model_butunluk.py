# -*- coding: utf-8 -*-
# Author: mertaygn
"""AI MODEL BÜTÜNLÜĞÜ — SHA256 manifesti üret / dağıtılan kopyayı doğrula  (VERIFICATION §6).

⚠️ NEDEN GEREKLİ
================
Ağırlıklar TEK kaynakta durur (`release_assets/ai_models`, bkz. bellek `pemf-model-single-source`)
ama sahaya **kopyalanarak** gider:
    release_assets/ai_models  →  %LOCALAPPDATA%\\PEMF Vet Client\\ai_models
    release_assets/ai_models  →  <EXE>/_internal/ai_models

Kopya yolu sessizdir: yarım inen bir zip, bozulan bir sektör ya da elle değiştirilmiş bir
ağırlık **hata vermez** — model yüklenir ve YANLIŞ TEŞHİS üretir. Sürüm numarası da yakalamaz,
çünkü dosya adı aynı kalır.

⚠️ BU, `test_model_artifact_drift.py`NİN YERİNE GEÇMEZ. O, pickle'ların hangi sklearn sürümüyle
serileştirildiğini izler (sessiz "invalid results" sınıfı). Bu betik BAYT eşitliğini ölçer
(bozulma/değiştirme sınıfı). İkisi farklı arızalar.

KULLANIM
--------
    # Manifesti KAYNAKTAN uret (release_assets/ai_models) -> release_assets/ai_models_sha256.json
    python scripts/model_butunluk.py --uret

    # Dagitilan bir kopyayi manifeste gore dogrula
    python scripts/model_butunluk.py --dogrula "C:/Users/<kullanici>/AppData/Local/PEMF Vet Client/ai_models"

    # Kaynagin kendisi manifestle uyumlu mu (kapi; CI/test)
    python scripts/model_butunluk.py --dogrula release_assets/ai_models

Çıkış kodu: 0 = tamam, 1 = uyuşmazlık/eksik, 2 = kullanım hatası.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

KOK = Path(__file__).resolve().parents[1]
KAYNAK = KOK / "release_assets" / "ai_models"
MANIFEST = KOK / "release_assets" / "ai_models_sha256.json"

#: Yalnız model AĞIRLIKLARI özetlenir. `.json`/`.txt` yardımcıları sık ve masum değişir
#: (etiket listesi, config) — onları kapıya sokmak kapıyı gürültüden kullanılamaz yapar.
AGIRLIK_UZANTILARI = {".onnx", ".pt", ".pth", ".pkl", ".safetensors", ".bin"}


def _ozet(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for parca in iter(lambda: f.read(1024 * 1024), b""):
            h.update(parca)
    return h.hexdigest()


def _tara(kok: Path) -> dict[str, dict]:
    """kok altındaki ağırlıkları {göreli_yol: {sha256, bayt}} olarak döndür."""
    kayit: dict[str, dict] = {}
    for f in sorted(kok.rglob("*")):
        if not f.is_file() or f.suffix.lower() not in AGIRLIK_UZANTILARI:
            continue
        bagil = f.relative_to(kok).as_posix()
        kayit[bagil] = {"sha256": _ozet(f), "bayt": f.stat().st_size}
    return kayit


def uret() -> int:
    if not KAYNAK.is_dir():
        print(f"HATA: kaynak dizin yok -> {KAYNAK}")
        return 2
    kayit = _tara(KAYNAK)
    if not kayit:
        print(f"HATA: {KAYNAK} altinda agirlik bulunamadi (uzantilar: {sorted(AGIRLIK_UZANTILARI)})")
        return 2
    toplam = sum(v["bayt"] for v in kayit.values())
    MANIFEST.write_text(
        json.dumps({"kaynak": KAYNAK.name, "dosyalar": kayit}, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"manifest uretildi: {MANIFEST}")
    print(f"  {len(kayit)} agirlik, {toplam / 1024 / 1024:.1f} MB")
    return 0


def dogrula(hedef: Path, tam: bool = False) -> int:
    """Hedefteki ağırlıkları manifeste göre doğrula.

    ⚠️ VARSAYILAN: EKSİK dosya HATA DEĞİLDİR. Ölçüldü (2026-09-13) — model çözümü
    `apps/backend/utils/model_downloader._resolve` içinde **dosya başına** yapılır: bir ağırlık kök #1'de
    (`PEMF_AI_MODELS_DIR` = profil katmanı) yoksa kök #5'e (EXE'ye gömülü paket) düşer.
    Profil katmanı bilerek EKSİKTİR (vet profili araştırma modellerini taşımaz).

    İlk yazımda eksikler hata sayılıyordu ve kurulu profil katmanına bakınca "14 model
    EKSİK — yanlış teşhis üretebilir" diye **yanlış alarm** verdi. Asıl ölçülmek istenen
    sınıf BOZULMA/DEĞİŞTİRME; yokluk zaten `/api/ai/hazirlik?derin=1` (16/16) ile ölçülüyor.

    `--tam` verilirse eksikler de hata olur — bu, KAYNAĞIN ve GÖMÜLÜ PAKETİN kapısıdır.
    """
    if not MANIFEST.is_file():
        print(f"HATA: manifest yok -> {MANIFEST}\n  once: python scripts/model_butunluk.py --uret")
        return 2
    if not hedef.is_dir():
        print(f"HATA: hedef dizin yok -> {hedef}")
        return 2

    beklenen = json.loads(MANIFEST.read_text(encoding="utf-8"))["dosyalar"]
    eksik: list[str] = []
    bozuk: list[str] = []
    tamam = 0

    for bagil, bilgi in sorted(beklenen.items()):
        p = hedef / bagil
        if not p.is_file():
            eksik.append(bagil)
            continue
        # Boyut ucuz bir ön eleme; eşitse SHA hesapla.
        if p.stat().st_size != bilgi["bayt"] or _ozet(p) != bilgi["sha256"]:
            bozuk.append(bagil)
            continue
        tamam += 1

    print(f"hedef: {hedef}")
    print(f"  bayt-birebir eslesen: {tamam} / {len(beklenen)}")

    if bozuk:
        print(f"  ⚠️ BOZUK/DEGISMIS ({len(bozuk)}):")
        for b in bozuk[:20]:
            print(f"    - {b}")
        if len(bozuk) > 20:
            print(f"    ... +{len(bozuk) - 20} tane daha")

    if eksik:
        etiket = "EKSIK" if tam else "bu kokte yok (baska kokten cozulur — normal)"
        print(f"  {etiket} ({len(eksik)}):")
        for b in eksik[:20]:
            print(f"    - {b}")
        if len(eksik) > 20:
            print(f"    ... +{len(eksik) - 20} tane daha")

    if bozuk:
        print(
            "\nSONUC: BOZULMA — dagitilan bir agirlik kaynakla AYNI DEGIL.\n"
            "  Bu SESSIZ bir arizadir: model yine yuklenir ve YANLIS TESHIS uretebilir.\n"
            "  Duzeltme: o dosyalari release_assets/ai_models'ten yeniden kopyalayin."
        )
        return 1
    if tam and eksik:
        print(
            "\nSONUC: EKSIK — --tam istendi ama bu kok butun agirliklari tasimiyor.\n"
            "  (Profil katmaninda bu NORMALDIR; --tam yalniz KAYNAK ve GOMULU paket icindir.)"
        )
        return 1
    if eksik:
        print(
            "\nSONUC: TAMAM — mevcut agirliklarin HEPSI bayt-birebir.\n"
            "  Eksikler hata degil: model cozumu dosya basina yapilir ve gomulu pakete duser\n"
            "  (dogrulama: /api/ai/hazirlik?derin=1 -> 16/16). Tam kapsam icin --tam kullanin."
        )
        return 0
    print("\nSONUC: TAMAM — dagitilan agirliklar kaynakla BIREBIR ayni.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--uret", action="store_true", help="kaynaktan SHA256 manifesti uret")
    g.add_argument("--dogrula", metavar="DIZIN", help="bu dizini manifeste gore dogrula")
    ap.add_argument(
        "--tam",
        action="store_true",
        help="eksik agirliklari da HATA say (yalniz KAYNAK ve EXE'ye GOMULU paket icin; "
        "profil katmani bilerek eksiktir)",
    )
    a = ap.parse_args()
    return uret() if a.uret else dogrula(Path(a.dogrula), tam=a.tam)


if __name__ == "__main__":
    sys.exit(main())
