# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""ARAŞTIRMA AI PRO ARAYÜZ SÖZLEŞMESİ (Faz 3, 2026-09-09).

Sahip isteği: "araştırma modunda AI Pro'ya fantom ve petriyi KEDİ YERİNE entegre et; em kedi vet
modundaki AI Pro'da olacak." Karar #13: gizleme SİMETRİK — kedi araştırmacıda, fantom/petri
veterinerde HİÇ görünmez.

BU KAPI NE ÖLÇER (jest'in ölçmediklerini):
  1. Profil ↔ model tablosunun TEK KAYNAK olduğu ve araştırmacı listesinde "kedi" GEÇMEDİĞİ.
     (Jest testi `secilebilirModeller`i doğrudan geçer → tablo bozulsa bile yeşil kalır.)
  2. Panelin modeli GERÇEKTEN taşıdığı uçların TAM listesi: model MÜHÜRE yazılan uçta (`propose`)
     ve hedefi/modeli set eden uçlarda (`hazirlik/baslat`, `organ`) bulunmalı; `/ai/pro/start`
     gövdesinde BULUNMAMALI (model onay MÜHRÜNDEN okunur — "fantom önerisini onaylat, kediyi
     başlat" yapısal olarak imkânsız kalmalı).
  3. Kullanıcıya gösterilen metinlerde ham teknik terim geçmediği (eylem söyleyen hata kuralı).
  4. Backend hedef adaylarının kare-oranlı `pxn` ürettiği — halkaların ham piksele dönmesi
     işaretleri hedeften kaydırırdı (WS önizlemesi kareyi 960 px'e küçültür).

⚠️ `pf/` bu depoda izlenmez (.gitignore) → kaynak yoksa ATLA (capraz kuralı).
"""

import ast
import pathlib
import re

import capraz

_KOK = pathlib.Path(__file__).resolve().parents[1]
_PROFIL = "pf/src/components/domain/aiProProfilleri.ts"
_PANEL = "pf/src/components/domain/AiProPanel.tsx"
_KARTLAR = "pf/src/components/domain/aipro/ModelSecimKartlari.tsx"
_HEDEF = "pf/src/components/domain/aipro/HedefSecici.tsx"
_ROZET = "pf/src/components/domain/aipro/KalibrasyonRozeti.tsx"


def _oku(gorece: str) -> str:
    capraz.atla_yoksa(gorece)
    return capraz.kaynak_yolu(gorece).read_text(encoding="utf-8")


def _tablo_bloklari(src: str) -> "dict[str, str]":
    """`MODELLER_PROFILE_GORE = { profil: [...] }` bloğunu profil→liste metnine çevirir."""
    m = re.search(r"MODELLER_PROFILE_GORE[^=]*=\s*\{(.*?)\n\};", src, re.S)
    assert m, "MODELLER_PROFILE_GORE tablosu bulunamadı (adı mı değişti?)"
    govde = m.group(1)
    return {k: v for k, v in re.findall(r"^\s*(\w+):\s*\[([^\]]*)\]", govde, re.M)}


def test_KRITIK_arastirmaci_listesinde_KEDI_YOK():
    """Araştırmacıya kedi modelini açmak sahip kararının tersine dönmesidir (karar #13)."""
    tablo = _tablo_bloklari(_oku(_PROFIL))
    assert "researcher" in tablo, f"araştırmacı profili tabloda yok: {sorted(tablo)}"
    assert "kedi" not in tablo["researcher"], (
        f"araştırmacı listesinde kedi VAR: {tablo['researcher']!r} — sahip kararı #13 (simetrik gizleme) ihlali"
    )
    for beklenen in ("fantom", "petri"):
        assert beklenen in tablo["researcher"], f"araştırmacı listesinde {beklenen} yok"


def test_KRITIK_veteriner_listesinde_FANTOM_PETRI_YOK():
    """Simetri: veterinere araştırma modeli açmak, klinik ekrana araştırma dozu sokardı."""
    tablo = _tablo_bloklari(_oku(_PROFIL))
    assert "veterinarian" in tablo, f"veteriner profili tabloda yok: {sorted(tablo)}"
    for yasak in ("fantom", "petri"):
        assert yasak not in tablo["veterinarian"], (
            f"veteriner listesinde {yasak} VAR: {tablo['veterinarian']!r} — simetrik gizleme ihlali"
        )
    assert "kedi" in tablo["veterinarian"], "veterinerde kedi kalmamış (klinik akış kırılır)"


def test_KRITIK_pet_owner_AI_PRO_GORMEZ():
    """Evcil hayvan sahibi YALNIZ ANALİZ yapar (sahip kararı) — otonom hedef modeli yok."""
    tablo = _tablo_bloklari(_oku(_PROFIL))
    assert tablo.get("pet_owner", "x").strip() == "", (
        f"pet_owner listesi boş değil: {tablo.get('pet_owner')!r} — analiz-only kararı ihlali"
    )


def test_KRITIK_TEK_KAYNAK_profil_model_eslemesi_baska_yerde_TEKRARLANMAZ():
    """İkinci bir eşleme tablosu, birinin sessizce ayrışmasına açık kapı bırakır."""
    capraz.atla_yoksa(_PANEL)
    kok = capraz.kaynak_yolu("pf/src")
    kaynaklar = [p for p in kok.rglob("*.ts*") if "__tests__" not in p.parts]
    tanim = [
        p.relative_to(kok).as_posix()
        for p in kaynaklar
        if re.search(r"MODELLER_PROFILE_GORE\s*[:=]", p.read_text(encoding="utf-8"))
    ]
    assert tanim == ["components/domain/aiProProfilleri.ts"], f"tablo birden fazla yerde tanımlı: {tanim}"
    # İkinci eşleme: bir PROFİL adı ile AI Pro model KİMLİĞİ ("fantom"/"petri") aynı satırda.
    # ⚠️ `em_fantom`/`em_petri` HARİÇ tutulur: onlar AI Hub'ın ANALİZ modül envanteridir (ayrı
    # kavram, ayrı liste). İlk yazımda bu ayrımı yapmayan kapı yanlış-pozitif verdi.
    model_kimligi = re.compile(r'(?<![\w])"(fantom|petri)"')
    profil_adi = re.compile(r"\b(researcher|veterinarian|pet_owner)\b")
    kopya = []
    for p in kaynaklar:
        if p.relative_to(kok).as_posix() == "components/domain/aiProProfilleri.ts":
            continue
        for satir in p.read_text(encoding="utf-8").splitlines():
            if satir.strip().startswith(("*", "//", "/*")):
                continue  # yorumda modelden bahsetmek eşleme DEĞİL
            if profil_adi.search(satir) and model_kimligi.search(satir):
                kopya.append(f"{p.relative_to(kok).as_posix()}: {satir.strip()[:80]}")
    assert not kopya, "profil-model eşlemesi başka dosyada TEKRARLANMIŞ:\n" + "\n".join(kopya)


def _istek_govdeleri(panel: str) -> "dict[str, list[str]]":
    """`apiPost(<yol>, <gövde>, ...)` çağrılarını yol→gövde metinleri sözlüğüne çevirir."""
    sonuc: dict[str, list[str]] = {}
    for m in re.finditer(r'apiPost<[^>]*>\(\s*"([^"]+)"\s*,\s*(\{.*?\})\s*,', panel, re.S):
        sonuc.setdefault(m.group(1), []).append(m.group(2))
    # Yolu ayrı satıra yazılmış çağrılar.
    for m in re.finditer(r'apiPost<[^>]*>\(\s*\n\s*"([^"]+)"\s*,\s*\n?\s*(\{.*?\n?\s*\})\s*,', panel, re.S):
        sonuc.setdefault(m.group(1), []).append(m.group(2))
    return sonuc


def test_KRITIK_model_MUHURLENEN_ve_HEDEF_SETLEYEN_uclarda_TASINIR():
    """Model gövdeden gitmezse backend onu "kedi" sayar → araştırmacı SESSİZCE kedi hattını açardı."""
    panel = _oku(_PANEL)
    govdeler = _istek_govdeleri(panel)
    for yol in ("/ai/pro/hazirlik/baslat", "/ai/pro/propose", "/ai/pro/organ"):
        assert yol in govdeler, f"{yol} çağrısı panelde bulunamadı (yol mu değişti?)"
        for g in govdeler[yol]:
            assert "model:" in g, f"{yol} gövdesi modeli TAŞIMIYOR: {g[:120]!r}"
            # State DEĞİL REF: öneri efektinin bağımlılık dizisi kaynak-regex kapısıdır
            # (tests/test_ai_pro_asamali_akis.py) — modeli o diziye sokmak kapıyı kırardı.
            assert "hedefModeliRef.current" in g, f"{yol} gövdesi modeli state'ten okuyor: {g[:120]!r}"


def test_KRITIK_START_govdesi_modeli_TASIMAZ_model_MUHURDEN_okunur():
    """⚠️ "Fantom önerisini onaylat, kediyi başlat" yapısal olarak imkânsız kalmalı: `/start`
    modeli gövdeden OKUMAZ (organ/süre ile AYNI ilke, 2026-08-06 mühür kararı). Panelin oraya
    model göndermesi, ilkenin gövdeden yönetilebildiği izlenimini verir."""
    panel = _oku(_PANEL)
    cagrilar = _istek_govdeleri(panel).get("/ai/pro/start", [])
    assert cagrilar, "/ai/pro/start çağrısı bulunamadı (yol mu değişti?)"
    for g in cagrilar:
        assert "model" not in g, f"/ai/pro/start gövdesine model konmuş: {g[:120]!r} — model MÜHÜRDEN okunur"


#: Kullanıcıya ASLA gösterilmeyecek ham teknik terimler (eylem söyleyen hata kuralı).
_YASAK_TERIM = ("VideoCapture", "Traceback", "aruco_pnp", "PEMF_ARASTIRMA_AIPRO", "onnx", "ImportError", "pxn")


def _kullanici_metinleri(src: str) -> "list[str]":
    """EKRANDA görünen parçalar: `<Text>` gövdeleri + a11y etiket/ipuçları.

    ⚠️ Dosyanın TAMAMINA bakmak yanlış-pozitif verir: `y === "aruco_pnp"` bir KARŞILAŞTIRMADIR,
    kullanıcı metni değil (ilk yazımda kapı tam bu yüzden sahte-kırmızı oldu)."""
    parcalar: list[str] = []
    parcalar += re.findall(r"<Text[^>]*>(.*?)</Text>", src, re.S)
    parcalar += re.findall(r"accessibilityLabel=\{?[\"`]([^\"`]*)", src)
    parcalar += re.findall(r"accessibilityHint=\{?[\"`]([^\"`]*)", src)
    return parcalar


def test_KRITIK_kullanici_metinlerinde_HAM_TEKNIK_terim_YOK():
    """Eylem söyleyen hata kuralı: ham teknik metin operatöre "yazılımda bug var" izlenimi verir."""
    for gorece in (_KARTLAR, _HEDEF, _ROZET):
        for parca in _kullanici_metinleri(_oku(gorece)):
            for terim in _YASAK_TERIM:
                assert not re.search(rf"\b{re.escape(terim)}\b", parca), (
                    f"{gorece} kullanıcı metninde ham teknik terim {terim!r}: {parca.strip()[:80]!r}"
                )


def test_KAPI_gercekten_olcuyor_yasakli_terim():
    """MUTASYON ÖZ-TESTİ: yasaklı terim bir `<Text>` gövdesine girse tarayıcı onu görür mü?"""
    sahte = "<Text style={s.m}>Konum ölçülemedi (aruco_pnp yok)</Text>"
    parcalar = _kullanici_metinleri(sahte)
    assert parcalar and any("aruco_pnp" in p for p in parcalar), "tarayıcı Text gövdesini görmüyor"


def test_KRITIK_halkalar_KARE_ORANLI_koordinat_kullanir():
    """Ham `px` WS'in KÜÇÜLTÜLMÜŞ karesiyle ölçeklenmez → işaretler hedeften kayar (S7 dersi)."""
    src = _oku(_HEDEF)
    m = re.search(r"left:\s*([^\n]+)", src)
    assert m, "halka konumu hesaplanmıyor"
    assert "pxn" in m.group(1), f"halka ham piksel kullanıyor: {m.group(1).strip()!r}"


def test_KRITIK_BACKEND_hedef_adaylarina_pxn_YAZAR():
    """Arayüz sözleşmesinin karşı yakası: sağlayıcı `pxn`i kare BOYUTUNA bölerek üretmeli."""
    src = (_KOK / "servers" / "ai_pro_hedef.py").read_text(encoding="utf-8")
    agac = ast.parse(src)
    fn = next((n for n in agac.body if isinstance(n, ast.FunctionDef) and n.name == "_hedef_tel"), None)
    assert fn is not None, "_hedef_tel yardımcısı yok — targets `pxn` taşımıyor demektir"
    govde = ast.get_source_segment(src, fn) or ""
    assert '"pxn"' in govde and "kare_w" in govde and "kare_h" in govde, "pxn kare boyutuna bölünerek üretilmiyor"
    # Ve GERÇEKTEN kullanılıyor mu (varlık değil UYGULAMA): targets listesi bu yardımcıdan kurulmalı.
    assert re.search(r'"targets":\s*\[_hedef_tel\(', src), "targets listesi _hedef_tel ile kurulmuyor"
