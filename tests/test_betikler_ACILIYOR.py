# -*- coding: utf-8 -*-
"""BETİKLER AÇILIYOR MU + DOCKER COPY YOLLARI GERÇEK Mİ — taşıma artığı `ModuleNotFoundError`.

🔴 ÖLÇÜLEN DURUM (2026-09-21, sahip isteği "bütün modülleri kontrol et"):
F4 taşıması (`apps/backend/`) import köklerini kaydırdı ve ÜÇ giriş betiği ÖLMÜŞTÜ —
açılışta `ModuleNotFoundError: No module named 'utils'`:

  · `scripts/stm_firmware_kimligi.py`  ⚠️ ürünün KENDİ hata mesajının operatöre önerdiği
    tanılama betiği (`utils/stm32_kimlik.uyum_denetle`: *"Dogrulama: python
    scripts/stm_firmware_kimligi.py"*) — firmware uyumsuzluğunda operatör ÇALIŞMAYAN bir
    komuta yönlendiriliyordu
  · `build_tools/source_crypto.py` · `build_tools/encrypt_sources.py` (kod şifreleme zinciri)

Ve `docker/Dockerfile.ai` altı satırda `COPY utils/...` diyordu; `utils/` artık kökte değil
→ **GPU AI imajı hiç derlenmiyordu** (build context `..`, bkz. `docker-compose.ai.yml`).

⚠️ Aynı sınıf bu depoda daha önce DÖRT kez ısırdı: `tools/e2e_*.py` (2 gün ölü) ·
   beş-biçimli dizin adı · betiğin kendi konumunu kırması · 54 kırık belge bağlantısı.
   Kod tarafında kapı vardı; BETİK + DOCKER yüzeyi ölçülmemişti.

⚠️ BU KAPI ÖNCE KÖRDÜ, MUTASYON YAKALADI: kaynakta `sys.path.insert` DİZESİNİ arıyordu.
   Döngüyü boşaltan mutasyon (`for _yol in ():`) dizeyi yerinde bıraktığı için kapı yeşil
   kaldı. Artık betiğin İMPORT ÖNSÖZÜ gerçekten koşturuluyor (`tests/onsoz_kosucu.py`).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from utils.path_utils import kaynak_kokunu_bul

KOK = kaynak_kokunu_bul(__file__)
BETIK_DIZINLERI = ("scripts/", "tools/", "build_tools/")
KOSUCU = Path(__file__).with_name("onsoz_kosucu.py")

#: MUAFİYET — (dosya, modül): GEREKÇE. ⚠️ Kaba dizin muafiyeti YASAK; dosya+modül çifti.
MUAF: dict[tuple[str, str], str] = {}


def _takipli(desenler: list[str]) -> list[str]:
    ham = subprocess.run(["git", "ls-files", "-z"] + desenler, cwd=KOK, capture_output=True, timeout=180).stdout
    return [x.decode("utf-8") for x in ham.split(b"\x00") if x]


def _onsozleri_kostur(
    dosyalar: list[str], kok: Path | None = None, ic_importlar: bool = False
) -> list[tuple[str, str]]:
    """Alt-süreçte önsözleri koştur; [(dosya, hata)] döndür. `ic_importlar`: fonksiyon/try içi import'lar da."""
    r = subprocess.run(
        [sys.executable, str(KOSUCU), str(kok or KOK), json.dumps(dosyalar)]
        + (["--ic-importlar"] if ic_importlar else []),
        cwd=str(KOK),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=600,
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
    )
    assert r.returncode == 0, f"önsöz koşucusu düştü:\n{r.stderr[-1500:]}"
    satirlar = [s for s in r.stdout.strip().splitlines() if s.strip()]
    assert satirlar, f"koşucu çıktı üretmedi:\n{r.stderr[-800:]}"
    return [tuple(x) for x in json.loads(satirlar[-1])]


# ──────────────────────────────────────────────────────────────────────────
# 0) KARŞIT-KANIT — koşucu GERÇEKTEN ölüyü ölü, sağlamı sağlam görüyor mu
# ──────────────────────────────────────────────────────────────────────────


def test_KARSIT_KANIT_kosucu_OLUYU_GORUYOR(tmp_path):
    """⚠️ Kapı bu koşucuya dayanıyor; önce ONU kanıtla — pozitif VE negatif."""
    (tmp_path / "olu_betik.py").write_text("import kesinlikle_olmayan_modul_xyz\n", encoding="utf-8")
    (tmp_path / "saglam_betik.py").write_text("import json\nX = 1\n", encoding="utf-8")

    sonuc = _onsozleri_kostur(["olu_betik.py", "saglam_betik.py"], kok=tmp_path)
    adlar = {x[0] for x in sonuc}
    assert "olu_betik.py" in adlar, "koşucu ÖLÜ betiği görmedi — kapı hiçbir şey ölçmüyor"
    assert "saglam_betik.py" not in adlar, "koşucu SAĞLAM betiği ölü sandı"


def test_KARSIT_KANIT_kosucu_YOLU_DARALTIYOR(tmp_path):
    """`apps/backend` yolu BIRAKILIRSA ölü betik sağlam görünür — daraltma ŞART."""
    (tmp_path / "backend_isteyen.py").write_text("import utils.path_utils\n", encoding="utf-8")
    sonuc = _onsozleri_kostur(["backend_isteyen.py"], kok=tmp_path)
    assert sonuc and sonuc[0][0] == "backend_isteyen.py", (
        "test süreci `conftest` yüzünden `apps/backend`i taşıyor; koşucu yolu daraltmazsa "
        "ölü betikler ÇÖZÜLÜR görünür ve kapı hiçbir şey ölçmez."
    )


def _ic_importlari_kostur(dosyalar: list[str], kok: Path | None = None) -> list[tuple[str, str]]:
    from onsoz_kosucu import IC_IMPORT_ONEKI

    return [(r, h) for r, h in _onsozleri_kostur(dosyalar, kok, ic_importlar=True) if h.startswith(IC_IMPORT_ONEKI)]


def test_KARSIT_KANIT_kosucu_FONKSIYON_ICI_olu_importu_GORUYOR(tmp_path):
    """D0Ö.19: fonksiyon/try İÇİNDEKİ birinci-taraf import — gövde koşturulmadan — görülmeli.

    Pozitif (yol kurmadan `apps/backend` paketini fonksiyonda import eden) VE negatif (yolu önsözde
    kuran; `try` içinde BİLEREK eksik üçüncü-taraf; aynı dizindeki kardeş modül) örneklerle.
    """
    (tmp_path / "apps" / "backend" / "arka").mkdir(parents=True)
    (tmp_path / "apps" / "backend" / "arka" / "__init__.py").write_text("", encoding="utf-8")
    (tmp_path / "kardes.py").write_text("X = 1\n", encoding="utf-8")
    (tmp_path / "olu_ic.py").write_text(
        "import json\n\n\ndef f():\n    try:\n        from arka import x\n    except Exception:\n        pass\n",
        encoding="utf-8",
    )
    (tmp_path / "saglam_ic.py").write_text(
        "import sys\nfrom pathlib import Path\n\n"
        "sys.path.insert(0, str(Path(__file__).resolve().parent / 'apps' / 'backend'))\n"
        "import json\n\n\ndef f():\n    import arka\n    import kardes\n"
        "    try:\n        import kesinlikle_olmayan_ucuncu_taraf_xyz\n    except ImportError:\n        pass\n",
        encoding="utf-8",
    )
    # Yolu son import'tan SONRA kuran sağlam betik (xai_batch_rapor biçimi) — aradaki BAĞIMSIZ yan
    # etki deyimi KOŞTURULMAMALI (yalnız sys.path dilimi + dayandığı tanımlar koşar; make_base_zip dersi).
    (tmp_path / "saglam_sonra.py").write_text(
        "import sys\nfrom pathlib import Path\n\n"
        "KOK = Path(__file__).resolve().parent\n"
        "(KOK / 'YAN_ETKI_KOSTU.txt').write_text('x')\n"
        "if str(KOK / 'apps' / 'backend') not in sys.path:\n"
        "    sys.path.insert(0, str(KOK / 'apps' / 'backend'))\n\n\n"
        "def f():\n    import arka\n",
        encoding="utf-8",
    )
    sonuc = _ic_importlari_kostur(["olu_ic.py", "saglam_ic.py", "saglam_sonra.py"], kok=tmp_path)
    adlar = {r for r, _ in sonuc}
    assert "olu_ic.py" in adlar, f"koşucu fonksiyon/try içindeki ÖLÜ birinci-taraf import'u görmedi: {sonuc}"
    assert "saglam_ic.py" not in adlar, f"koşucu yolu önsözde kuran sağlam betiği ölü sandı: {sonuc}"
    assert "saglam_sonra.py" not in adlar, f"koşucu yolu son import'tan sonra kuran betiği ölü sandı: {sonuc}"
    assert not (tmp_path / "YAN_ETKI_KOSTU.txt").exists(), "koşucu yol dilimi DIŞINDAKİ üst-düzey deyimi KOŞTURDU"
    # Önsöz kapısı (bayraksız) bu ölüyü GÖREMEZ — yeni adımın gerekçesi.
    assert not _onsozleri_kostur(["olu_ic.py"], kok=tmp_path), "önsöz kapısı fonksiyon içini zaten görüyormuş"


def test_KRITIK_fonksiyon_ici_ilk_taraf_importlari_COZULUYOR():
    """D0Ö.19/20/21 (B-10.57 · B-10.32 · B-9.25 · B-9.27) — betikler F4'ten beri fonksiyon İÇİNDE ölüydü.

    `hasta_anahtari_emanet._sirlari_oku` (`utils`), `vault_emanet.tatbikat` (`database`),
    `xai_batch_rapor` ses kolu (`utils.ses_kalitesi`), `soak_http_ws._veri_koku` (`utils`):
    önsöz sağlam göründü, iş yapan fonksiyon ilk çağrıda `ModuleNotFoundError` verdi — çoğu
    `except` ile yutuldu (emanet ACL'siz yazıldı, soak yanlış kökü ölçtü, rapor exit 0).
    Tüm birinci-taraf import düğümleri betiğin KENDİ kurduğu `sys.path` ile, conftest yolları
    olmadan (alt süreç, daraltılmış yol) çözülmeli ve çözüm DEPO İÇİNE düşmeli.
    """
    dosyalar = _takipli([f"{d}*.py" for d in BETIK_DIZINLERI])
    assert len(dosyalar) > 30, f"VAKUM: yalnız {len(dosyalar)} betik tarandı — tarama bozuk"
    olu = [(rel, hata) for rel, hata in _ic_importlari_kostur(dosyalar) if (rel, hata.split("'")[1]) not in MUAF]
    assert not olu, (
        "FONKSİYON/TRY İÇİNDE ÇÖZÜLEMEYEN BİRİNCİ-TARAF IMPORT:\n  "
        + "\n  ".join(f"{a} -> {b}" for a, b in olu)
        + "\n\nDüzeltme: betiğin önsözünde depo kökünü İŞARET DOSYASIYLA bulup kök + `apps/backend`i "
        "sys.path'e ekleyin (örnek: scripts/stm_firmware_kimligi.py `_depo_koku`)."
    )


# ──────────────────────────────────────────────────────────────────────────
# 1) BETİKLER — açılışta ImportError atmamalı (DAVRANIŞ)
# ──────────────────────────────────────────────────────────────────────────


def test_KRITIK_giris_betikleri_ACILISTA_patlamiyor():
    dosyalar = _takipli([f"{d}*.py" for d in BETIK_DIZINLERI])
    assert len(dosyalar) > 30, f"VAKUM: yalnız {len(dosyalar)} betik tarandı — tarama bozuk"
    olu = [
        (rel, hata)
        for rel, hata in _onsozleri_kostur(dosyalar)
        if (rel, hata.split("'")[1] if "'" in hata else "") not in MUAF
    ]
    assert not olu, (
        "AÇILIŞTA ÖLÜ BETİK:\n  "
        + "\n  ".join(f"{a} -> {b}" for a, b in olu)
        + "\n\nDüzeltme: betiğe depo kökü + `apps/backend` sys.path kurulumu ekleyin. "
        "⚠️ Kökü işaret dosyasıyla YUKARI arayın, sabit derinlikle (`parents[1]`) yazmayın."
    )


@pytest.mark.parametrize(
    "rel,beklenen_import",
    [
        ("scripts/stm_firmware_kimligi.py", "utils.stm32_kimlik"),
        ("build_tools/source_crypto.py", "utils.source_crypto"),
        ("build_tools/encrypt_sources.py", "build_tools.source_crypto"),
    ],
)
def test_DUZELTILEN_uc_betik_YASIYOR(rel: str, beklenen_import: str):
    """2026-09-21'de canlandırılan üç betik ölmesin — ve doğru modülü import etsin."""
    metin = (KOK / rel).read_text(encoding="utf-8", errors="replace")
    assert beklenen_import in metin, f"{rel}: {beklenen_import!r} kaybolmuş — çıpa bayat"
    olu = _onsozleri_kostur([rel])
    assert not olu, f"{rel} yeniden ÖLDÜ: {olu[0][1]}"


# ──────────────────────────────────────────────────────────────────────────
# 2) DOCKER — COPY kaynakları GERÇEKTEN var mı (context compose'dan OKUNUR)
# ──────────────────────────────────────────────────────────────────────────


def _compose_contextleri() -> dict[str, Path]:
    """{dockerfile_mutlak: context_dizini} — compose'dan OKUNUR, tahmin edilmez."""
    out: dict[str, Path] = {}
    for rel in _takipli(["*compose*.yml", "*compose*.yaml"]):
        p = KOK / rel
        ctx = None
        for satir in p.read_text(encoding="utf-8", errors="replace").splitlines():
            s = satir.strip()
            if s.startswith("context:"):
                ctx = s.split(":", 1)[1].strip()
            elif s.startswith("dockerfile:") and ctx is not None:
                taban = (p.parent / ctx).resolve()
                out[str((taban / s.split(":", 1)[1].strip()).resolve())] = taban
    return out


def test_KRITIK_dockerfile_COPY_kaynaklari_DISKTE_VAR():
    """`COPY <kaynak> <hedef>` kaynakları build context'inde bulunmalı.

    Ölçülen arıza: `docker/Dockerfile.ai` altı satırda `utils/...` kopyalıyordu; `utils/`
    F4'te `apps/backend/` altına gitti → imaj HİÇ derlenmiyordu, hiçbir kapı görmedi.

    ⚠️ Context TAHMİN EDİLMEZ, compose'dan okunur: `Dockerfile.frontend`in context'i
    `../apps/ui`, `Dockerfile.ai-full`ünki `release_assets`. Kökü varsaymak üç dosyayı
    YANLIŞLIKLA kırık gösteriyordu (ilk ölçümde tam bu oldu).
    """
    ctx = _compose_contextleri()
    assert ctx, "VAKUM: hiçbir compose dosyasından context okunamadı"

    kirik: list[str] = []
    bakilan = 0
    for rel in _takipli(["**/Dockerfile*"]):
        p = KOK / rel
        taban = ctx.get(str(p.resolve()))
        if taban is None:
            continue  # compose'da tanımlı değil → context bilinmiyor, iddia EDİLMEZ
        for satir in p.read_text(encoding="utf-8", errors="replace").splitlines():
            s = satir.strip()
            if not s.upper().startswith("COPY "):
                continue
            parcalar = [x for x in s.split()[1:] if not x.startswith("--")]
            if len(parcalar) < 2 or parcalar[0].startswith("<<"):
                continue  # heredoc / eksik
            for kaynak in parcalar[:-1]:
                if kaynak.startswith("/") or "*" in kaynak or "?" in kaynak:
                    continue  # önceki aşamadan / glob → dosya sistemi iddiası yok
                bakilan += 1
                if not (taban / kaynak).exists():
                    kirik.append(f"{rel}  ->  {kaynak}   (context: {taban.name})")
    assert bakilan > 10, f"VAKUM: yalnız {bakilan} COPY kaynağı sınandı"
    assert not kirik, (
        "DOCKERFILE COPY KAYNAĞI YOK:\n  "
        + "\n  ".join(kirik)
        + "\n\nKlasör taşındıysa yolu güncelleyin — imaj sessizce derlenemez hâle gelir."
    )
