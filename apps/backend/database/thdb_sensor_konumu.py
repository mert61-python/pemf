# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""Y308 (sahip 19-11: "konum kaydını da al yayına ama sensör serbest de gezdirilebilsin konum bilgisi olmadan; kullanıcı hangisini isterse")
— KABİN SENSÖRÜ (MLX) KONUM KAYDI, İSTEĞE BAĞLI.

VARSAYILAN serbest: hiç giriş yoksa seans, ekran, grafik, PDF / CSV bugünküyle BİREBİR. KONUMLU kullanım: seans sırasında ya da seans
bittikten sonra ZAMAN DAMGALI girişler (sol çıkıntıdan cm, ön çıkıntıdan cm, tabandan yükseklik cm, isteğe bağlı not) ya da "serbest"
girişi (konumsuz dilim). Her giriş bir sonrakine (ya da seans sonuna) kadar geçerlidir.

VERİ: mevcut tablolara ALTER YOK — AYRI tablo `sensor_konumlari`; mevcut göç düzeneğinde (`_semayi_kur`, tek işlem) idempotent
`CREATE TABLE IF NOT EXISTS`; şifreli DB'nin kendi bağlantı yolundan. Eski sürüm bu tabloyu tanımaz ve YOK SAYAR. Buluta senkron
kapsamına ALINMAZ (outbox'a yazılmaz — yerel). Seans silinince kayıtları da silinir (`delete_session` / toplu silme); yedek ve veri
taşıma DB dosyasının bütünüyle çalıştığı için tabloyu kendiliğinden kapsar (ölçüldü: testler)."""

from __future__ import annotations

import time
from typing import Dict, List, Optional

TABLO = "sensor_konumlari"

#: `thdb_sema._create_core_tables` bunu çalıştırır (tek işlem, idempotent).
SEMA = """
    CREATE TABLE IF NOT EXISTS sensor_konumlari (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id INTEGER NOT NULL,
        zaman_epoch REAL NOT NULL,
        serbest INTEGER NOT NULL DEFAULT 0,
        sol_cm REAL,
        on_cm REAL,
        yukseklik_cm REAL,
        not_metni TEXT,
        created_at REAL NOT NULL
    )
"""
DIZIN = "CREATE INDEX IF NOT EXISTS idx_sensor_konumlari_seans ON sensor_konumlari(session_id, zaman_epoch)"

_ALANLAR = ("id", "session_id", "zaman_epoch", "serbest", "sol_cm", "on_cm", "yukseklik_cm", "not_metni")


def _satir(r) -> Dict:
    d = dict(zip(_ALANLAR, r))
    d["serbest"] = bool(d["serbest"])
    return d


class SensorKonumuKarisimi:
    """TreatmentHistoryDB karışımı — `sensor_konumlari` okuma / yazma (yalnız bu tablo)."""

    def sensor_konumu_ekle(
        self,
        session_id: int,
        zaman_epoch: float,
        *,
        serbest: bool,
        sol_cm: Optional[float] = None,
        on_cm: Optional[float] = None,
        yukseklik_cm: Optional[float] = None,
        not_metni: str = "",
    ) -> int:
        self._ensure_write_guardrail()
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO sensor_konumlari (session_id, zaman_epoch, serbest, sol_cm, on_cm, yukseklik_cm, not_metni, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    int(session_id),
                    float(zaman_epoch),
                    1 if serbest else 0,
                    None if serbest else sol_cm,
                    None if serbest else on_cm,
                    None if serbest else yukseklik_cm,
                    not_metni or "",
                    time.time(),
                ),
            )
            kimlik = int(cur.lastrowid)
            conn.commit()
            return kimlik

    def sensor_konumu_guncelle(
        self,
        kayit_id: int,
        session_id: int,
        zaman_epoch: float,
        *,
        serbest: bool,
        sol_cm: Optional[float] = None,
        on_cm: Optional[float] = None,
        yukseklik_cm: Optional[float] = None,
        not_metni: str = "",
    ) -> bool:
        self._ensure_write_guardrail()
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute(
                "UPDATE sensor_konumlari SET zaman_epoch = ?, serbest = ?, sol_cm = ?, on_cm = ?, yukseklik_cm = ?, not_metni = ? "
                "WHERE id = ? AND session_id = ?",
                (
                    float(zaman_epoch),
                    1 if serbest else 0,
                    None if serbest else sol_cm,
                    None if serbest else on_cm,
                    None if serbest else yukseklik_cm,
                    not_metni or "",
                    int(kayit_id),
                    int(session_id),
                ),
            )
            degisti = cur.rowcount > 0
            conn.commit()
            return degisti

    def sensor_konumu_sil(self, kayit_id: int, session_id: int) -> bool:
        self._ensure_write_guardrail()
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute(
                "DELETE FROM sensor_konumlari WHERE id = ? AND session_id = ?", (int(kayit_id), int(session_id))
            )
            silindi = cur.rowcount > 0
            conn.commit()
            return silindi

    def sensor_konumlari(self, session_id: int) -> List[Dict]:
        with self._get_connection() as conn:
            rows = conn.execute(
                f"SELECT {', '.join(_ALANLAR)} FROM sensor_konumlari WHERE session_id = ? ORDER BY zaman_epoch, id",
                (int(session_id),),
            ).fetchall()
        return [_satir(r) for r in rows]
