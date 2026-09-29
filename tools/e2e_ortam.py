# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""e2e araçlarının (`tools/e2e_smoke.py`, `tools/e2e_full.py`) backend ALT SÜRECİ ortamı — TEK YERDE.

⚠️ D0Ö.08 (B-10.21 · B-10.22). İki araç ortamı ayrı ayrı kuruyordu ve ayrışmışlardı: e2e_smoke'ta
`PEMF_STM_PORT` YOKTU → varsayılan COM10: gerçek kart takılıysa seans senaryosu bobin 1, 2, 7'ye
%25 / 50 Hz paket gönderebilirdi (onaysız sürüş). İkisi de GERÇEK ProgramData cihaz sırrını okuyup
yazıyor, gömülü Supabase adresiyle üretim `devices` tablosuna e2e kaydı upsert ediyordu.
Kapı: tests/test_e2e_alt_surec_ortami.py (her aracın `main()`i sahte Popen'la koşturulur).
"""

from __future__ import annotations

import os
from pathlib import Path

#: Bağlantı reddedilen loopback (discard portu): bulut cihaz kaydı buraya gider, üretime GİTMEZ.
SUPABASE_KARA_DELIK = "http://127.0.0.1:9"


def alt_surec_ortami(data_dir: Path, port: int, guii: Path, ek: dict | None = None) -> dict:
    """Backend alt sürecinin ortamı: her kök `data_dir` altında, donanım ve bulut kapalı."""
    # Alt surecin SAHTE EV DIZINI — masaustu sizintisini keser.
    sahte_ev = data_dir / "sahte_ev"
    (sahte_ev / "Desktop").mkdir(parents=True, exist_ok=True)
    # ⚠️ İZİN LİSTESİ (D0Ö.08 ek): dış ortamdan HİÇBİR PEMF_*/SUPABASE_* miras alınmaz — ör. PEMF_BACKUP_DIR
    # backend'in ilk yedek turunda kurtarma zarfını GERÇEK off-site dizindeki aynı adlı zarfın ÜZERİNE
    # yazdırırdı; PEMF_MQTT_CLOUD_* E-stop'u gerçek broker'a aynalar, PEMF_SENTRY_DSN uzaktan hata izlemeyi
    # açar; PEMF_REQUIRE_AUTH/CORS/MASK_HISTORY_PII senaryoları bozar. Gereken her şey aşağıda AÇIKÇA verilir.
    env = {k: v for k, v in os.environ.items() if not k.upper().startswith(("PEMF_", "SUPABASE_"))}
    env.update(
        {
            "PEMF_SIMULATE": "1",  # sanal STM+ESP+8 bobin + sensör
            # ⚠️ PEMF_SIMULATE `stm_bagli`yı ETKİLEMEZ: port verilmezse varsayılan COM10'a bağlanılır.
            # 'SIM' gerçek bir port değil ve otomatik taramaya DÜŞMEZ → gerçek karta paket GİTMEZ.
            "PEMF_STM_PORT": "SIM",
            "PEMF_FW_AUTO_UPDATE": "0",
            "PEMF_HOTSPOT": "0",
            "PEMF_DATA_DIR": str(data_dir),  # İZOLE veri dizini
            # ══════════════════════════════════════════════════════════════════════
            # ⚠️ MASAUSTU DA IZOLE EDILMELI (2026-09-11, IKINCI KEZ yasandi)
            # ══════════════════════════════════════════════════════════════════════
            # `/api/session/start` her seansta masaustune `PEMF_alan_*.csv` yazar
            # (apps/backend/servers/seans_alan_kaydi). Bu betik GERCEK bir backend alt sureci baslatir
            # ve pytest `conftest` izolasyonu BURADA GECERLI DEGILDIR → her kosu sahibin
            # masaustune bir tomar test dosyasi birakiyordu (olculdu: 3 kosu = 18 dosya,
            # hasta adlari SyncTest/ParamTest/Minnos/Duman...).
            #
            # `masaustu_dizini()` yolu `os.path.expanduser("~")`den cozer → alt surecin
            # EV DIZINI sahteye cevrilir. ⚠️ Yalniz ALT SURECTE: ana surecteki gercek `~`
            # dokunulmadan kalir, boylece `tests/test_veri_dizini_izolasyonu.py` gibi
            # GERCEK ev dizinine bakan kapilar sahte-yesile DONMEZ.
            #
            # ⚠️ `Desktop` KLASORU ONCEDEN ACILIR: `masaustu_dizini()` masaustunu bulamazsa
            # `Path.cwd()`e duser ve bu kez DEPO DIZINI dosyayla dolardi.
            "USERPROFILE": str(sahte_ev),
            "HOME": str(sahte_ev),
            # ⚠️ APPDATA DA İZOLE EDİLMELİ (2026-08-14). `PEMF_DATA_DIR` tek başına YETMİYOR:
            # backend açılışta `%APPDATA%\PEMF_GUI`den "eski kullanıcı klasörü → makine geneli"
            # göçünü çalıştırıyor (apps/backend/utils/path_utils._kullanicidan_makineye_gocur) ve geliştirici
            # makinesindeki BAYAT, BAŞKA ANAHTARLA şifreli tedavi DB'sini test dizinine
            # kopyalıyordu → `hmac check failed for pgno=1` → backend HİÇ açılmıyordu.
            # (Testin gördüğü hata da yanıltıcıydı; bkz. e2e_smoke'taki log yazdırma notu.)
            "APPDATA": str(data_dir / "_appdata"),
            "LOCALAPPDATA": str(data_dir / "_localappdata"),
            # ⚠️ Makine kapsamlı cihaz sırrı (`ProgramData\PEMF_System\device_identity.json`) veri
            # kökünü İZLEMEZ → ayrıca yönlendirilir (B-10.22: araçlar GERÇEK sırrı okuyup yazıyordu).
            "PROGRAMDATA": str(data_dir / "_programdata"),
            "PEMF_DEVICE_IDENTITY_DIR": str(data_dir / "_makine_kimligi"),
            # Bulut: cihaz kaydı kara-deliğe, hasta senkronu kapalı, E-stop bulut aynası provizyonsuz
            # (depo içindeki `data/cloud_mqtt_provision.json` GERÇEK broker'ın kimliğidir).
            "SUPABASE_URL": SUPABASE_KARA_DELIK,
            "PEMF_CLOUD_PATIENT_SYNC": "0",
            "PEMF_CLOUD_PROVISION_PATH": str(data_dir / "YOK_cloud_mqtt_provision.json"),
            "PEMF_API_HOST": "127.0.0.1",
            "PEMF_API_PORT": str(port),
            "PEMF_HEADLESS": "1",
            "PEMF_ENABLE_TUNNEL": "0",
            "PEMF_LOG_DIR": str(data_dir / "logs"),
            # Gomulu Python dagitimi (._pth) betik dizinini sys.path'e eklemiyor → acikca ver.
            "PYTHONPATH": str(guii),
            "PYTHONIOENCODING": "utf-8",
            # ⚠️ KASA (D0Ö.08 ek): ürünün eski-kaynak okuyucuları önce keyring'e bakar → kaynaktan koşan
            # backend sahibin GERÇEK Windows kasasındaki PEMF_GUI anahtarlarını (sqlcipher_key dahil) okuyup
            # e2e köküne göçürüyor, e2e DB'lerini GERÇEK at-rest anahtarıyla şifreliyordu (D0Ö.02 sınıfı).
            "PYTHON_KEYRING_BACKEND": "keyring.backends.null.Keyring",
        }
    )
    # LAN muaf → token'sız test; varsayılan CORS/PII davranışı sınanır (izin listesi bunları zaten dışarıda
    # bırakır — PEMF_REQUIRE_AUTH, PEMF_REQUIRE_PATIENT_AUTH, PEMF_CORS_ORIGINS, PEMF_MASK_HISTORY_PII).
    env.update(ek or {})
    return env
