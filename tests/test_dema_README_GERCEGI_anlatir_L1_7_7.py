# -*- coding: utf-8 -*-
"""L1-7.7 (A-37 · D5.36 / D6.70 kolu) — DEMA simülatörü README'si GERÇEĞİ anlatır, AI Studio şablonunu değil.

🔴 ÖLÇÜLEN (HEAD ebf1c3fe): `dema-terapi-simülatörü/README.md` Google AI Studio şablonunun aynısıydı: "Run and deploy your AI Studio app",
AI Studio bağlantısı ve "Set the `GEMINI_API_KEY` … to your Gemini API key" ADIMI. Oysa simülatörün kaynağı Gemini'yi çağırmaz (`src/` içinde
`@google/genai` / `GEMINI_API_KEY` yok — bu kapı ölçer), dizin A-37 gereği TANITIM / EĞİTİM aracıdır ve ürün onu `dist/` olarak `/simulator`dan
sunar (derleme `build_tools/build_installer.ps1`, paket denetimi `build_tools/dema_iddia_denetimi.py`). Belgeyi okuyan geliştirici gereksiz bir
API anahtarı arıyor ve aracın ne olduğunu (etiketini) belgeden öğrenemiyordu.

ÖLÇÜT (iki yönlü, kodla): kaynak Gemini'yi ÇAĞIRMIYORSA README anahtar KURULUM adımı vermez ve "AI Studio app" şablon başlığını taşımaz; kaynak
çağırırsa (ileride) README anahtarı anlatmak ZORUNDA. README ayrıca A-37 etiketini ve ürünün kullandığı derleme / sunum yolunu anar.
"""

from __future__ import annotations

import re
from pathlib import Path

KOK = Path(__file__).resolve().parents[1]
DEMA = KOK / "dema-terapi-simülatörü"
README = DEMA / "README.md"


def kaynak_gemini_kullanir(kok: Path = DEMA) -> bool:
    """`src/` altındaki TS/TSX kaynağı Gemini istemcisini içe aktarıyor ya da anahtarı okuyor mu (yorumlar soyulur)."""
    for d in [*(kok / "src").rglob("*.ts"), *(kok / "src").rglob("*.tsx")]:
        t = d.read_text(encoding="utf-8")
        t = re.sub(r"/\*.*?\*/", " ", t, flags=re.S)
        t = "\n".join(re.sub(r"(^|\s)//.*$", " ", s) for s in t.splitlines())
        if re.search(r"@google/genai|GoogleGenAI|GEMINI_API_KEY", t):
            return True
    return False


def test_KRITIK_README_AI_Studio_sablonu_DEGIL_ve_gereksiz_anahtar_adimi_YOK():
    metin = README.read_text(encoding="utf-8")
    if not kaynak_gemini_kullanir():
        assert not re.search(r"AI Studio app", metin), "README hâlâ AI Studio şablon başlığını taşıyor"
        assert not re.search(r"Set the `?GEMINI_API_KEY`?|GEMINI_API_KEY`?\s+(?:in|değerini)\s", metin), (
            "kaynak Gemini'yi çağırmıyor ama README GEMINI_API_KEY KURULUM adımı veriyor"
        )
        assert not re.search(r"ai\.studio/apps/", metin), "README AI Studio uygulama bağlantısı veriyor"
    else:
        assert "GEMINI_API_KEY" in metin, "kaynak Gemini'yi çağırıyor — README anahtarın nasıl verileceğini anlatmalı"
        assert not re.search(r"Gemini'yi ÇAĞIRMAZ|anahtar GEREKMEZ", metin), (
            "kaynak Gemini'yi ÇAĞIRIYOR ama README 'çağırmaz / anahtar gerekmez' diyor"
        )


def test_KRITIK_README_A37_etiketini_ve_urun_yolunu_anlatir():
    metin = README.read_text(encoding="utf-8")
    duz = re.sub(r"\*\*|\s+", " ", metin)
    assert re.search(r"[Tt]anıtım\s*/\s*eğitim amaçlıdır, cihaz davranışını temsil\s+etmez", duz), (
        "README A-37 etiketini söylemiyor"
    )
    for parca in ("build_installer.ps1", "dema_iddia_denetimi.py", "npm run build"):
        assert parca in metin, f"README ürünün kullandığı yolu anmıyor: {parca}"
    sunum = re.search(r"\*\*Sunum:\*\*(.*?)(?:\n- \*\*|\n## )", metin, re.S)
    assert sunum and "`/simulator`" in sunum.group(1) and "api_server.py" in sunum.group(1), (
        "README 'Sunum' maddesi backend'in simülatörü hangi yoldan (`/simulator`, api_server.py) sunduğunu söylemiyor"
    )
    kod = (KOK / "apps" / "backend" / "servers" / "api_server.py").read_text(encoding="utf-8")
    assert re.search(r'app\.mount\("/simulator",', kod), (
        "README `/simulator` diyor ama backend o yolu bağlamıyor — belge ya da kod bayat"
    )


def test_KARSIT_KANIT_gemini_olcucusu_kaynagi_GORUR(tmp_path):
    """Ölçücü gerçek bir içe aktarmayı GÖRÜR, yalnız yorumdakini GÖRMEZ."""
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.tsx").write_text(
        "// import { GoogleGenAI } from '@google/genai'\nexport const x = 1\n", encoding="utf-8"
    )
    assert kaynak_gemini_kullanir(tmp_path) is False
    (tmp_path / "src" / "b.ts").write_text("import { GoogleGenAI } from '@google/genai'\n", encoding="utf-8")
    assert kaynak_gemini_kullanir(tmp_path) is True


# TUR 2 (çürütücü kolu): anahtar KURULUM adımı yalnız İngilizce şablon cümlesiyle ("Set the `GEMINI_API_KEY` …") aranıyordu; aynı adımın Türkçesi
# ("`.env.local` dosyasına Gemini API anahtarınızı yazın") YAŞIYORDU (mutant `cur177_n1`). Emir kipi + anahtar / .env.local birlikteyse adımdır.
_ANAHTAR_KURULUM = re.compile(
    r"(?:GEMINI_API_KEY|Gemini\s+API\s+(?:anahtar\w*|key)|\.env\.local)[^.\n]{0,80}?\b(?:yazın|girin|ekleyin|ayarlayın|tanımlayın|koyun|set|add|put)\b"
    r"|\b(?:Set|Add|Put)\b[^.\n]{0,40}(?:GEMINI_API_KEY|Gemini\s+API\s+key)",
    re.I,
)


def anahtar_kurulum_adimlari(metin: str) -> list[str]:
    return [m.group(0) for m in _ANAHTAR_KURULUM.finditer(metin)]


def test_KRITIK_README_anahtar_KURULUM_adimi_hicbir_dilde_YOK():
    bulgular = anahtar_kurulum_adimlari(README.read_text(encoding="utf-8"))
    assert kaynak_gemini_kullanir() or not bulgular, (
        f"kaynak Gemini'yi çağırmıyor ama README anahtar kurulum adımı veriyor (dil fark etmez): {bulgular}"
    )


def test_KARSIT_KANIT_anahtar_adimi_deseni_AYIRIYOR():
    assert anahtar_kurulum_adimlari("2. `.env.local` dosyasına Gemini API anahtarınızı yazın.")
    assert anahtar_kurulum_adimlari("Set the `GEMINI_API_KEY` in .env.local to your Gemini API key")
    assert not anahtar_kurulum_adimlari(
        "`vite.config.ts`deki `GEMINI_API_KEY` tanımı şablondan kalmadır — çalıştırmak için anahtar GEREKMEZ."
    )
    assert not anahtar_kurulum_adimlari("(yerelde çalıştırma + Gemini API anahtarı\ntalimatı)")
