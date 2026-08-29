# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""LAUNCHER ARAYÜZÜ AYRIŞTIRILABİLİR OLMALI — saha arızası 2026-08-29.

⚠️ ÜRÜNÜ TAMAMEN ÇÖKERTEN BİR HATA HİÇBİR KAPIYA TAKILMADI.

Olan: `index.html` içindeki bir dil metnine (`bgCancelConfirm`) `\\n` kaçışı yerine GERÇEK
SATIR SONU girdi. JavaScript'te bir dize sabiti satır sonunda kapanmadığı için `SyntaxError:
Invalid or unexpected token` oluştu → `<script type="module">` bloğunun TAMAMI çalışmadı →
launcher açılışta "Ortam algılanıyor…" ekranında SONSUZA DEK kaldı (başlıkta `v—`, hiçbir düğme
yok, uygulama kullanılamaz). Klinik makinesi güncelledikten sonra ürünü hiç açamıyordu.

Neden yakalanmadı — mevcut kapıların hepsi UI'nın PARÇALARINA bakıyordu:
  * `test_arkaplan_bar_davranisi.py` / `test_devam_et_duraklatilmis_guncelleme.py`:
    tek tek FONKSİYONLARI çıkarıp Node'da koşturuyor → sözlük (dil metinleri) bloğu hiç girmiyor,
  * diğer testler kaynak metinde dize arıyor → sözdizimi hatası bir dizeyi "var" göstermeye devam eder,
  * Rust testleri UI'ya hiç bakmıyor, `cargo build` HTML'i AYRIŞTIRMADAN gömüyor.
Yani ürünün en temel değişmezi — "arayüz kodu çalışabiliyor mu" — hiç ölçülmüyordu.

⚠️ KÖK NEDEN (yöntemsel): dosya heredoc ile yazılmıştı ve kabuk ters bölüyü yedi. Bu tuzak
projede daha önce de yaşandı; kural: ters bölü içeren içerik heredoc'la YAZILMAZ.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

_KOK = Path(__file__).resolve().parents[1]
_UI = _KOK / "launcher" / "app" / "ui" / "index.html"
_NODE = shutil.which("node")


def _script_govdesi() -> str:
    ham = _UI.read_text(encoding="utf-8")
    m = re.search(r'<script type="module">(.*?)</script>', ham, re.S)
    assert m, "index.html içinde `<script type=\"module\">` bloğu bulunamadı (çıpa kaymış olabilir)"
    return m.group(1)


@pytest.mark.skipif(not _NODE, reason="node yok")
def test_KRITIK_UI_JAVASCRIPTI_AYRISTIRILABILIYOR(tmp_path):
    """Tüm script bloğu geçerli JS olmalı.

    Bu kapı olmadan tek bir kaçış hatası ürünü açılmaz hâle getirir ve yayına kadar görünmez
    (2026-08-29'da tam olarak bu oldu: launcher 1.9.40 "Ortam algılanıyor…"da donuyordu).
    """
    f = tmp_path / "ui.mjs"
    f.write_text(_script_govdesi(), encoding="utf-8")
    r = subprocess.run([_NODE, "--check", str(f)], capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, (
        "launcher arayüzünün JavaScript'i AYRIŞTIRILAMIYOR → uygulama açılışta donar "
        f"(kullanıcı yalnız 'Ortam algılanıyor…' görür):\n{r.stderr[:1200]}"
    )


@pytest.mark.skipif(not _NODE, reason="node yok")
def test_KRITIK_dil_metinlerinde_KAPANMAMIS_dize_yok(tmp_path):
    """Dize sabitleri satır sonunda kapanmadan bırakılmamalı (asıl arızanın biçimi).

    `node --check` bunu zaten yakalar; bu test HATANIN YERİNİ söyler: hangi anahtar bozuk.
    Sözlük satırları `ad: "..."` biçimindedir ve tek satırda kapanmalıdır."""
    bozuk = []
    for no, satir in enumerate(_script_govdesi().splitlines(), 1):
        s = satir.strip()
        m = re.match(r'^([A-Za-z_][\w]*)\s*:\s*"', s)
        if not m:
            continue
        # Satırdaki KAÇIŞSIZ çift tırnakları say; açılan dize aynı satırda kapanmalı.
        govde = s[m.end() - 1 :]
        tirnaklar = len(re.findall(r'(?<!\\)"', govde))
        if tirnaklar % 2 != 0:
            bozuk.append(f"satır {no}: {m.group(1)} → {s[:70]}")
    assert not bozuk, (
        "Bu dil metinlerinde dize satır sonunda KAPANMIYOR (muhtemelen `\\n` yerine gerçek "
        "satır sonu girmiş) — JS ayrıştırılamaz ve arayüz hiç açılmaz:\n" + "\n".join(bozuk)
    )


def test_KRITIK_cok_satirli_metinler_KACIS_kullaniyor():
    """Kullanıcıya çok satırlı metin gösteren anahtarlar `\\n` KAÇIŞI içermeli.

    Onay kutusundaki paragraf ayrımı `\\n\\n` ile yapılır; gerçek satır sonu JS'i bozar."""
    govde = _script_govdesi()
    for anahtar in ("bgCancelConfirm",):
        m = re.search(rf'{anahtar}:\s*"([^"\\]*(?:\\.[^"\\]*)*)"', govde)
        assert m, f"'{anahtar}' tek satırlık bir dize olarak bulunamadı — satır sonu içeriyor olabilir"
        assert "\\n" in m.group(1), f"'{anahtar}' paragraf ayrımı için `\\n` kaçışı kullanmıyor"


@pytest.mark.skipif(not _NODE, reason="node yok")
def test_KARSIT_KANIT_kapi_gercekten_kirmizi_olabiliyor(tmp_path):
    """Kapının boş çalışmadığının kanıtı: bozuk bir dize `node --check`i düşürmeli.

    (Asıl arızanın birebir biçimi: dize satır sonunda kapanmıyor.)"""
    f = tmp_path / "bozuk.mjs"
    f.write_text('const t = { a: "kapanmayan dize\nikinci satir" };\n', encoding="utf-8")
    r = subprocess.run([_NODE, "--check", str(f)], capture_output=True, text=True, timeout=120)
    assert r.returncode != 0, "node --check bozuk dizeyi kabul etti — kapı hiçbir şey ölçmüyor"
