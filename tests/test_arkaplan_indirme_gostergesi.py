# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""Sahip isteği 2026-08-16: arka plan güncellemesinde YÜZDELİK real-time bar.

DURUM: yeni sürüm paketleri inmemişse client kullanıcıyı BEKLETMEZ — sessizce indirir ve
kurulumu bir sonraki açılışa bırakır (2026-08-08 sahip kararı: "hayvanı masada bekleyen
veteriner 45 dakikalık indirmeye takılmamalı"). Ama kullanıcı ne kadar kaldığını GÖREMİYORDU:
`prefetch_runtime_update` ilerlemeyi BİLEREK atıyordu (`let mut on = |_| {};`).

ÇÖZÜM: ön-indirme AYRI bir ilerleme kanalına yazar (`get_prefetch_progress`), UI onu yoklayıp
bilgi notunun içinde yüzde + ince bar çizer. Kurulum ekranı AÇILMAZ.

⚠️ KANAL NEDEN AYRI: `get_progress`i kurulum ekranı yokluyor. Ön-indirme oraya yazsaydı,
sürmekte olan bir kurulum/onarım ile iki akış birbirine karışır ve ekran ele geçirilirdi —
oysa ön-indirmenin TEK amacı kullanıcıyı bekletmemek. Bu dosya o ayrımı kilitler.
"""

import re
from pathlib import Path

import pytest

_KOK = Path(__file__).resolve().parent.parent
_MAIN_RS = _KOK / "launcher" / "app" / "src" / "main.rs"
_UI = _KOK / "launcher" / "app" / "ui" / "index.html"


@pytest.fixture(scope="module")
def rs() -> str:
    return _MAIN_RS.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def ui() -> str:
    return _UI.read_text(encoding="utf-8")


# ─────────────────────────────────────────────────────────────────────────────
# Rust: ilerleme gerçekten yayınlanıyor mu?
# ─────────────────────────────────────────────────────────────────────────────


def test_KRITIK_prefetch_ilerlemeyi_ARTIK_atmiyor(rs):
    """🔴 ASIL REGRESYON: eski hâlde ilerleme boş closure'a düşüyordu → bar hiç dolmazdı."""
    govde = re.search(r"async fn prefetch_runtime_update\((.*?)\n}", rs, re.S)
    assert govde, "prefetch_runtime_update bulunamadı"
    g = govde.group(1)
    assert "|_: flow::Progress| {}" not in g, (
        "ön-indirme ilerlemeyi hâlâ ATIYOR (boş closure) — kullanıcı yüzdeyi göremez."
    )
    assert "prefetch" in g and "lock()" in g, "ilerleme bir kanala YAZILMIYOR"


def test_KRITIK_prefetch_KENDI_kanalina_yazar_kurulum_kanalina_DEGIL(rs):
    """🔴 Ayrı kanal: aynı anda kurulum sürerken ekran ele geçirilmemeli."""
    govde = re.search(r"async fn prefetch_runtime_update\((.*?)\n}", rs, re.S).group(1)
    assert "state.prefetch.clone()" in govde, "ön-indirme `prefetch` kanalını kullanmıyor"
    assert "state.progress" not in govde, (
        "ön-indirme KURULUM kanalına (`progress`) yazıyor — kurulum ekranı bunu yoklar ve "
        "sessiz indirme ekranı ele geçirir; ön-indirmenin amacı tam tersiydi."
    )


def test_prefetch_bitince_kanal_KAPANIR(rs):
    """Bitişte `None` yazılmazsa bar son yüzdede DONMUŞ kalır ve UI 'bitti' diyemez."""
    govde = re.search(r"async fn prefetch_runtime_update\((.*?)\n}", rs, re.S).group(1)
    assert govde.count("= None") >= 2, (
        "kanal başlangıçta sıfırlanmalı VE bitişte kapatılmalı (`*store.lock().unwrap() = None`)"
    )


def test_ilerleme_yazicisi_KURULUMLA_ayni_kaynak(rs):
    """Ön-indirme, kurulumla AYNI snapshot yazıcısını kullanmalı (throttle + son-parça kuralı).

    ⚠️ Bu test önce `prefetch_runtime_update` gövdesinde `final_chunk` dizesini arıyordu ve
    mutasyon turunda ZAYIF çıktı: `!final_chunk &&` kaldırılınca bile `let final_chunk = ...`
    satırı durduğu için regex eşleşiyordu. Kural artık `snapshot_yazici`ya çıkarıldı ve
    DAVRANIŞSAL olarak `main.rs::tests::son_parca_throttle_a_TAKILMAZ` ile kilitleniyor.
    Burada yalnız "iki yol tek kaynağı paylaşıyor mu" doğrulanır — ayrışırsa biri düzeltilip
    diğeri unutulur.
    """
    govde = re.search(r"async fn prefetch_runtime_update\((.*?)\n}", rs, re.S).group(1)
    assert "snapshot_yazici(" in govde, (
        "ön-indirme ortak yazıcıyı kullanmıyor → throttle/son-parça kuralı kopyalanmış olabilir"
    )
    assert "fn snapshot_yazici" in rs, "ortak yazıcı tanımlı değil"
    # Kurulum yolu da aynı yazıcıyı kullanmalı ki iki akış ayrışmasın.
    rep = re.search(r"fn progress_reporter\((.*?)\n}", rs, re.S)
    assert rep and "snapshot_yazici(" in rep.group(1), "kurulum yolu ortak yazıcıyı kullanmıyor"


def test_get_prefetch_progress_komutu_KAYITLI(rs):
    """Komut tanımlansa da `invoke_handler`a eklenmezse UI `invoke` çağrısı hata verir."""
    assert "fn get_prefetch_progress" in rs, "komut tanımlı değil"
    handler = re.search(r"invoke_handler\(tauri::generate_handler!\[(.*?)\]\)", rs, re.S)
    assert handler, "invoke_handler bloğu bulunamadı"
    assert "get_prefetch_progress" in handler.group(1), (
        "komut `invoke_handler`a KAYITLI DEĞİL → UI'da 'command not found' olur, bar hiç çizilmez."
    )


# ─────────────────────────────────────────────────────────────────────────────
# UI: yüzde çiziliyor ve ekran ele geçirilmiyor mu?
# ─────────────────────────────────────────────────────────────────────────────


def test_UI_arka_plan_ilerlemesini_yoklar(ui):
    assert "get_prefetch_progress" in ui, "UI ön-indirme ilerlemesini hiç yoklamıyor"
    assert "startPrefetchPoll()" in ui and "stopPrefetchPoll()" in ui


def test_KRITIK_arka_plan_indirmede_kurulum_EKRANI_ACILMAZ(ui):
    """🔴 Ön-indirmenin tek amacı kullanıcıyı BEKLETMEMEK.

    `show("s-install")` çağrılırsa ekran ele geçer ve "Başlat" kullanılamaz hâle gelir —
    2026-08-08 sahip kararının tam tersi.
    """
    m = re.search(r"if \(!plan\.cached\) \{(.*?)\n        \}", ui, re.S)
    assert m, "arka plan indirme dalı bulunamadı"
    dal = m.group(1)
    assert "startPrefetchPoll" in dal, "arka plan dalında yoklama başlatılmıyor"
    assert 's-install' not in dal, "arka plan dalı KURULUM EKRANINI açıyor — kullanıcıyı bekletir"
    assert "startPolling()" not in dal, "kurulum yoklaması (ekranı ele geçiren) başlatılıyor"


def test_yuzde_ve_bar_ciziliyor(ui):
    """Sahip isteğinin özü: yüzde + bar."""
    assert "bgpct" in ui and "bgbar" in ui, "yüzde/bar elemanları yok"
    assert re.search(r'pctEl\.textContent\s*=\s*has\s*\?\s*"%"', ui), "yüzde yazılmıyor"
    assert re.search(r'fill\.style\.width\s*=\s*has\s*\?', ui), "bar genişliği ayarlanmıyor"


def test_content_length_yoksa_BELIRSIZ_bar(ui):
    """`total=0` (sunucu boyut vermezse) sahte %0 göstermek yerine belirsiz bar olmalı."""
    assert 'bar.classList.toggle("indet", !has)' in ui, "belirsiz-bar durumu ele alınmamış"


def test_KRITIK_baslangicta_null_gelince_HEMEN_durmaz(ui):
    """🔴 Rust ilk snapshot'ı yazana kadar `null` döner.

    İlk `null`da durursak bar HİÇ görünmez — özelliğin tamamı sessizce ölür.
    """
    assert "prefetchSeen" in ui, "ilk-null koruması yok"
    assert re.search(r"if \(prefetchSeen\) \{ stopPrefetchPoll\(\)", ui), (
        "en az bir ilerleme görülmeden durdurma yapılıyor → bar hiç çizilmez"
    )


def test_hic_ilerleme_gelmezse_yoklama_SONSUZ_donmez(ui):
    """Her şey önbellekteyse ilerleme hiç gelmeyebilir; zamanlayıcı sızmamalı."""
    assert re.search(r"Date\.now\(\) - basladi > \d+", ui), "zaman aşımı koruması yok"


def test_bitis_ve_hata_yollarinda_yoklama_DURUR(ui):
    """Zamanlayıcı sızarsa arka planda sonsuza dek `invoke` çağrılır."""
    # Çağrının hem `.then` hem `.catch` dalında durdurma OLMALI. (Kod şekli değişebilir —
    # `(r) => {}` vs `() => {}` — bu yüzden dalların İÇİNE bakıyoruz, imzaya değil.)
    m = re.search(r'invoke\("prefetch_runtime_update".*?\n\s*\.catch\((.*?)\}\)', ui, re.S)
    assert m, "ön-indirme çağrısı bulunamadı"
    cagri = m.group(0)
    then_dali = re.search(r"\.then\((.*?)\)\n\s*\.catch", cagri, re.S)
    assert then_dali and "stopPrefetchPoll()" in then_dali.group(1), "başarı yolunda durmuyor"
    assert "stopPrefetchPoll()" in m.group(1), "hata yolunda durmuyor"
    # Not kapatılınca da durmalı: kullanıcı notu kapattıysa arka planda yoklama sürmemeli.
    clear_nt = re.search(r"function clearNotice\(\)[^\n]*", ui)
    assert clear_nt and "stopPrefetchPoll()" in clear_nt.group(0), (
        "clearNotice yoklamayı durdurmuyor → zamanlayıcı sızar"
    )


def test_KRITIK_basarisiz_on_indirme_BASARILI_denmez(rs, ui):
    """🔴 Komut HATA'da da `Ok({status:"failed"})` döner → `.then()` her iki durumda çalışır.

    Sonucu okumadan "yeni sürüm indirildi, sonraki açılışta kurulacak" demek kullanıcıya
    YALAN söyler: açılışta hiçbir şey olmaz ve sebep hiçbir yerde görünmez. (Bu hata bar
    eklenirken gerçekten oluştu ve denetimde yakalandı.)
    """
    # Ön koşul: komut gerçekten reject ETMİYOR — test bu varsayıma dayanıyor.
    govde = re.search(r"async fn prefetch_runtime_update\((.*?)\n}", rs, re.S).group(1)
    assert 'json!({ "status": "failed"' in govde, (
        "komut artık hata döndürüyor olabilir — bu testin dayandığı varsayım değişmiş, gözden geçir"
    )
    m = re.search(r'invoke\("prefetch_runtime_update".*?\n\s*\.catch', ui, re.S)
    assert m, "ön-indirme çağrısı bulunamadı"
    blok = m.group(0)
    assert "status" in blok and "prefetched" in blok, (
        "başarı `status` alanına BAKILMADAN ilan ediliyor → başarısız indirmede 'indirildi' denir"
    )
    assert "rtBgFail" in blok, "başarısızlık için ayrı mesaj yok"


def test_basarisizlik_mesaji_iki_dilde(ui):
    assert ui.count("rtBgFail:") == 2, "rtBgFail iki dilde de tanımlı olmalı"


def test_i18n_iki_dilde_de_TAM(ui):
    """Eksik anahtar `undefined` basar — kullanıcı boş metin görür."""
    for anahtar in ("rtBgDone", "rtBgPrep"):
        assert ui.count(f"{anahtar}:") == 2, (
            f"`{anahtar}` iki dilde de tanımlı olmalı (bulunan: {ui.count(f'{anahtar}:')})"
        )
