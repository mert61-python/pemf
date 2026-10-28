# -*- coding: utf-8 -*-
"""SON-A2.51 (22 · D6.71 "YAŞAYAN MUTANT → 22") — depo genelinde ÇİZGİSİZ CANLI güvenlik iddiası taraması.

D6.71'in dar kapısı yalnız bilinen cümleleri pinliyordu: README'ye çizgisiz "Backend'de 48 °C sınırı korunur" ekleyen mutant
dar kapı + D6.04 + README kapısından GEÇİYORDU. Bu kapı izlenen HER metin dosyasını tarar ve sahip kararlarıyla çelişen
OLUMLU iddiayı (var / korunur / kalır / birebir / devrede …) yakalar:
  K1  "48 °C" + backend / sunucu / arayüz / istemci / STM öznesi (A-47 · Y9: bu katmanların HİÇBİRİNDE 48 °C sınırı yok)
  K2  "termal koruma / termal kesme / sıcaklık kesmesi / termal interlock" + varlık fiili (A-47; ESP'nin kendi yerel kesmesi
      Y40 gereği ESP firmware dizinlerinde anlatılabilir — orada yalnız backend / STM / arayüz öznesiyle birleşen iddia yasak)
  K3  "ISO 13485" olumlu (uyumlu / sertifikalı / standardına göre) iddiası
  K4  site / tanıtım yüzeyinde (apps/web, website, DEMA) "otonom biofeedback" iddiası
İZİNLİ BAĞLAM (KARŞIT — yeşil kalmalı): üstü çizili `~~…~~` / `<s>` / `<del>` metin · "TARİHÇE" geçen paragraf · cümlede olumsuzluk
(YOK / değil / KALDIRILDI / EKLENMEZ / YAPILMAYACAK / UYGULANMAZ / ⛔ …) ya da "yalnız görsel uyarı" · dosya düzeyinde tarihçe
(CHANGELOG, docs/arsiv, docs/README "TARİHLİ KAYIT" tablosu, ilk 40 satırda "> … TARİHÇE" bandı) · testler · i18n meta listeleri ·
iddia denetleyicisinin kendisi.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]

METIN_UZANTI = {
    ".md",
    ".txt",
    ".py",
    ".ts",
    ".tsx",
    ".js",
    ".mjs",
    ".cjs",
    ".json",
    ".c",
    ".h",
    ".cpp",
    ".hpp",
    ".ino",
    ".ps1",
    ".psm1",
    ".iss",
    ".nsi",
    ".nsh",
    ".rs",
    ".html",
    ".env",
    ".yml",
    ".yaml",
    ".toml",
    ".spec",
    ".sql",
    ".cfg",
    ".ini",
    ".sh",
    ".bat",
    ".cmd",
    ".rst",
}

T48 = r"48\s*°?\s*C\b"
OZNE = r"(backend|back-end|sunucu|server|arayüz|arayuz|istemci|client|frontend|STM\s*32|STM\b|STM'|bobin\s*1\s*[-–]\s*[57])"
VARLIK = (
    r"(korunur|korunuyor|korunmaktadır|uygulanır|uygulanıyor|uyguluyor|devrede|aktif|çalışır|calisir|kalır|KALIR|kaldı|KALDI|"
    r"birebir|BİREBİR|politika|değişmez|degismez|var\b|vardır|VAR\b|mevcut|gömülü|sağlar|sağlanır|durdurur|keser|engeller)"
)
KORUMA_ADI = r"(termal\s+(koruma|kesme|interlock|kilit)|sıcaklık\s+(koruması|kesmesi|kesme|interlock)|aşırı[- ]ısınma\s+(koruması|kesmesi|interlock))"
OLUMSUZ = (
    r"(\byok\b|\bYOK\b|\bYok\b|yoktur|YOKTUR|\byoktu\b|değil|DEĞİL|degil|[Kk]aldırıl|KALDIRIL|[Kk]aldirildi|KALDIRILDI|"
    r"[Kk]aldırdı|KALDIRDI|[Kk]aldirdi|"
    r"[Ee]klenmez|EKLENMEZ|[Ee]klenmeyecek|EKLENMEYECEK|GERİ EKLEME|[Gg]eri ekleme|yapılmaz|YAPILMAZ|yapılmayacak|YAPILMAYACAK|"
    r"uygulanmaz|UYGULANMAZ|istemedi|İSTEMEDİ|ilgisi yok|İLGİSİ YOK|ILGISI YOK|⛔|❌|tetiklenemez|bulunmaz|olmayan|"
    r"yalnız\s+görsel|YALNIZ\s+(görsel|GÖRSEL)|yalniz\s+gorsel|GÖRSEL uyarı|GORSEL uyari|görsel uyarı|iddia|İDDİA|yasak|YASAK|"
    r"silindi|SİLİNDİ|"
    # tarihçe anlatımı / alıntı: "bu yorum eskiden … diyordu"
    r"[Ee]skiden|ESKİDEN|[Öö]nceden|ÖNCEDEN|diyordu|DİYORDU|yazıyordu|YAZIYORDU)"
)
#: ESP firmware'inin KENDİ yerel kesmesi (Y40: 8266 100 °C kalır; S3 kodu uykuda) ESP bağlamında anlatılabilir
ESP_BAGLAMI = r"(\bESP|\bS3\b|8266|CoilController|esps3|esp8266|bobin\s*8\b)"
ISO_OLUMLU = r"ISO\s*13485[^.;|\n]{0,40}(uyumlu|sertifika|onaylı|standardına|belgeli|compliant|certified)|(uyumlu|sertifikalı|compliant|certified)[^.;|\n]{0,25}ISO\s*13485"
SITE_KOKLERI = ("apps/web/", "website/", "dema-terapi-simülatörü/")
ESP_KOKLERI = ("firmware/esp8266_pemf_coil/", "firmware/esps3_pemf_coil/")
OZNE_ESP_DISI = r"(backend|back-end|sunucu|server|arayüz|arayuz|istemci|frontend|STM\s*32|STM\b|STM')"

SATICI_KOKLERI = ("firmware/stm32_pemf/Drivers/", "training_archive/", "bin/")
DOSYA_MUAF = {
    "CHANGELOG.md": "sürüm tarihçesi",
    "i18n/kapsam.json": "i18n meta (katalog/kaynak dizgelerinin aynası — kaynakları ayrıca taranır)",
    "i18n/kritik-anahtarlar.json": "i18n meta",
    "build_tools/dema_iddia_denetimi.py": "iddia denetleyicisinin kendisi (yasak deseni tanımlar)",
    "build_tools/PEMF_Backend_onedir.spec": "denetleyiciyi çağıran derleme adımı yorumu",
}


def _tarihli_kayit_dosyalari() -> set[str]:
    """docs/README.md "TARİHLİ KAYIT" bölümünde listelenen belgeler (o günün ölçümü — bugünün kaynağı değil)."""
    yol = KOK / "docs" / "README.md"
    if not yol.exists():
        return set()
    metin = yol.read_text(encoding="utf-8")
    m = re.search(r"^##[^\n]*TARİHLİ KAYIT[^\n]*\n(.*?)(?=^## )", metin, re.S | re.M)
    if not m:
        return set()
    return {"docs/" + h for h in re.findall(r"\]\(([^)#]+\.md)\)", m.group(1)) if "/" not in h}


def dosya_muaf(rel: str, metin: str, tarihli: set[str]) -> str | None:
    if rel.startswith("tests/") or "/__tests__/" in rel or re.search(r"\.(test|spec)\.[cm]?[jt]sx?$", rel):
        return "test"
    if rel in DOSYA_MUAF:
        return DOSYA_MUAF[rel]
    if rel.endswith("/CHANGELOG.md"):
        return "sürüm tarihçesi"
    if rel.startswith("docs/arsiv/"):
        return "arşiv"
    if rel in tarihli:
        return "docs/README TARİHLİ KAYIT"
    ilk = "\n".join(metin.splitlines()[:40])
    if re.search(r"^\s*>.*TARİHÇE", ilk, re.M):
        return "belge-geneli TARİHÇE bandı"
    return None


def _cizgileri_sil(metin: str) -> str:
    # çizili parça silinir ama SATIR SAYISI korunur (bulgu satır numarası kaymasın)
    def bos(m):
        return " " + "\n" * m.group(0).count("\n")

    metin = re.sub(r"~~[^~]{1,3000}?~~", bos, metin, flags=re.S)
    return re.sub(r"<(s|del|strike)\b[^>]*>.*?</\1>", bos, metin, flags=re.S | re.I)


#: cümle sınırı: nokta/ünlem/soru + boşluk · tablo hücresi `|` · yeni madde imi (Markdown `-`/`+`/`1.` ya da `* ` + harf)
CUMLE_SINIRI = r"(?<=[.!?])\s+|[|;]|\n(?=[ \t]*(?:[-+]|\d+[.)])[ \t])"


SATIR_UZANTI = {".json", ".env", ".yml", ".yaml", ".toml", ".cfg", ".ini"}


def _cumleler(metin: str, kod: bool = False):
    """(satır_no, cümle) — paragraf (boş satırla ayrılır) içinde CUMLE_SINIRI ile bölünür; satır sonu birleşir ( `;` BÖLMEZ:
    "X; termal kesme YOK" aynı cümlede olumsuzlanır). "TARİHÇE" geçen paragraf atlanır."""
    satir = 1
    for par in re.split(r"(\n[ \t]*(?://|#|\*|--|;)?[ \t]*\n)", metin):
        if re.fullmatch(r"\n[ \t]*(?://|#|\*|--|;)?[ \t]*\n", par or ""):
            satir += par.count("\n")
            continue
        bas = satir
        satir += par.count("\n")
        if "TARİHÇE" in par or "TARIHCE" in par:
            continue
        konum, no = 0, bas
        for m in re.finditer(CUMLE_SINIRI + (r"|\n" if kod else ""), par + "\n\n"):
            parca = par[konum : m.start()]
            if parca.strip():
                bas_bosluk = parca[: len(parca) - len(parca.lstrip())]
                yield no + bas_bosluk.count("\n"), re.sub(r"\s+", " ", parca).strip()
            no += par.count("\n", konum, m.end()) if m.end() <= len(par) else par.count("\n", konum)
            konum = m.end()
            if konum >= len(par):
                break


def _yakin(a: str, b: str, c: str, uzaklik: int = 60) -> bool:
    """İki desen aynı cümlede ve birbirine ≤ uzaklik karakter yakın (uzun kod parçalarında ilgisiz eşleşme sayılmasın)."""
    return bool(re.search(f"{a}.{{0,{uzaklik}}}{b}|{b}.{{0,{uzaklik}}}{a}", c, re.I))


def iddialar(rel: str, metin: str) -> list[tuple[int, str, str]]:
    """Dosyadaki çizgisiz OLUMLU yasak iddialar: (satır, kural, cümle)."""
    bulgu = []
    esp = rel.startswith(ESP_KOKLERI)
    site = rel.startswith(SITE_KOKLERI)
    kod = Path(rel).suffix.lower() in SATIR_UZANTI  # satır-tabanlı biçimlerde (katalog JSON, env, yml) her satır ayrı
    # CRLF → LF: aksi hâlde "\r\n\r\n" boş satırı paragraf sınırı sayılmaz → dosya TEK paragraf olur ve tek bir "TARİHÇE"
    # sözcüğü bütün dosyayı atlatır (aparat körlüğü — CRLF belgelerde ölçüldü)
    metin = metin.replace("\r\n", "\n")
    for no, c in _cumleler(_cizgileri_sil(metin), kod):
        # soru cümlesi iddia değildir ("48 °C'yi aşıyor mu?") · olumsuz / tarihçe / görsel-uyarı bağlamı izinli
        olumsuz = re.search(OLUMSUZ, c) or c.rstrip("*_`) ").endswith("?")
        ozne = OZNE_ESP_DISI if esp else OZNE
        # varlık fiili YA DA koruma adı ("Backend safety-limit'leri (freq/duty/48°C) bundan bağımsızdır" — varlığı varsayar)
        if (
            _yakin(T48, ozne, c)
            and re.search(VARLIK + r"|sınır|limit|safety|güvenlik|interlock|durdurma", c, re.I)
            and not olumsuz
        ):
            bulgu.append((no, "K1 48 °C + backend/arayüz/STM öznesi", c[:220]))
            continue
        if re.search(KORUMA_ADI, c, re.I) and re.search(VARLIK, c) and not olumsuz:
            yabanci_ozne = _yakin(KORUMA_ADI, OZNE_ESP_DISI, c)
            esp_kendi = esp or (re.search(ESP_BAGLAMI, c) and not yabanci_ozne)
            if not esp_kendi or yabanci_ozne:
                bulgu.append((no, "K2 termal koruma / kesme VAR", c[:220]))
                continue
        if re.search(ISO_OLUMLU, c, re.I) and not olumsuz:
            bulgu.append((no, "K3 ISO 13485 olumlu", c[:220]))
            continue
        if site and re.search(r"otonom\s+biofeedback|autonomous\s+biofeedback", c, re.I) and not olumsuz:
            bulgu.append((no, "K4 sitede otonom biofeedback", c[:220]))
    return bulgu


def _izlenen() -> list[str]:
    cikti = subprocess.run(
        ["git", "-c", "core.quotepath=false", "ls-files", "-z"], cwd=KOK, capture_output=True, check=True
    ).stdout
    return [p for p in cikti.decode("utf-8").split("\0") if p and Path(p).suffix.lower() in METIN_UZANTI]


def depo_taramasi() -> tuple[list[str], int]:
    tarihli = _tarihli_kayit_dosyalari()
    bulunan, taranan = [], 0
    for rel in _izlenen():
        yol = KOK / rel
        if rel.startswith(SATICI_KOKLERI) or rel.endswith("package-lock.json"):
            continue  # üçüncü taraf / eğitim verisi (ürün iddiası taşımaz)
        try:
            if yol.stat().st_size > 2_000_000:
                continue
            metin = yol.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        if dosya_muaf(rel, metin, tarihli):
            continue
        taranan += 1
        for no, kural, c in iddialar(rel, metin):
            bulunan.append(f"{rel}:{no}: [{kural}] {c}")
    return bulunan, taranan


# ── KARŞIT + POZİTİF birim örnekleri (sınıflandırıcının kendisi) ─────────────────────────────────────────────
@pytest.mark.parametrize(
    "metin",
    [
        "- Backend'de 48 °C sınırı korunur.",  # D6.71 yaşayan mutantı
        "Backend'in 48°C politikası sunucuda KALIR; bu, ağ koptuğunda son savunma hattıdır.",
        "YEREL TERMAL KORUMA — backend 48°C değişmeziyle birebir; ağ koptuğunda.",
        "S3 ve STM32 48 °C'de KALDI.",
        "Yerel acil-durdurma + termal koruma zaten cihazda gömülü mosquitto ile çalışır.",
        "Cihaz ISO 13485 uyumlu üretilir.",
    ],
)
def test_siniflandirici_CANLI_iddiayi_YAKALAR(metin):
    assert iddialar("README.md", metin), f"canlı iddia kaçtı: {metin!r}"


@pytest.mark.parametrize(
    "metin",
    [
        "~~Backend'de 48 °C sınırı korunur.~~ (A-47)",  # KARŞIT: çizili tarihçe
        "~~Yerel acil-durdurma + termal koruma zaten cihazda\ngömülü mosquitto ile çalışır.~~ ⚠️ **Termal koruma YOK** (A-47).",
        "> ⚠️ GÜNCELLEME — TARİHÇE: backend 48 °C sınırı korunur diye yazılmıştı.",
        "Backend'de tedavi duty tavanı ve 48 °C sınırı YOKTUR (Y9 · A-47 — geri EKLENMEZ).",
        "48 °C üstü yalnız görsel uyarıdır — seans otomatik durdurulmaz.",
        "arayüzdeki 48 °C GORSEL uyarisi buna bagimlidir.",
        "Termal kesme firmware'de YOK — senin kararındı.",
        "dayanaksız ISO 13485 iddiası yasak.",
    ],
)
def test_siniflandirici_IZINLI_BAGLAMI_gecirir(metin):
    assert not iddialar("README.md", metin), f"izinli bağlam yanlış yakalandı: {iddialar('README.md', metin)}"


def test_CRLF_belgede_TARIHCE_paragrafi_YALNIZ_kendini_atlatir():
    """Aparat körlüğü kolu: CRLF'li belgede boş satır paragraf sınırı sayılmazsa tek "TARİHÇE" bütün dosyayı atlatırdı."""
    metin = "> TARİHÇE: eski anlatım.\r\n\r\nGüncel:\r\n\r\n- Backend'de 48 °C sınırı korunur.\r\n"
    assert iddialar("docs/X.md", metin), "CRLF belgede TARİHÇE paragrafı sonraki paragraftaki canlı iddiayı da atlattı"


def test_esp_dizininde_KENDI_yerel_kesmesi_izinli_ama_backend_iddiasi_YASAK():
    assert not iddialar(
        "firmware/esps3_pemf_coil/README.md",
        "Termal: sensör 48 °C üstü → PWM durur; 45 °C altına inmeden start reddedilir.",
    )
    assert iddialar(
        "firmware/esps3_pemf_coil/CoilController.cpp",
        "Backend'in 48°C politikası sunucuda KALIR; bu son savunma hattıdır.",
    )


def test_site_yuzeyinde_otonom_biofeedback_iddiasi_YASAK():
    assert iddialar("apps/web/src/i18n/tr/icerik.json", '"x": "Otonom biofeedback ile seans kendini ayarlar"')
    assert not iddialar(
        "apps/ui/src/i18n/tr/ai.json", '"baslik": "Otonom Biofeedback"'
    )  # uygulama içi onaylı özellik adı (D1.88)


# ── depo taraması ─────────────────────────────────────────────────────────────────────────────────────
def test_depoda_CIZGISIZ_CANLI_guvenlik_iddiasi_YOK():
    bulunan, taranan = depo_taramasi()
    assert taranan >= 500, f"aparat: taranan dosya çok az ({taranan}) — git ls-files / uzantı süzgeci kör"
    assert not bulunan, (
        "çizgisiz CANLI güvenlik iddiası (A-47 · Y9 · A-37) — ~~çiz~~ + gerçeği yaz ya da cümleyi düzelt:\n  "
        + "\n  ".join(bulunan)
    )


def test_TARIHLI_KAYIT_listesi_okunuyor():
    tarihli = _tarihli_kayit_dosyalari()
    assert "docs/denetim-bulgular.md" in tarihli and len(tarihli) >= 5, (
        f"aparat: TARİHLİ KAYIT tablosu okunamadı ({sorted(tarihli)})"
    )
