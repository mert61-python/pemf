# Author: mertaygn, cglrgrkn
"""Characterization: sistem/durum GET uçlarının RESPONSE SHAPE'i (anahtar kümesi).

Route-contract PATH'i korur; bu test RESPONSE gövdesinin anahtar-kümesini dondurur →
extraction sırasında bir handler'ın çıktı-şekli (ör. transkripsiyon hatası, eksik alan)
değişirse KIRILIR. Özellikle `/api/health` kurulum-doğrulaması (`atRestEncrypted`,
`status`) için kritik.

Baseline: 2026-07-06. Client kurulumu test_api_safety ile aynı (PEMF_SIMULATE kapalı).
"""

import pytest
from fastapi.testclient import TestClient

GOLDEN_SHAPES = {
    "/api/health": {
        "atRestEncrypted",
        "core_initialized",
        "deviceId",
        "localIp",
        "pairingCode",
        "service",
        "services",
        "status",
        "stmConnected",
        # ⚠️ BILINCLI SEKIL DEGISIKLIGI 2026-09-18 — "BAGLI" ile "UYUMLU" AYRI SORULARDIR.
        # `stmConnected` yalnizca "kart konusuyor mu" der. Eski firmware (5 bobin) backend'in
        # 120 baytlik paketini anlamaz, her pakete NACK doner ve PWM'e hic dokunmaz — ama
        # `STM_READY` bastigi icin `stmConnected` YINE TRUE olur. Belirti: gosterge yesil,
        # hata yok, HICBIR bobin calismiyor. Bu iki alan o ayrimi gorunur kilar:
        #   stmUyumlu: true=uyumlu · false=KESIN uyumsuz (seans 409 ile reddedilir) ·
        #              null=banner taninmadi/henuz gorulmedi (seans ENGELLENMEZ)
        # Kapi: tests/test_stm_firmware_uyum_kapisi.py
        "stmUyumlu",
        "stmUyumsuzlukSebebi",
        # ⚠️ BILINCLI SEKIL DEGISIKLIGI 2026-10-14 (TD1, tezgâh Oturum 13): operatör KODU (FW-PAKET = kartın yazılımı
        # uyumsuz · FW-KIMLIK = doğrulanamadı · null = bant yok). `stmUyumsuzlukSebebi` destek metnidir (teknik).
        "stmUyumKodu",
        "tunnelUrl",
        # DENETIM P2 (BILINCLI sekil degisikligi): bulut cihaz-registry durumu. 'secret_mismatch'
        # KALICI bir hatadir (TOFU muhru — yeniden kurulum sonrasi device_secret degisti) ve
        # eskiden yalnizca log'a dusuyordu; operator uzaktan erisimin neden sessizce
        # guncellenmedigini goremiyordu. Bu test tam da sekil degisikliklerini yakalamak icin
        # var → altin kume kasitli olarak genisletildi.
        "cloudRegistry",
        # DENETIM 2026-08-04 P2 #13 (BILINCLI sekil degisikligi): launcher'in "bu porttaki
        # GERCEKTEN benim baslattigim backend mi?" dogrulamasi. find_free_port portu bind edip
        # hemen birakiyor; o pencerede portu kapan yerel bir surec HTTP 200 dondugu icin "hazir"
        # saniliyordu → kapanistaki E-stop POST'u ONA gidiyor, gercek bobinler hastanin uzerinde
        # kaliyordu. Deger YALNIZ loopback'e verilir (tunele/LAN'a sizarsa dogrulama anlamsiz);
        # `PEMF_HEALTH_NONCE` verilmemisse None doner. Bkz. launcher/core/src/backend.rs.
        "launcherNonce",
        # DENETIM 2026-08-04 (BILINCLI sekil degisikligi): launcher oto-guncellemesi acilista
        # SESSIZCE `/S` kurulum yapar; NSIS yukseltme kancasi PEMF_Backend.exe'yi oldurur →
        # HASTA UZERINDE SUREN seans yarida kesilirdi. Launcher artik guncellemeden ONCE bunu
        # okuyup seans varsa ERTELIYOR. launcherNonce ile ayni gerekcede YALNIZ loopback'e verilir
        # (auth-muaf + tunelden erisilebilir bir uc; "su an tedavi suruyor" disari sizmamali).
        "sessionActive",
        # DENETIM 2026-08-09 (BILINCLI sekil degisikligi): tibbi kayit DB'si yazilabilir mi.
        # DB acilamazken seans baslatma yolu tum DB hatalarini "best-effort" sayip yutuyordu →
        # bobinler enerjileniyor, tedavi uygulaniyor, ama seans/coil-run/sensor kaydinin HICBIRI
        # yazilmiyordu (hastanin aldigi doz geriye donuk BILINEMEZ). Kayitsiz tedavi artik 503 ile
        # reddedilir; bu alan olmadan ariza ancak veteriner seans baslatmayi DENEYINCE, yani hasta
        # masadayken gorunuyordu. Bkz. api_server._kayit_db_hazir + tests/test_db_ready_gate.py.
        "dbReady",
        # D1.37 · B-3.8 (2026-10-01, BILINCLI sekil degisikligi): DB acilista acilamazsa backend artik
        # OLMUYOR, DB'siz (kisitli) aciliyor. `dbReady` false iken NEDENI ("Hasta veritabani goc bekliyor …");
        # true iken null. Yol/istisna ayrintisi tasimaz (bu uc auth-muaf). Bkz. test_acilis_DB_acilamasa_ACIL_DURDUR_yasar.
        "dbSebep",
        # DENETIM 2026-08-09 Tier 3 (BILINCLI sekil degisikligi): SURUM GORUNURLUGU.
        # `/api/health` saha teshisinin ilk duragi ama surumu HIC soylemiyordu; destek telefonda
        # "hangi surum" diye sorup operatore menu tarif etmek zorunda kaliyordu. `buildId` ise
        # surumun soyleyemedigini soyler: ayni "1.9.5" farkli paket icerigi calistirabilir
        # (yeniden yayin, yarim guncelleme, elle kopyalanmis dosya) — deger, launcher'in kurdugu
        # paketin sha256'sinin ilk 12 hanesidir (PEMF_BASE_SHA). Launcher'siz calistirmada None
        # (uydurma kimlik URETILMEZ). Bkz. tests/test_version_visibility.py.
        "version",
        "buildId",
        # YH-A4 (2026-11-16, BILINCLI sekil degisikligi · Tezgah-2 listesi 5): `paketIcerigi` = CALISAN runtime'in icerik
        # kimligi (app katmani ozeti, `_app_roots.json`); `buildId` launcher KAYDINI soyler ve yerel deneme kurulumunda
        # yayindaki paketi gosterir. Kaynaktan / eski pakette None. Bkz. tests/test_YH_A4_paket_icerigi_RUNTIME_kimligi.py.
        "paketIcerigi",
        # D1.81 · Y4 (2026-10-01, BILINCLI sekil degisikligi): ACIL DURDURMA MANDALI — kuruluyken hicbir START kabul
        # edilmez; arayuz (oturumsuz Karsilama/Giris ekranlari dahil) durumu ve "Sifirla"yi gosterir. Uzak istemci
        # yalniz `aktif`i gorur. Bkz. tests/test_estop_MANDALI_Y4_hicbir_START_gecmez.py.
        "estopMandali",
        # D1.116 · B-4.11 (2026-10-06, BILINCLI sekil degisikligi): oto-firmware durumu (eylem, gerekce, son yakma sonuc
        # kodu; D1.119 · Y16 launcher sinyali `istemciGeriAlinmali`). Eskiden yalniz servis gunlugundeydi. Yerel/LAN'a
        # ayrinti, tunel istemcisine None. Bkz. tests/test_firmware_durumu_SAGLIK_ve_DESTEK_PAKETI_D1116.py.
        "firmwareGuncelleme",
        # Y118 (2026-10-09, BILINCLI sekil degisikligi): veri klasoru AG PAYLASIMINDA mi (UNC / eslenmis ag surucusu) —
        # SQLite orada guvenilir degil; arayuz bandi bu alani gosterir. Yalniz bayrak (yol gunlukte); yerel/LAN'a bool,
        # tunel istemcisine None. Bkz. tests/test_veri_koku_AG_PAYLASIMI_uyarisi_Y118.py.
        "veriKokuAgda",
    },
    "/api/discovery": {"capabilities", "localIp", "port", "service", "tunnelUrl", "version"},
    "/api/system/info": {
        "deviceId",
        "hardwareVersion",
        "pairingCode",
        "softwareVersion",
        "stmConnected",
        "timestamp",
        "tunnelUrl",
        # 2-F incelemesi §10 #7 (D5, BILINCLI sekil eki): sensor telemetri kaydi yazilabiliyor mu {acik, hata, sonHata, yazilan,
        # atilan}. Yol tasimaz; yerel/LAN'a dict, tunel istemcisine None. Bkz. tests/test_sensor_kaydi_HATASI_gorunur_YARIM_satir_birlesmez_D5E7.py.
        "sensorKaydi",
    },
    "/api/gateway/status": {
        "bridgeConnected",
        "brokerRunning",
        # ⚠️ BILINCLI SEKIL DEGISIKLIGI 2026-10-24 (D3 T-e, Tezgâh-2 #8; yalnız-ek): ESP alt sistemi bilinçli kapalı mı
        # (Cihaz Köprüsü "Devre dışı") ve internet ÖLÇÜLMEDİ mi (servis yok / ilk ölçüm öncesi → "Bilinmiyor", "Kapalı" DEĞİL).
        "espEtkin",
        "gatewayState",
        "hotspotActive",
        "internetBilinmiyor",
        "mosquitto",
        "mqttConnected",
        "network",
        "networkOnline",
        "stmConnected",
    },
    "/api/kpi/summary": {
        "avgDurationMin",
        "coilUsage",
        "completedSessions",
        "last7Days",
        "modeDistribution",
        "stoppedSessions",
        "totalSessions",
    },
}


@pytest.fixture(scope="module")
def client():
    from servers import api_server

    return TestClient(api_server.app)


@pytest.mark.parametrize("path,expected_keys", sorted(GOLDEN_SHAPES.items()))
def test_status_endpoint_shape(client, path, expected_keys):
    r = client.get(path)
    assert r.status_code == 200, f"{path} -> HTTP {r.status_code}"
    assert set(r.json().keys()) == expected_keys, f"{path} response anahtar-kümesi DEĞİŞTİ"
