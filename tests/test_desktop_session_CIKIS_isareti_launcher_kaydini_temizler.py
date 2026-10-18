# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""MASAÜSTÜ OTURUM DEVRİ — pencerede ÇIKIŞ launcher'a bildirilir (sahip kararı 2026-10-18).

🔴 SAHA (2026-10-17, auth_session.bin kaybı): pencerede çıkış (`AuthContext.logout` → `DELETE /api/auth/desktop-session`
+ Supabase `signOut(local)` → oturum SUNUCUDA silinir) launcher'a bildirilmiyordu: launcher'ın 60 sn çekme döngüsü boş
devri `{}` "oturum yok" sayıp YOK sayıyor, diskteki "Beni hatırla" kaydı ölü jetonla kalıyordu → sonraki açılışta yenileme
reddediliyor ve kayıt SESSİZCE siliniyordu. Sahip: "pencerede Çıkış Yap → launcher da hemen çıkış durumuna geçsin".
SÖZLEŞME: DELETE sonrası GET `{"cikis": true}` (jeton YOK) döner; yeni devir (POST) işareti kaldırır; hiç devir / çıkış
olmamışsa GET `{}` (bugünkü anlam — backend yeniden başladı ≠ çıkış). LAN'dan DELETE 403 ve işaret KURULMAZ.
"""

from fastapi.testclient import TestClient

TOKEN = "eyJhbGciOiJIUzI1NiJ9.SAHTE-ACCESS-TOKEN-cikis.imza"
YENILEME = "SAHTE-REFRESH-TOKEN-cikis-7a1e"


def _yerel() -> TestClient:
    from servers import api_server

    return TestClient(api_server.app, client=("127.0.0.1", 1234))


def _temizle():
    from servers import auth_router

    auth_router._desktop_session.clear()


def test_KRITIK_pencerede_cikis_sonrasi_GET_cikis_isareti_doner_jeton_yok():
    _temizle()
    c = _yerel()
    c.post(
        "/api/auth/desktop-session", json={"access_token": TOKEN, "refresh_token": YENILEME, "email": "vet@klinik.com"}
    )
    assert c.delete("/api/auth/desktop-session").json() == {"ok": True}
    veri = c.get("/api/auth/desktop-session").json()
    assert veri == {"cikis": True}, f"cikis isareti yok — launcher pencere cikisini ogrenemez: {veri}"
    _temizle()


def test_KRITIK_yeni_devir_cikis_isaretini_kaldirir():
    _temizle()
    c = _yerel()
    c.delete("/api/auth/desktop-session")
    c.post(
        "/api/auth/desktop-session", json={"access_token": TOKEN, "refresh_token": YENILEME, "email": "b@klinik.com"}
    )
    veri = c.get("/api/auth/desktop-session").json()
    assert "cikis" not in veri and veri.get("access_token") == TOKEN, veri
    _temizle()


def test_KARSIT_hic_cikis_olmadan_GET_bos_sozluk():
    """Backend yeniden başladı / hiç devir yapılmadı → `{}` (launcher bunu çıkış SAYMAZ, kaydını korur)."""
    _temizle()
    assert _yerel().get("/api/auth/desktop-session").json() == {}


def test_KARSIT_LAN_dan_DELETE_403_ve_isaret_KURULMAZ():
    from servers import api_server

    _temizle()
    c = _yerel()
    c.post("/api/auth/desktop-session", json={"access_token": TOKEN, "refresh_token": YENILEME})
    lan = TestClient(api_server.app, client=("192.168.1.50", 1234))
    assert lan.delete("/api/auth/desktop-session").status_code == 403
    assert c.get("/api/auth/desktop-session").json().get("access_token") == TOKEN
    _temizle()
