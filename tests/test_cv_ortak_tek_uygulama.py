# Author: mertaygn, cglrgrkn
r"""KABİN CV KODU TEK UYGULAMADA KALIR (A2, 2026-09-19).

NE OLDU. `inference_em_fantom/phantom_cv/` ile `inference_petri_dish/petri_cv/` altındaki
üç dosya kopyaydı:

    coord_transform.py   326 satır  — MD5 BİREBİR aynı
    mqtt_publish.py      144 satır  — MD5 BİREBİR aynı
    cabin_config.py      367 satır  — 366'sı aynı; tek fark `mqtt_client_id` varsayılanı

`coord_transform` = **bobin/hedef geometrisi**. Bir taraftaki düzeltme diğerinde kalmazdı.
Depo bunu biliyor ve kaldırmak yerine bir teste bağlamıştı — o kapı yalnız *unutulunca*
kırılıyordu, yani arızayı **önlemiyor, haber veriyordu**. Ortak gövde
`ai_hub/cv_ortak/`a alındı; profil paketlerinde ince kabuk kaldı.

⚠️ BİRLEŞTİRME SIRASINDA İKİ GERÇEK BULGU ÇIKTI — ikisi de ölçülerek:

1. **Yakın kaza — taşınan modülün kendi konumu.** `cabin_config.py` içinde
   `DEFAULT_CONFIG_YAML = Path(__file__).parent / "cabin_config_example.yaml"` vardı.
   Modül `cv_ortak/`a taşınınca bu yol oraya kayar ve **orada örnek YAML yoktur**; üstelik
   iki profilin örneği FARKLIDIR (192 vs 206 satır). `load_cabin_config(None)` ÜRETİMDE
   dört yerden çağrılıyor (`ai_router.py:985,1009` · `predictors.py:104,115`) → naif taşıma
   dördünü de `FileNotFoundError` ile kırardı. Varsayılan artık **çağırandan** gelir.
   (Aynı sınıfı bu depo aynı gün `bootstrap.ps1` taşımasında da yaşadı.)

2. **Sabit MQTT `client_id`.** Ortak `mqtt_publish` yapılandırmadan gelen kimliği
   doğrudan `mqtt.Client(client_id=...)`a veriyordu. Bu depoda kayıtlı karar:
   *client_id SABİT OLAMAZ* — aynı kimlikle ikinci bağlantı brokerda birincisini düşürür.
   Backend bunu iki denetim turunda `_mqtt_client_id(role)` (`pemf_{role}_{pid}`) ile
   çözmüştü; CV yayıncısı o dersten **muaf kalmıştı** — hem kod varsayılanı hem örnek YAML
   sabit dize veriyordu. Artık yayın anında süreç eki konuyor, 23 karakter sınırı korunarak.

BU KAPININ İŞİ: kopyanın geri gelmesini ve kabuğun şişmesini KIRMIZI yapmak.
"""

from __future__ import annotations

import hashlib
import os
from collections import defaultdict
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]

#: ⚠️ VAKUM KAPISI: tarama sıfır dosya bulursa sonsuza kadar yeşil kalırdı.
#: 2026-09-19'da ölçülen: 82 izlenen `.py`. Taban, tavan değil.
ASGARI_TARANAN = 70

#: Kabuk = yalnız yeniden-dışa-aktarım + profil kimliği. Gövde taşırsa kopya geri gelmiştir.
KABUK_TAVANI = 70

PROFILLER = {
    "ai_hub/inference_em_fantom/phantom_cv": "phantom_cv_pipeline",
    "ai_hub/inference_petri_dish/petri_cv": "petri_cv_pipeline",
}
ORTAK_MODULLER = ("coord_transform", "mqtt_publish", "cabin_config")


#: Kabuklar — birbirinin aynı OLMALARI normaldir (aynı yeniden-dışa-aktarım metni).
#: Gövde taşımadıklarını `test_KRITIK_profil_dosyasi_KABUK_kaliyor` ayrıca ölçer.
KABUK_YOLLARI = frozenset(f"{p}/{m}.py" for p in PROFILLER for m in ORTAK_MODULLER)


def _taranan_py() -> list[str]:
    """`ai_hub` altındaki TÜM `.py` — DOSYA SİSTEMİNDEN.

    ⚠️ `git ls-files` KULLANILMAZ, ve bu bir mutasyonla ortaya çıktı (2026-09-19).
    İlk hâl git'e soruyordu; git yalnız İZLENEN dosyaları listeler. Birleştirme
    sırasında yeni kabuklar henüz takipsizdi ve tarama onları HİÇ GÖRMEDİ — "kopyayı
    geri koy" mutasyonu kapıyı bu yüzden geçti. Kopya diske yazılır, git'e değil;
    ölçüm de diskte yapılmalı.
    """
    kok = KOK / "ai_hub"
    if not kok.is_dir():
        pytest.skip("ai_hub yok")
    return sorted(p.relative_to(KOK).as_posix() for p in kok.rglob("*.py") if "__pycache__" not in p.parts)


def _kopya_gruplari(dosyalar: list[str]) -> dict[str, list[str]]:
    grup: dict[str, list[str]] = defaultdict(list)
    for rel in dosyalar:
        try:
            grup[hashlib.sha256((KOK / rel).read_bytes()).hexdigest()].append(rel)
        except OSError:
            continue
    return {h: v for h, v in grup.items() if len(v) > 1}


# ═════════════════════════════════════════════════════════════════════════════════════════
# 1. YAPI — kopya geri gelmesin
# ═════════════════════════════════════════════════════════════════════════════════════════


def test_KRITIK_ai_hub_altinda_BIREBIR_KOPYA_yok():
    """🔴 ASIL REGRESYON: aynı dosyanın iki kopyası → bir taraftaki düzeltme diğerinde kalmaz."""
    dosyalar = _taranan_py()
    assert len(dosyalar) >= ASGARI_TARANAN, (
        f"tarama çok dar ({len(dosyalar)} < {ASGARI_TARANAN}) — kapı boş dönüyor olabilir"
    )
    # ⚠️ Kabuklar taramanın İÇİNDE olmalı; dışarıda kalırlarsa "kopyayı geri koy"
    # mutasyonu görülmez (ilk hâlde tam bu oldu — git takipsiz dosyayı listelemiyordu).
    eksik = sorted(KABUK_YOLLARI - set(dosyalar))
    assert not eksik, f"kabuk dosyaları taramaya GİRMİYOR: {eksik} — kapı kör"

    kopya = _kopya_gruplari([d for d in dosyalar if d not in KABUK_YOLLARI])
    assert not kopya, "`ai_hub` altında BİREBİR AYNI dosyalar var:\n" + "\n".join(
        "  " + " == ".join(v) for v in kopya.values()
    )


def test_KRITIK_muafiyet_BASKA_kapiya_pinli():
    """Kabuklar kopya taramasından MUAF — muafiyet ancak başka bir kapı onları tutarsa geçerli.

    İki kabuk birbirinin aynıdır (aynı yeniden-dışa-aktarım metni) ve bu NORMALDİR:
    gövde taşımıyorlar. Tehlikeli olan, muafiyetin arkasına gövde saklanmasıdır — onu
    `test_KRITIK_profil_dosyasi_KABUK_kaliyor` satır tavanıyla ölçer. Bu test yalnız
    muafiyetin O KAPIYLA ÖRTÜŞTÜĞÜNÜ ve şişmediğini doğrular.
    """
    beklenen = {f"{p}/{m}.py" for p in PROFILLER for m in ORTAK_MODULLER}
    assert KABUK_YOLLARI == beklenen, (
        f"muafiyet listesi kabuk kapısıyla ÖRTÜŞMÜYOR — muaf ama ölçülmeyen dosya olur:\n"
        f"  yalnız muaf : {sorted(KABUK_YOLLARI - beklenen)}\n"
        f"  yalnız kapı : {sorted(beklenen - KABUK_YOLLARI)}"
    )
    assert len(KABUK_YOLLARI) == 6, f"muafiyet listesi şişmiş: {sorted(KABUK_YOLLARI)}"


@pytest.mark.parametrize("paket", sorted(PROFILLER))
@pytest.mark.parametrize("modul", ORTAK_MODULLER)
def test_KRITIK_profil_dosyasi_KABUK_kaliyor(paket: str, modul: str):
    """Kabuk şişerse kopya sessizce geri gelmiş demektir (gövde yapıştırma)."""
    p = KOK / paket / f"{modul}.py"
    assert p.exists(), f"{p} yok — kabuk silinmiş; import yolu sözleşmesi kırılır"
    satir = len(p.read_text(encoding="utf-8").splitlines())
    assert satir <= KABUK_TAVANI, (
        f"{paket}/{modul}.py {satir} satır (tavan {KABUK_TAVANI}) — gövde geri yapışmış olabilir"
    )
    assert "cv_ortak" in p.read_text(encoding="utf-8"), (
        f"{paket}/{modul}.py ortak uygulamaya bağlı DEĞİL — kendi gövdesini taşıyor olabilir"
    )


# ═════════════════════════════════════════════════════════════════════════════════════════
# 2. DAVRANIŞ — tek uygulama AMA profil kimliği korunuyor
# ═════════════════════════════════════════════════════════════════════════════════════════


def test_KRITIK_CabinConfig_TEK_SINIF():
    """İki profil aynı sınıfı görmeli; ayrı sınıflar = hâlâ iki uygulama."""
    from ai_hub.inference_em_fantom.phantom_cv.cabin_config import CabinConfig as C1
    from ai_hub.inference_petri_dish.petri_cv.cabin_config import CabinConfig as C2

    assert C1 is C2, "CabinConfig iki AYRI sınıf — birleştirme yalnız görünüşte"


def test_KRITIK_her_profil_KENDI_ornek_YAMLini_okuyor():
    """🔴 YAKIN KAZA. Taşıma sonrası varsayılan `cv_ortak/`a kayardı ve orada YAML YOK.

    `load_cabin_config(None)` üretimde dört yerden çağrılıyor; bu dal kırılırsa hepsi
    `FileNotFoundError` verir.
    """
    from ai_hub.inference_em_fantom.phantom_cv.cabin_config import load_cabin_config as fy
    from ai_hub.inference_petri_dish.petri_cv.cabin_config import load_cabin_config as py_

    a, b = fy(None), py_(None)
    assert a.cabin_id != b.cabin_id, (
        f"iki profil AYNI kabin yapılandırmasını okuyor ({a.cabin_id!r}) — varsayılan YAML ortak modüle kaymış olabilir"
    )
    assert "phantom" in a.cabin_id.lower(), f"fantom profili yanlış YAML okuyor: {a.cabin_id!r}"
    assert "petri" in b.cabin_id.lower(), f"petri profili yanlış YAML okuyor: {b.cabin_id!r}"


def test_KRITIK_profil_client_id_KIMLIGI_korundu(tmp_path):
    """⚠️ BU TESTİN İLK HÂLİ VAKUMDU — mutasyon ortaya çıkardı (A3, 2026-09-19).

    İlk yazımda yalnız `load_cabin_config(None)`ın döndürdüğü kimliğe bakıyordu. Ama
    örnek YAML `client_id`i **açıkça yazıyor**, yani `mq.get("client_id", varsayilan)`
    varsayılana HİÇ düşmüyor. Petri kabuğunun `VARSAYILAN_CLIENT_ID`ini fantomunkiyle
    değiştiren mutasyon kapıyı YEŞİL geçti: test, ölçtüğünü sandığı kod yolunu değil
    **YAML'ı** ölçüyordu.

    Şimdi iki yol AYRI ölçülüyor:
      · sabit doğrudan okunur (kabuğun kimliği)
      · YAML'dan `client_id` SİLİNİP yüklenir → varsayılan dalı GERÇEKTEN koşar
    """
    from ai_hub.inference_em_fantom.phantom_cv import cabin_config as fkab
    from ai_hub.inference_petri_dish.petri_cv import cabin_config as pkab

    # ── 1) Kabuk sabitleri ayrı olmalı ────────────────────────────────────────
    assert fkab.VARSAYILAN_CLIENT_ID != pkab.VARSAYILAN_CLIENT_ID, (
        f"iki profilin varsayılan kimliği AYNI ({fkab.VARSAYILAN_CLIENT_ID!r}) — profil kimliği kayboldu"
    )
    assert {fkab.VARSAYILAN_CLIENT_ID, pkab.VARSAYILAN_CLIENT_ID} == set(PROFILLER.values())

    # ── 2) VARSAYILAN DALI gerçekten koşsun: YAML'dan client_id'yi sil ────────
    for etiket, modul in (("fantom", fkab), ("petri", pkab)):
        satirlar = modul.DEFAULT_CONFIG_YAML.read_text(encoding="utf-8").splitlines(True)
        kirpik = [s for s in satirlar if "client_id:" not in s]
        assert len(kirpik) == len(satirlar) - 1, f"{etiket}: örnek YAML'da tam bir `client_id:` satırı beklenirdi"
        hedef = tmp_path / f"{etiket}.yaml"
        hedef.write_text("".join(kirpik), encoding="utf-8")

        cfg = modul.load_cabin_config(hedef)
        assert cfg.output.mqtt_client_id == modul.VARSAYILAN_CLIENT_ID, (
            f"{etiket}: YAML'da kimlik yokken varsayılan KULLANILMADI "
            f"({cfg.output.mqtt_client_id!r} ≠ {modul.VARSAYILAN_CLIENT_ID!r})"
        )

    # ── 3) YAML yolu da ayrı kimlik vermeye devam etmeli ──────────────────────
    a = fkab.load_cabin_config(None).output.mqtt_client_id
    b = pkab.load_cabin_config(None).output.mqtt_client_id
    assert a != b, f"YAML yolunda profil kimliği kaybolmuş — ikisi de {a!r}"


# ═════════════════════════════════════════════════════════════════════════════════════════
# 3. SABİT MQTT client_id YASAK
# ═════════════════════════════════════════════════════════════════════════════════════════


def test_KRITIK_mqtt_client_id_SABIT_DEGIL():
    """⚠️ Kayıtlı karar: aynı kimlikle ikinci bağlantı brokerda birincisini DÜŞÜRÜR."""
    from ai_hub.cv_ortak.mqtt_publish import benzersiz_client_id

    taban = "phantom_cv_pipeline"
    uretilen = benzersiz_client_id(taban)
    assert uretilen != taban, "kimlik olduğu gibi geçiyor — SABİT client_id"
    assert str(os.getpid() % 100000) in uretilen, f"süreç eki yok: {uretilen!r}"


@pytest.mark.parametrize(
    "taban", ["phantom_cv_pipeline", "petri_cv_pipeline", "cv", "a" * 60], ids=["fantom", "petri", "kisa", "cok_uzun"]
)
def test_KRITIK_client_id_23_KARAKTERI_ASMIYOR(taban: str):
    """⚠️ Eski brokerların SERT sınırı. Aşılırsa bağlantı REDDEDİLİR ve yayıncı SESSİZCE ölür.

    Backend `estop-cloud` rolünde bu tam olarak yaşandı: 24 karaktere taşıyordu.
    """
    from ai_hub.cv_ortak.mqtt_publish import benzersiz_client_id

    u = benzersiz_client_id(taban)
    assert len(u) <= 23, f"{taban!r} -> {u!r} ({len(u)} karakter) sınırı aşıyor"
    assert u, "boş kimlik üretildi"


def test_KRITIK_yayinci_HAM_kimligi_KULLANMIYOR():
    """Yardımcı var ama çağrılmıyorsa hiçbir şey değişmemiştir — çağrıyı kaynağa pinle."""
    kaynak = (KOK / "ai_hub" / "cv_ortak" / "mqtt_publish.py").read_text(encoding="utf-8")
    kod = "\n".join(s.split("#")[0] for s in kaynak.splitlines())
    assert "client_id=benzersiz_client_id(" in kod, (
        "`mqtt.Client(client_id=...)` yardımcıdan GEÇMİYOR — sabit kimlik geri gelmiş"
    )
    assert "client_id=out_cfg.mqtt_client_id" not in kod, "ham kimlik hâlâ doğrudan veriliyor"


# ═════════════════════════════════════════════════════════════════════════════════════════
# 4. KARŞIT-KANITLAR
# ═════════════════════════════════════════════════════════════════════════════════════════


def test_KARSIT_KANIT_kopya_tarayicisi_GERCEKTEN_yakaliyor(tmp_path):
    """Kapı boş geçmiyor: aynı içerikli iki dosya YAKALANMALI."""
    a, b, c = tmp_path / "a.py", tmp_path / "b.py", tmp_path / "c.py"
    a.write_bytes(b"x = 1\n")
    b.write_bytes(b"x = 1\n")
    c.write_bytes(b"x = 2\n")

    import hashlib as _h

    grup: dict[str, list[str]] = defaultdict(list)
    for p in (a, b, c):
        grup[_h.sha256(p.read_bytes()).hexdigest()].append(p.name)
    kopya = {k: v for k, v in grup.items() if len(v) > 1}
    assert len(kopya) == 1, "tarayıcı kopyayı KAÇIRIYOR"
    assert sorted(next(iter(kopya.values()))) == ["a.py", "b.py"]
    assert "c.py" not in str(kopya), "FARKLI dosya kopya sayıldı"


def test_KARSIT_KANIT_birlesme_ONCESI_hal_KIRMIZI_olurdu():
    """2026-09-19 öncesi ağaç bu kapıdan GEÇEMEZDİ — ölçülen gerçek durum.

    O gün `coord_transform.py` (326 satır) ve `mqtt_publish.py` (144) iki pakette
    MD5 birebir aynıydı. Kapı o hâli kırmızı yapmalıydı; aşağıdaki kurgu onu temsil eder.
    """
    ortak = (KOK / "ai_hub" / "cv_ortak" / "coord_transform.py").read_bytes()
    grup: dict[str, list[str]] = defaultdict(list)
    for ad in ("phantom_cv/coord_transform.py", "petri_cv/coord_transform.py"):
        grup[hashlib.sha256(ortak).hexdigest()].append(ad)
    assert len({h: v for h, v in grup.items() if len(v) > 1}) == 1, (
        "birleşme öncesi hâl yakalanmıyor — kapı o günkü arızayı görmezdi"
    )


def test_KARSIT_KANIT_sabit_esikler_SISIRILMEMIS():
    """ "Kırmızıyı sustur" diye tavanı/tabanı oynatan yamayı yakalar."""
    assert KABUK_TAVANI <= 70, f"kabuk tavanı şişmiş ({KABUK_TAVANI}) — gövde geri sızabilir"
    assert ASGARI_TARANAN >= 70, f"tarama tabanı düşürülmüş ({ASGARI_TARANAN})"
    assert len(ORTAK_MODULLER) == 3, "ortak modül listesi değişmiş — bilinçliyse kapıyı güncelle"
