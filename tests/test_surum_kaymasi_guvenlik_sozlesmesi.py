# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""SURUM KAYMASI — GUVENLIK SINYALI SOZLESMESI (sahip karari 2026-08-22).

SENARYO (sahip sordu): kullanici masaustu/cihaz surumunu guncelledi ama telefonda ESKI surumde
kalmak istedi — ya da tersi. Ne olmali?

OLCULEN DURUM (2026-08-22, iki yonde de): hicbir surum kapisi YOK, yeni uc de eklenmedi →
baglanti kurulur, hata cikmaz. Ama "yeni ozelliklerden mahrum" ifadesi eksikti: kaybolan sey
OZELLIK degil, GUVENLIK UYARISIYDI.

  · Telefon eski + cihaz yeni: `/session/stop` `hardware_stop_unconfirmed` alanini donuyordu;
    eski istemcide o alani okuyan kod YOK ve kontrolu `res.status === "error"` — yani tanimadigi
    her degeri BASARI sayiyor. Sonuc: bobinler HALA CALISIYORken ekranda duz "durduruldu".
  · Telefon yeni + cihaz eski: alan hic gelmiyor → uyari yine cikmiyor.

Iki yonde de ariza AYNI ve en kotu turden: SESSIZ.

KARAR (uc parca):
 1. Baglanti ASLA bloklanmaz (Android'de kurulumu isletim sistemi sorar; bloklamak uzaktan ACIL
    DURDURMAYI kalici kilitlemek olurdu — bkz. MobileUpdateGate).
 2. "BILINMIYORSA KOTUMSER" SOZLESMESI: guvenlik uyarisi YENI BIR ALANA degil, eski istemcinin de
    anladigi KANALA konur → 2xx DISI yanit (409). Eski istemci 2xx-disini YUTAMAZ.
 3. Uyari KAYBOLMAYACAK bir yere de duser: bildirim akisi + gunluk (klinik bilgisayarinin
    arayuzu paketle birlikte GUNCELDIR, yani uyari en azindan BIRINE ulasir).

Bu dosya ucunu de kilitler.
"""

from __future__ import annotations

import re
from pathlib import Path

_KOK = Path(__file__).resolve().parents[1]
_API = (_KOK / "servers" / "api_server.py").read_text(encoding="utf-8", errors="replace")


def _stop_govdesi() -> str:
    """`/session/stop` yanit kurulumunun bulundugu kesit."""
    i = _API.find('_yanit = {"status": "success", "message": "Seans durduruldu."')
    assert i > -1, "stop yanit kurulumu bulunamadi — bicim degismis, kapiyi guncelleyin"
    return _API[i : i + 4000]


def test_KRITIK_teyitsiz_durdurma_2xx_DISI_doner():
    """⚠️ EN KRITIK MADDE. 2xx donerse eski istemci sessizce 'basarili' sayar ve operatore
    bobinler calisirken 'durduruldu' gosterir — [1.1]'in duzeltmeye calistigi arizanin ta kendisi.
    207 Multi-Status DA 2xx'tir (response.ok true) → kullanilamaz."""
    g = _stop_govdesi()
    m = re.search(r"JSONResponse\(status_code=(\d+)", g)
    assert m, (
        "teyitsiz-durdurma yolunda JSONResponse(status_code=...) YOK → yanit 2xx donuyor demektir. "
        "Eski istemci uyariyi YUTAR (yalniz `status === 'error'` kontrol eder)."
    )
    kod = int(m.group(1))
    assert not (200 <= kod < 300), (
        f"teyitsiz-durdurma {kod} donuyor — 2xx `response.ok`tur, eski istemci sessizce basari sayar"
    )


def test_KRITIK_uyari_detail_alaninda_TASINIR():
    """Olculdu (pf/src/services/apiClient.ts): 2xx-disi yanitta eski istemci YALNIZ `detail`
    alanini okuyup ekrana basar. Uyari orada olmazsa eski kullanici hicbir metin gormez."""
    g = _stop_govdesi()
    assert '_yanit["detail"]' in g, (
        "yanitta `detail` YOK — eski istemcinin gosterebilecegi TEK alan odur "
        "(apiClient: showError('Sunucu Hatasi', detail))"
    )
    assert "ACİL DURDUR" in g or "ACIL DURDUR" in g, (
        "uyari metni operatore NE YAPACAGINI soylemiyor (acil durdurma yonlendirmesi yok)"
    )


def test_KRITIK_uyari_KAYBOLMAYACAK_bir_yere_de_duser():
    """3. madde: telefon eski surumdeyse ya da ekrani kimse gormuyorsa uyari yok olmasin."""
    g = _stop_govdesi()
    assert "_push_notification" in g, "teyitsiz-durdurma bildirim akisina DUSMUYOR"
    assert re.search(r"logging\.(error|critical)", g), "teyitsiz-durdurma gunluge YAZILMIYOR"


def test_KARSIT_KANIT_MUTLU_YOL_hala_2xx_ve_sekli_AYNI():
    """Asiri-genisleme korumasi: her durdurmayi 409 yapmak alarm yorgunlugu uretir ve mevcut
    cagiranlarin sozlesmesini bozar. Teyitsizlik YOKSA yanit birebir eski hâlinde kalmali."""
    g = _stop_govdesi()
    assert "if not _stop_teyitsiz:\n        return _yanit" in g, (
        "mutlu yol erken donmuyor — 409 yolu tum durdurmalara sizabilir"
    )


def test_KRITIK_yeni_istemci_409_u_AYIRT_EDER():
    """Yeni istemci 409'u genel hata sanmamali: seans kaydi GERCEKTEN kapandi, UI'da seansi
    yeniden 'acik' gostermek yanlis olurdu."""
    # ⚠️ YORUMLAR SOYULUR. Ilk yazimda duz `"409" in hook` deniyordu ve mutasyon KACTI: kararin
    # gerekcesi yorumlarda da "409" diye geciyor, yani CALISAN kod kaldirilsa bile test yesil
    # kaliyordu. Kapinin gormesi gereken sey KODDUR (17. partide C tarafinda ogrenilen ders).
    from c_soyucu import c_soy

    hook = c_soy((_KOK / "pf" / "src" / "hooks" / "useSessionControl.ts").read_text(encoding="utf-8", errors="replace"))
    assert "409" in hook, "istemci 409'u ayirt etmiyor → seans UI'da acik kalir"
    assert "onHttpError" in hook, "istemci hata govdesini okumuyor → bobin listesi gosterilemez"
    assert "hardware_stop_unconfirmed" in hook, "teyitsiz bobin listesi istemcide okunmuyor"


def test_KRITIK_hata_govdesi_cagirana_TASINIR():
    """`onHttpError` yalniz `detail` dizesini gecirseydi, cagiran yapisal bobin listesini
    METINDEN ayristirmak zorunda kalirdi (kirilgan)."""
    api = (_KOK / "pf" / "src" / "services" / "apiClient.ts").read_text(encoding="utf-8", errors="replace")
    assert re.search(r"onHttpError\?:\s*\(status: number, detail\?: string, govde\?: unknown\)", api), (
        "onHttpError hata GOVDESINI tasimiyor"
    )
    assert "onHttpError?.(response.status, detail, govdeHam)" in api, "govde cagirana gecirilmiyor"


def test_KRITIK_surum_farki_bandi_BLOKLAMAZ():
    """1. madde: fark GORUNUR olsun ama giris/acil-durdurma yolu ASLA tikanmasin."""
    yol = _KOK / "pf" / "src" / "components" / "domain" / "SurumFarkiBanner.tsx"
    assert yol.exists(), "sürüm farkı bandı yok"
    src = yol.read_text(encoding="utf-8", errors="replace")
    # Kapatilabilir olmali (kalici bir engel degil).
    assert "setKapatilan" in src, "bant kapatilamiyor — kalici engele donusur"
    # ⚠️ DONANIM CALISIRKEN gosterilmemeli (operatorun ekranini bolmez).
    #
    # GUNCELLENDI (denetim 2026-08-23, bulgu M4): eskiden burada `seansSuruyor` degiskeninin ADI
    # araniyordu ve olcu `activeTreatment.isActive`ti. O olcu EKSIKTI — bobinler SEANSSIZ da
    # calisir (AI Pro, bobin paneli, baska istemci) ve o durumda bant hastanin uzerinde ENERJILI
    # bobin varken ciziliyordu. Olcu artik deponun geri kalaniyla ayni: `useDonanimCalisiyor`
    # (= isActive || coils.some(running)); GlobalEmergencyStop / useTeardownGuard / useApkGuncelleme
    # zaten bu genis olcuyu kullaniyordu.
    #
    # ⚠️ Test artik DEGISKEN ADI degil KULLANILAN OLCU uzerinden kilitliyor: dar olcuye donus
    # (yalniz activeTreatment) kirmizi verir.
    assert "useDonanimCalisiyor" in src, (
        "bant dar olcuye (yalniz activeTreatment.isActive) donmus — bobinler SEANSSIZ da calisir "
        "ve bant hastanin uzerinde enerjili bobin varken cizilir (bulgu M4)"
    )
    assert "if (donanimCalisiyor) return null;" in src, "bant donanim calisirken gizlenmiyor"
    assert "snapshot.activeTreatment" not in src, (
        "bant kendi dar olcusunu yeniden kurmus — tek kaynak useDonanimCalisiyor olmali"
    )
    # Kancanin kendisi gercekten GENIS olcuyu uygulamali (kanca bosaltilirsa bant da bosalir):
    kanca = (_KOK / "pf" / "src" / "hooks" / "useDonanimCalisiyor.ts").read_text(encoding="utf-8", errors="replace")
    assert "activeTreatment" in kanca and "running" in kanca, (
        "useDonanimCalisiyor iki sinyalden birini kaybetmis (seans VEYA calisan bobin)"
    )
    # Bir yerlere yerlestirilmis olmali, yoksa hic gorunmez.
    shell = (_KOK / "pf" / "src" / "components" / "ui" / "AppShell.tsx").read_text(encoding="utf-8", errors="replace")
    assert "<SurumFarkiBanner />" in shell, "bant hicbir ekrana baglanmamis"


def test_KARSIT_KANIT_baglanti_SURUME_gore_REDDEDILMEZ():
    """⚠️ Pazarlik edilemez: hicbir yerde 'surum uyusmazligi → baglanma' kapisi olmamali."""
    hedefler = [
        _KOK / "pf" / "src" / "services" / "apiClient.ts",
        _KOK / "pf" / "src" / "services" / "discovery.ts",
        _KOK / "pf" / "src" / "components" / "domain" / "SurumFarkiBanner.tsx",
    ]
    yasak = re.compile(r"(surum|version).{0,40}(uyusmaz|mismatch|incompatible|reddet|block)", re.I)
    for p in hedefler:
        if not p.exists():
            continue
        for no, satir in enumerate(p.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            kirpik = satir.strip()
            if kirpik.startswith(("//", "*", "/*")):
                continue  # yorumlar KARARI anlatir, kod degildir
            assert not yasak.search(satir), (
                f"{p.name}:{no} surum uyusmazliginda baglantiyi engelliyor olabilir: {kirpik[:90]}"
            )
