# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""ARKA PLAN İNDİRMESİ KULLANICI DENETİMİ — saha bildirimi 2026-08-28.

Klinik ekranında 1,39 GB'lık `deps` paketi inerken kullanıcının DURDURMA YOLU YOKTU: kartta
yalnız ilerleme çubuğu vardı ("%76 · 649 KB/s · ~9 dk kaldı"), tek bir düğme yoktu.

⚠️ SINIF: "YETENEK VAR, KABLO YOK". Ölçüldü — gereken her parça zaten mevcuttu:
  * `net::Control::{Pause, Cancel}` (Pause → `.part` KORUNUR; Cancel → `.part` SİLİNİR),
  * `pause_install` / `cancel_install` Tauri komutları,
  * kurulum yolları bunları üç ayrı yerde ZATEN okuyordu.
Bağlanmamış olan tek yer arka plan indirmesiydi: `prefetch_runtime_update` içinde
`&|| net::Control::Continue` SABİTİ veriliyordu, yani hiçbir kontrol ulaşamıyordu. Üstelik
`resume_install` komutu HİÇ YOKTU (kurulum yolları bayrağı tur başında sıfırladığı için
eksikliği görünmüyordu).

Bu dosya UI↔Rust kablosunu kilitler. Çekirdek davranış (control'e uyma) ayrıca
`launcher/core/tests/arka_plan_indirme_denetimi.rs` ile kilitlenir — ikisi BİRLİKTE anlamlıdır:
Rust testi "motor çalışıyor", bu test "pedal bağlı" der.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

_KOK = Path(__file__).resolve().parents[1]
_MAIN_RS = _KOK / "launcher" / "app" / "src" / "main.rs"
_UI = _KOK / "launcher" / "app" / "ui" / "index.html"


def _prefetch_govdesi() -> str:
    """`prefetch_runtime_update` komutunun gövdesi.

    ⚠️ Pencere `prefetch_updates` ÇAĞRISINDA biter: ilk hâli 4000 karakter alıyordu ve
    komşu fonksiyonlardaki `CTL_PAUSE` geçişlerine taşıyordu — sabit `Continue`a dönen
    mutasyon kapıyı YEŞİL bırakıyordu (ölçüldü)."""
    metin = _MAIN_RS.read_text(encoding="utf-8")
    i = metin.find("async fn prefetch_runtime_update")
    if i == -1:
        i = metin.find("fn prefetch_runtime_update")
    assert i != -1, "prefetch_runtime_update komutu bulunamadı (çıpa kaymış olabilir)"
    # Bir sonraki üst-seviye `fn`e kadar (komut gövdesi) — komşu fonksiyonlara TAŞMAZ.
    j = metin.find("\n#[tauri::command]", i + 10)
    if j == -1:
        j = i + 4000
    return metin[i:j]


def _prefetch_cagrisi() -> str:
    """`flow::prefetch_updates(...)` çağrısının kendisi — kontrol closure'ı dâhil."""
    govde = _prefetch_govdesi()
    i = govde.find("flow::prefetch_updates(")
    assert i != -1, "prefetch_updates çağrısı bulunamadı"
    return govde[i : i + 700]


# ── 1) Rust: arka plan indirmesi kontrolü DİNLİYOR ───────────────────────────


def test_KRITIK_on_indirme_SABIT_Continue_KULLANMIYOR():
    """Bulgunun ta kendisi: sabit `Continue` → kullanıcı hiçbir şeyi durduramaz."""
    cagri = _prefetch_cagrisi()
    assert "&|| net::Control::Continue)" not in cagri, (
        "arka plan indirmesi SABİT Continue ile çağrılıyor — kullanıcı hiçbir şeyi durduramaz (bulgunun ta kendisi)"
    )
    assert "CTL_PAUSE" in cagri and "CTL_CANCEL" in cagri, (
        "arka plan indirmesi duraklat/iptal bayrağını OKUMUYOR (yetenek var, kablo yok)"
    )


def test_KRITIK_resume_komutu_VAR_ve_KAYITLI():
    """`pause_install`ın karşılığı olmadan duraklatılan indirme sonsuza dek duraklı kalır.

    ⚠️ Arka plan turu bayrağı BİLEREK sıfırlamaz (kullanıcının kararı ezilmesin); bu yüzden
    açık bir `resume_install` komutu ZORUNLU."""
    metin = _MAIN_RS.read_text(encoding="utf-8")
    assert "fn resume_install" in metin, "resume_install komutu YOK → duraklatma geri alınamaz"
    i = metin.find("generate_handler")
    assert i != -1
    kayit = metin[i : i + 3000]
    for komut in ("pause_install", "cancel_install", "resume_install"):
        assert komut in kayit, f"{komut} Tauri handler listesinde KAYITLI DEĞİL → UI çağıramaz"


def test_KRITIK_kullanici_karari_HATA_olarak_raporlanmaz():
    """ "Duraklat"a basan kullanıcıya "indirme tamamlanamadı" demek yanlış geri bildirimdir."""
    govde = _prefetch_govdesi()
    assert '"paused"' in govde and '"cancelled"' in govde, (
        "duraklat/iptal ayrı durum olarak raporlanmıyor → UI bunları hata sanır"
    )


def test_KRITIK_durum_kodu_HATA_TIPINDEN_cikariliyor():
    """⚠️ Kırılgan-çıpa koruması: hata METNİNE bakan bir ayrım, cümle bir gün düzenlenince
    SESSİZCE bozulur ve kullanıcının "duraklat"ı yine "tamamlanamadı" diye görünür."""
    govde = _prefetch_govdesi()
    assert "NetError::Paused" in govde and "NetError::Cancelled" in govde, (
        "durum kodu hata TİPİNDEN çıkarılmıyor (metin eşleştirme kırılgandır)"
    )
    assert '.contains("duraklat")' not in govde, "metin tabanlı ayrım kullanılıyor"


# ── 2) UI: düğmeler var ve GERÇEKTEN bağlı ───────────────────────────────────


def _ui() -> str:
    return _UI.read_text(encoding="utf-8")


def test_KRITIK_UI_duraklat_ve_iptal_dugmeleri_VAR():
    """Ekranda düğme yoksa Rust tarafındaki yetenek kullanıcıya ulaşmaz (bulgunun özü)."""
    m = _ui()
    assert 'id = "bg-pause"' in m or 'id="bg-pause"' in m or 'btnDuraklat.id = "bg-pause"' in m, (
        "arka plan indirmesinde DURAKLAT düğmesi yok"
    )
    assert "bg-cancel" in m, "arka plan indirmesinde İPTAL düğmesi yok"


@pytest.mark.parametrize("komut", ["pause_install", "cancel_install", "resume_install"])
def test_KRITIK_UI_komutlari_GERCEKTEN_cagiriyor(komut):
    """⚠️ ZAYIF-ÇIPA KORUMASI: düğme var ama komutu çağırmıyorsa hiçbir şey değişmez."""
    assert f'invoke("{komut}")' in _ui(), f"UI {komut} komutunu çağırmıyor — düğme süs olur"


def test_KRITIK_iptal_ONAY_soruyor_ve_KAYBI_soyluyor():
    """İptal `.part`ı SİLER: 1,4 GB baştan iner. Kullanıcı bunu "duraklat" sanmamalı."""
    m = _ui()
    # ⚠️ ÇIPA ÇAĞRIYA pinli: ilk hâli yalnız metnin TANIMLI olmasına bakıyordu, oysa asıl mesele
    # onayın SORULMASI. `confirm(...)` satırını silen mutasyon kapıyı yeşil bırakıyordu (ölçüldü).
    i_iptal = m.find("btnIptal.onclick")
    assert i_iptal != -1, "İptal düğmesinin tıklama işleyicisi bulunamadı"
    handler = m[i_iptal : i_iptal + 900]
    assert "confirm(" in handler, "iptal ONAY SORMUYOR — tek tıkla 1,4 GB çöpe gider"
    assert "bgCancelConfirm" in handler, "onay metni yerelleştirilmiş anahtardan gelmiyor"
    i = m.find("bgCancelConfirm:")
    assert i != -1
    metin = m[i : i + 400]
    assert "SİLİNİR" in metin or "BAŞTAN" in metin, f"onay metni kaybı açıkça söylemiyor: {metin[:160]}"
    assert "Duraklat" in metin, "onay metni daha ucuz seçeneği (Duraklat) önermiyor"


def test_KRITIK_devam_ET_turu_YENIDEN_baslatiyor():
    """Bayrağı serbest bırakmak yetmez: duraklatma indirmeyi SONLANDIRIR (Paused hatası),
    yeni bir tur başlatılmalı. `.part` korunduğu için Range ile kaldığı yerden sürer."""
    # ⚠️ ÇIPA GERÇEK HANDLER'A pinli: ilk hâli `bg-pause` dizesinin İLK geçtiği yeri (etiket
    # yazıcısı `bgButonlariYaz`) buluyordu ve orada `invoke` yok — kapı yanlış yeri ölçüyordu.
    m = _ui()
    i = m.find("btnDuraklat.onclick")
    assert i != -1, "Duraklat düğmesinin tıklama işleyicisi bulunamadı (çıpa kaymış olabilir)"
    pencere = m[i : i + 1600]
    assert 'invoke("resume_install")' in pencere, "Devam et resume_install çağırmıyor"
    assert 'invoke("prefetch_runtime_update"' in pencere, (
        "Devam et yeni tur başlatmıyor → duraklatılan indirme hiç sürmez"
    )


def test_KRITIK_periyodik_tur_KULLANICI_kararini_EZMIYOR():
    """Periyodik tur 6 saatte bir koşar; duraklatan kullanıcının indirmesini kendiliğinden
    yeniden başlatmamalı — yoksa "Duraklat" birkaç saat sonra sessizce geri alınır."""
    m = _ui()
    assert re.search(r"if \(prefetchDuraklatildi \|\| prefetchIptalEdildi\) return;", m), (
        "periyodik tur duraklatılmış/iptal edilmiş indirmeyi yeniden başlatabiliyor"
    )


@pytest.mark.parametrize(
    "anahtar", ["bgPause", "bgResume", "bgCancel", "bgCancelConfirm", "rtBgPaused", "rtBgCancelled"]
)
def test_metinler_IKI_DILDE_de_var(anahtar):
    """Launcher iki dilli; eksik anahtar `undefined` düğme etiketi demektir."""
    m = _ui()
    assert m.count(f"{anahtar}:") >= 2, (
        f"'{anahtar}' iki dilde tanımlı değil ({m.count(f'{anahtar}:')} kez) → bir dilde boş görünür"
    )


def test_KARSIT_KANIT_mevcut_ilerleme_gosterimi_BOZULMADI():
    """Düğmeler eklendi diye çubuk/yüzde/ETA kaybolmamalı."""
    m = _ui()
    for parca in ("bgbar", "bgpct", "bgsub", "etaLeft"):
        assert parca in m, f"mevcut ilerleme gösterimi bozuldu: '{parca}' yok"
