# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""DESTEK PAKETİ — tek dosyada, PII maskelenmiş teşhis (2026-08-09 denetimi, Tier 3).

ARIZA: saha teşhisi "telefonda operatöre ProgramData yolunu tarif etmek"ti. Veteriner
`C:\\ProgramData\\PEMF_System\\logs` altından hangi dosyayı, nasıl göndereceğini bilmiyor; log
dosyaları 60 MB ve **içlerinde hasta adı geçebiliyor** — yani "logu bana yolla" demek, KVKK
açısından kontrolsüz bir kişisel veri aktarımı istemek demek.

BU MODÜLÜN SÖZLEŞMESİ
  • Toplar: sağlık/sürüm özeti, log kuyrukları, çökme kaydı, denetim izi ÖZETİ (tür+sayı),
    yapılandırma anahtarlarının VARLIK bilgisi.
  • ASLA toplamaz: `pemf_secrets.json`, anahtar dosyaları, veritabanı dosyaları, kurtarma zarfı.
  • Maskeler: (a) DB'den okunan GERÇEK hasta/sahip adları ve operatör e-postaları — jenerik
    desen değil, o cihazdaki somut değerler; (b) e-posta/jeton/parola/anahtar kalıpları.

⚠️ Maskeleme "en iyi gayret"tir, mutlak değil. Bu yüzden paket bir ÖZET dosyası taşır: hangi
kalemler tarandı, kaç eşleşme maskelendi. Destek de klinik de neyin gönderildiğini görebilir.
"""

from __future__ import annotations

import io
import json
import logging
import os
import re
import zipfile
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

#: Log kuyruğu tavanı — 60 MB'lık dosyanın tamamı gönderilmez.
KUYRUK_BAYT = 512 * 1024

#: ASLA pakete girmeyecek dosya adları (tam ad ya da uzantı).
YASAK_ADLAR = {
    "pemf_secrets.json",
    ".sqlcipher_key",
    "kurtarma-zarfi.enc",
    "KURTARMA-KODU.txt",
    "server.env",
    "device.env",
    ".env",
}
YASAK_UZANTILAR = {".db", ".db-wal", ".db-shm", ".sqlite", ".pem", ".p12", ".p8", ".jks", ".keystore"}

# Jenerik sır/PII kalıpları.
#
# ⚠️ SIRA KRİTİK (ölçülerek bulundu): anahtar=değer kuralı `Authorization: Bearer eyJ...`
# satırında değer olarak yalnız "Bearer" kelimesini yakalıyor ve JETONU OLDUĞU GİBİ BIRAKIYORDU.
# Bu yüzden şema-önekli kimlik başlıkları ÖNCE tüketilir. Aynı gerekçeyle `authorization`
# başlığında satır SONUNA kadar maskelenir — jeton içinde boşluk olmasa da, "değer boşlukta
# biter" varsayımı bir kimlik başlığı için fazla iyimserdir.
_KALIPLAR = [
    (re.compile(r'(?i)\bauthorization\s*[:=].*'), 'Authorization: [MASKELENDI]'),
    (re.compile(r'(?i)\b(?:Bearer|Basic|Token)\s+[A-Za-z0-9._\-=+/]{8,}'), '[MASKELENDI]'),
    (
        re.compile(
            r'(?i)\b([\w.-]*(?:password|passphrase|secret|token|api[_-]?key)[\w.-]*)'
            r'\s*[:=]\s*["\']?([^\s"\',;}]{4,})'
        ),
        r'\1=[MASKELENDI]',
    ),
    (re.compile(r'\b[\w.+-]+@[\w-]+\.[\w.-]+\b'), '[EPOSTA]'),
    (re.compile(r'\b[0-9a-f]{32,}\b'), '[HEX]'),
]


class Maskeleyici:
    """Cihaza ÖZGÜ PII değerlerini + jenerik kalıpları maskeler."""

    def __init__(self, gercek_degerler=()):
        self.pii_listesi_bos = not bool(list(gercek_degerler))
        # Uzundan kısaya: "Ali" önce eşleşip "Ali Veli"yi bölmesin.
        self._degerler = sorted(
            {str(d).strip() for d in gercek_degerler if d and len(str(d).strip()) >= 3}, key=len, reverse=True
        )
        self._sayac = 0

    @property
    def maskelenen(self) -> int:
        return self._sayac

    def __call__(self, metin: str) -> str:
        for d in self._degerler:
            if d in metin:
                self._sayac += metin.count(d)
                metin = metin.replace(d, "[PII]")
        for desen, yerine in _KALIPLAR:
            metin, n = desen.subn(yerine, metin)
            self._sayac += n
        return metin


def _pii_degerleri(app_data_dir) -> list:
    """Cihazdaki gerçek hasta/sahip adları + operatör e-postaları. Okunamıyorsa boş liste
    (paket yine üretilir; jenerik maskeleme devrede kalır)."""
    degerler = []
    try:
        from database.treatment_history_db import get_treatment_db

        db = get_treatment_db(Path(app_data_dir))
        with db._get_connection() as c:
            for sorgu in (
                "SELECT DISTINCT patient_name FROM treatment_sessions",
                "SELECT DISTINCT operator_name FROM treatment_sessions",
                "SELECT DISTINCT operator_email FROM treatment_sessions",
                "SELECT DISTINCT name FROM patients",
                "SELECT DISTINCT owner_name FROM patients",
            ):
                try:
                    degerler += [r[0] for r in c.execute(sorgu).fetchall() if r[0]]
                except Exception:
                    continue
    except Exception as e:
        logger.warning("Destek paketi: PII listesi okunamadi (jenerik maskeleme devrede): %s", e)
    return degerler


def _log_dizini(app_data_dir) -> Path:
    return Path(os.environ.get("PEMF_LOG_DIR", Path(app_data_dir) / "logs"))


def _guvenli_mi(p: Path) -> bool:
    return p.name not in YASAK_ADLAR and p.suffix.lower() not in YASAK_UZANTILAR


def _kuyruk(p: Path, tavan: int = KUYRUK_BAYT) -> str:
    """Dosyanın SON `tavan` baytı (log dosyaları 60 MB olabilir)."""
    try:
        boyut = p.stat().st_size
        with open(p, "rb") as f:
            if boyut > tavan:
                f.seek(boyut - tavan)
                f.readline()  # yarım satırı at
            return f.read().decode("utf-8", errors="replace")
    except Exception as e:
        return f"[okunamadi: {e}]"


def _saglik_ozeti(app_data_dir) -> dict:
    """Sağlık/sürüm özeti — HTTP'ye gerek yok; paket backend çökmüşken de üretilebilmeli."""
    ozet = {"olusturuldu_utc": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    try:
        from utils.path_utils import get_app_version, get_build_id

        ozet["app_version"] = get_app_version()
        ozet["build_id"] = get_build_id() or None
    except Exception:
        pass
    for anahtar, env in (
        ("launcher_version", "PEMF_LAUNCHER_VERSION"),
        ("base_sha", "PEMF_BASE_SHA"),
        ("data_dir", "PEMF_DATA_DIR"),
        ("log_dir", "PEMF_LOG_DIR"),
    ):
        v = os.environ.get(env)
        if v:
            ozet[anahtar] = v
    try:
        import platform
        import sys

        ozet["python"] = sys.version.split()[0]
        ozet["os"] = f"{platform.system()} {platform.release()}"
    except Exception:
        pass
    try:
        from database.treatment_history_db import get_treatment_db

        db = get_treatment_db(Path(app_data_dir))
        ozet["at_rest_encrypted"] = bool(getattr(db, "at_rest_encrypted", False))
        ozet["audit_event_count"] = db.denetim_sayisi()
    except Exception as e:
        ozet["db_hatasi"] = str(e)[:200]
    return ozet


def _denetim_ozeti(app_data_dir) -> dict:
    """Denetim izinin SAYIM özeti. Olayların kendisi (kapsam/kimlik) pakete GİRMEZ: destek
    "cihazda 3 kez toplu silme olmuş" bilgisini görmeli, kimin sildiğini görmek zorunda değil."""
    try:
        from database.treatment_history_db import get_treatment_db

        db = get_treatment_db(Path(app_data_dir))
        sayim = {}
        for k in db.denetim_oku(1000):
            sayim[k["event_type"]] = sayim.get(k["event_type"], 0) + 1
        return sayim
    except Exception:
        return {}


def olustur(app_data_dir, hedef=None, log_tavani: int = KUYRUK_BAYT) -> tuple:
    """Destek paketini üret. `(zip_baytlari, ozet_dict)` döner.

    `hedef` verilirse dosyaya da yazılır.
    """
    app_data_dir = Path(app_data_dir)
    maskele = Maskeleyici(_pii_degerleri(app_data_dir))

    saglik = _saglik_ozeti(app_data_dir)
    denetim = _denetim_ozeti(app_data_dir)

    log_dir = _log_dizini(app_data_dir)
    alinan, atlanan = [], []
    tampon = io.BytesIO()
    with zipfile.ZipFile(tampon, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("saglik.json", json.dumps(saglik, ensure_ascii=False, indent=2))
        z.writestr("denetim_ozeti.json", json.dumps(denetim, ensure_ascii=False, indent=2))
        if log_dir.is_dir():
            for p in sorted(log_dir.glob("*")):
                if not p.is_file():
                    continue
                if not _guvenli_mi(p):
                    atlanan.append(p.name)
                    continue
                z.writestr(f"logs/{p.name}", maskele(_kuyruk(p, log_tavani)))
                alinan.append(p.name)
        ozet = {
            **saglik,
            "log_dizini": str(log_dir),
            "alinan_dosyalar": alinan,
            "atlanan_dosyalar": atlanan,
            "maskelenen_eslesme": maskele.maskelenen,
            "log_tavani_bayt": log_tavani,
            "not": (
                "Bu paket KİŞİSEL VERİ İÇERMEMEK ÜZERE maskelenmiştir; maskeleme en iyi "
                "gayrettir. Göndermeden önce içeriğe bakabilirsiniz. Sır dosyaları, "
                "veritabanları ve kurtarma zarfı BİLİNÇLİ OLARAK dâhil edilmez."
            ),
        }
        # ⚠️ SESSİZ ZAYIFLAMA UYARISI. Asıl koruma, cihazdaki GERÇEK hasta/sahip adlarının
        # maskelenmesidir; o liste DB'den okunur. Şifreli DB açılamazsa (örn. bu araç servis
        # dışında, anahtara erişimi olmayan bir hesapla çalıştırıldıysa) liste BOŞ kalır ve
        # geriye yalnız jenerik desenler kalır — hasta adı maskelenmez. Bu, paketi üreten
        # kişiye SÖYLENMELİDİR; sessizce zayıflamış bir maskeleme, hiç maskelememekten kötüdür.
        if maskele.pii_listesi_bos:
            ozet["UYARI"] = (
                "Hasta/operatör listesi okunamadı (şifreli veritabanı açılamadı). "
                "Yalnız genel desenler maskelendi; loglarda GERÇEK HASTA ADI "
                "kalmış olabilir. Göndermeden önce logs/ içeriğini gözden geçirin "
                "ya da paketi cihazın kendi arayüzünden (Destek paketi düğmesi) "
                "üretin."
            )
        z.writestr("OZET.json", json.dumps(ozet, ensure_ascii=False, indent=2))

    veri = tampon.getvalue()
    if hedef:
        Path(hedef).write_bytes(veri)
    return veri, ozet


def dosya_adi() -> str:
    return f"pemf-destek-{datetime.now():%Y%m%d-%H%M}.zip"
