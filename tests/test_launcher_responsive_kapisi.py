# Author: mertaygn, cglrgrkn
"""BAŞLATICI YERLEŞİM/ERİŞİLEBİLİRLİK KAPISI  [L, 2026-09-04 responsive denetimi].

ÖLÇÜLEN DURUM (headless Edge + CDP ile, `scripts/responsive_kapisi.py`):
  · 700×540'lık ASGARİ pencerede `login`, `select`, `ready` ve `error` ekranlarının başlığı üst
    şeridin ALTINDA kalıyordu (ilk içerik üstü 13-56 px < header altı 75 px) ve KAYDIRMAYLA DA
    ULAŞILAMIYORDU: `main { justify-content: center }` taşan içeriği iki uçtan birden kırpar.
  · `@media (max-width: 680px)` bloğu ÖLÜYDÜ — pencere asgari genişliği 700 px.
  · Profil kartları `<div>` idi: klavyeyle seçilemiyordu.
  · Modallar yalnız `hidden` ile açılıyordu: Tab arka plandaki "Kur ve Başlat"a gidiyordu.
  · Üst şerit ikon düğmelerinin etiketi dar pencerede gizleniyor ama kalıcı bir erişilebilir ad
    (title/aria-label) YOKTU.

⚠️ Bu kapı yorum-soyulmuş metinde çalışır (yorumlar sözleşmenin KENDİSİNİ içerir; ham metinde
arama yapan kapılar bu yüzden yanlış-yeşil/yanlış-kırmızı verir — S6/S7 kapılarında ölçüldü).
"""

import json
import pathlib
import re

import pytest

_KOK = pathlib.Path(__file__).resolve().parents[1]
_UI = _KOK / "launcher" / "app" / "ui" / "index.html"
_CONF = _KOK / "launcher" / "app" / "tauri.conf.json"
_RS = _KOK / "launcher" / "app" / "src" / "main.rs"

pytestmark = pytest.mark.skipif(not _UI.exists(), reason="launcher/ kaynak ağacı yok — kapı atlanır")


def _soy(metin: str) -> str:
    """HTML ve JS/CSS yorumlarını çıkar (sözleşme metni yorumlarda geçiyor)."""
    metin = re.sub(r"<!--.*?-->", " ", metin, flags=re.DOTALL)
    metin = re.sub(r"/\*.*?\*/", " ", metin, flags=re.DOTALL)
    metin = re.sub(r"^\s*//.*$", "", metin, flags=re.MULTILINE)
    return metin


def _ui() -> str:
    return _soy(_UI.read_text(encoding="utf-8"))


def test_KRITIK_dikey_tasma_icerigi_kirpmiyor():
    """`center` taşan içeriği İKİ UÇTAN kırpar; `flex-start` + `margin: auto 0` kırpmaz."""
    ui = _ui()
    m = re.search(r"\bmain\s*\{[^}]*\}", ui)
    assert m, "main kuralı bulunamadı (CSS yeniden yazıldıysa kapı güncellenmeli)"
    assert "justify-content: flex-start" in m.group(0), (
        "main hâlâ dikey ortalıyor: 700×540'ta başlık üst şeridin altında kalır ve kaydırmayla da ulaşılamaz."
    )
    st = re.search(r"\.stage\s*\{[^}]*\}", ui)
    assert st and "margin: auto 0" in st.group(0), (
        ".stage `margin: auto 0` taşımıyor: içerik sığdığında dikey ortalama kaybolur."
    )


def test_olu_medya_sorgusu_yok_kisa_pencere_sorgusu_var():
    ui = _ui()
    # ⚠️ Ölçüt MEDYA SORGUSU, ham metin değil: "@media (min-width: 1600px)" bloğu içindeki
    # ".stage { max-width: 680px }" MEŞRU (geniş ekranda sahne genişler) ve kapının ilk sürümü
    # onu ihlal saymıştı.
    assert "@media (max-width: 680px)" not in ui, "ölü kural geri gelmiş (pencere asgari genişliği 700)"
    assert "max-height: 620px" in ui, "kısa pencere (1366@%150 → 480 px) sorgusu yok"
    assert "pointer: coarse" in ui, "dokunmatik (Surface) taban kuralı yok"


def test_KRITIK_ikon_dugmelerin_kalici_erisilebilir_adi_var():
    """Etiket <span>'i dar pencerede gizleniyor → title/aria-label KALICI ad olmalı."""
    ui = _ui()
    for dugme in ("btn-web", "btn-guide", "btn-about", "btn-logout"):
        m = re.search(rf'<button[^>]*id="{dugme}"[^>]*>', ui)
        assert m, f"{dugme} bulunamadı"
        assert "aria-label" in m.group(0) and "title=" in m.group(0), (
            f"{dugme} kalıcı erişilebilir ad taşımıyor (etiketi dar pencerede gizleniyor)"
        )


def test_KRITIK_profil_kartlari_klavyeyle_secilebilir():
    ui = _ui()
    # ⚠️ Çıpa KART DEĞİŞKENİNE pinli: dosyada başka `createElement("button")` çağrıları da var,
    # genel arama kartın <div>'e geri dönmesini YAKALAMIYORDU (mutasyonla ölçüldü).
    assert 'const card = document.createElement("button")' in ui, (
        "profil kartı <button> değil (Tab ile seçilemez, Enter/Space çalışmaz)"
    )
    assert 'setAttribute("aria-pressed"' in ui, "seçili durum ekran okuyucuya bildirilmiyor"


def test_KRITIK_modal_arka_plani_etkisizlestiriyor_ve_geri_aciyor():
    """`inert` kaldırılmazsa Başlat/E-stop'a giden TÜM yol klavyeden kilitlenir."""
    ui = _ui()
    assert "inert = true" in ui and "inert = false" in ui, "modal odak yönetimi yok"
    kapat = re.search(r"function closeModal\([^)]*\)\s*\{[^}]*\}", ui, re.DOTALL)
    assert kapat and "inert = false" in kapat.group(0), (
        "closeModal inert'i KOŞULSUZ kaldırmıyor — arka plan klavyeden kalıcı kilitlenir."
    )
    assert 'e.key === "Escape"' in ui, "Escape ile kapatma yok"


def test_pencere_asgari_boyutu_kisa_ekranda_kucultmeye_izin_veriyor():
    conf = json.loads(_CONF.read_text(encoding="utf-8"))
    w = conf["app"]["windows"][0]
    assert w["minHeight"] <= 460, (
        f"asgari yükseklik {w['minHeight']}: 1366×768 @%150 çalışma alanı 480 px, kullanıcı pencereyi küçültemez."
    )
    assert w.get("visible") is False, "pencere ilk karede görünür: boyutlandırma sonrası show() ile zıplama önlenir."


def test_KRITIK_pencere_boyutu_monitore_gore_kirpiliyor():
    """Saf fonksiyon `cargo test` ile ölçülür; burada BAĞLANTI kilitlenir."""
    rs = _RS.read_text(encoding="utf-8")
    assert "fn ana_pencere_boyutu(" in rs and "fn uygulama_pencere_boyutu(" in rs
    assert "ana_pencere_boyutu(" in rs.split("fn ana_pencere_boyutu(", 1)[1], (
        "saf fonksiyon tanımlı ama KULLANILMIYOR (setup'ta çağrı yok)"
    )
    assert "min_inner_size(" in rs, "app penceresi asgari boyut vermiyor (matris-9)"
