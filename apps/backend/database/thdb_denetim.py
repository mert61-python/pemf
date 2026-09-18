# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""DENETIM IZI (audit) — `TreatmentHistoryDB`nin denetim yarisi (B4 · 2/N, 2026-09-18).

⚠️ AYRILMA GEREKCESI: bkz. `database/thdb_outbox.py` bas yorumu (B4 · 1/N). Ozet: tek sinifta
yedi ayri sorumluluk vardi; her kume TEK tabloya dokundugu icin ayri ayri tasinabiliyor.
Bu kume `audit_events` tablosuna dokunur.

⚠️ NEDEN AYRI BIR TABLO VE NEDEN SILINMEZ: denetim izi, "kim ne zaman hangi hasta kaydina
dokundu" sorusunun TEK kanitidir (KVKK "unutulma hakki" talepleri dahil). Iz, sildigi
verinin ikinci bir kopyasi OLAMAZ — bu yuzden hasta ADI yazilmaz, yalniz kimlik/kapsam.

⚠️ GOVDELER DEGISTIRILMEDI — bayt bayt tasindi. Kullandigi yardimcilar
(`get_app_version`, `get_build_id`, `dict_satir_fabrikasi`) FONKSIYON ICINDE import
ediliyor, yani govdelerle birlikte geldi; modul duzeyinde ek import gerekmiyor.

`self` uzerinden kullandigi ve ANA SINIFTA kalan uyeler: `_get_connection`, `logger`.
"""

from __future__ import annotations


class DenetimKarisimi:
    def _create_audit_table(self, cursor):
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS audit_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts_utc TEXT NOT NULL,
                event_type TEXT NOT NULL,
                operator_email TEXT,
                client_ip TEXT,
                scope TEXT,
                item_count INTEGER,
                outcome TEXT,
                detail TEXT,
                app_version TEXT,
                build_id TEXT
            )
        ''')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_audit_ts ON audit_events(ts_utc)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_audit_type ON audit_events(event_type, ts_utc)')
        # EKLEME-ONLY mühür: SQLite tetikleyicileri. Uygulama kodu zaten UPDATE/DELETE yapmıyor;
        # bu, DB dosyasına doğrudan erişen birine karşı ikinci kapı.
        cursor.execute('''
            CREATE TRIGGER IF NOT EXISTS audit_events_no_update
            BEFORE UPDATE ON audit_events
            BEGIN SELECT RAISE(ABORT, 'denetim izi degistirilemez (ekleme-only)'); END
        ''')
        cursor.execute('''
            CREATE TRIGGER IF NOT EXISTS audit_events_no_delete
            BEFORE DELETE ON audit_events
            BEGIN SELECT RAISE(ABORT, 'denetim izi silinemez (ekleme-only)'); END
        ''')

    def denetim_yaz(
        self,
        event_type: str,
        *,
        operator_email: str = "",
        client_ip: str = "",
        scope: str = "",
        item_count=None,
        outcome: str = "ok",
        detail=None,
    ) -> bool:
        """Denetim olayını yaz. **ASLA istisna atmaz** ve çağıranın işlemini bozmaz.

        ⚠️ Bilinçli tasarım: denetim yazımı bir silme/dışa-aktarma işlemini ENGELLEMEZ. Aksi
        hâlde dolu bir diskte veteriner hiçbir şey yapamaz hâle gelirdi. Ama yazamama sessiz
        de kalmaz — log'a ERROR düşer ve `outcome` alanı çağıranın sonucunu taşır.
        """
        import datetime as _dt
        import json as _json

        try:
            from utils.path_utils import get_app_version, get_build_id

            surum, yapi = get_app_version(), get_build_id()
        except Exception:
            surum, yapi = "", ""
        try:
            ayrinti = _json.dumps(detail, ensure_ascii=False)[:4000] if detail is not None else None
        except Exception:
            ayrinti = None
        try:
            with self._lock:
                with self._get_connection() as conn:
                    conn.execute(
                        "INSERT INTO audit_events (ts_utc, event_type, operator_email, client_ip, "
                        "scope, item_count, outcome, detail, app_version, build_id) "
                        "VALUES (?,?,?,?,?,?,?,?,?,?)",
                        (
                            _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"),
                            str(event_type)[:64],
                            (operator_email or "")[:200],
                            (client_ip or "")[:64],
                            (scope or "")[:200],
                            int(item_count) if item_count is not None else None,
                            (outcome or "")[:32],
                            ayrinti,
                            surum,
                            yapi,
                        ),
                    )
                    conn.commit()
            return True
        except Exception as e:
            self.logger.error("DENETIM IZI YAZILAMADI (%s): %s", event_type, e)
            return False

    def denetim_oku(self, limit: int = 200, event_type: str = "") -> list:
        """Son denetim olayları (en yeni önce). Salt-okuma."""
        try:
            from database.sqlcipher_util import dict_satir_fabrikasi

            with self._lock:
                with self._get_connection() as conn:
                    # ⚠️ DENETİM 2026-08-17: `row_factory` burada atanıp GERİ YÜKLENMİYORDU ve
                    # bağlantı HAVUZDAN gelip thread-başına yeniden kullanıldığı için kirlenme
                    # süreç ömrü boyunca sürüyordu (bütünlük kontrolü "bozuk", KVKK onay bloğu
                    # görünmez, export/import 500). Ayrıntı: dict_satir_fabrikasi docstring'i.
                    with dict_satir_fabrikasi(conn):
                        sorgu = (
                            "SELECT * FROM audit_events "
                            + ("WHERE event_type = ? " if event_type else "")
                            + "ORDER BY id DESC LIMIT ?"
                        )
                        par = (event_type, int(limit)) if event_type else (int(limit),)
                        return [dict(r) for r in conn.execute(sorgu, par).fetchall()]
        except Exception as e:
            self.logger.error("Denetim izi okunamadi: %s", e)
            return []

    def denetim_sayisi(self) -> int:
        try:
            with self._lock:
                with self._get_connection() as conn:
                    return int(conn.execute("SELECT COUNT(*) FROM audit_events").fetchone()[0])
        except Exception:
            return 0
