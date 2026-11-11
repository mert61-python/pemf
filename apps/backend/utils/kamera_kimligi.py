# -*- coding: utf-8 -*-
# Author: mertaygn, cglrgrkn
"""KABİN KAMERASI KİMLİĞİ — ad + VID/PID + aygıt yolu (KD-2, sahip kararı 2026-11-10).

OpenCV'nin MSMF arka ucu kamera İNDEKSİNİ `MFEnumDeviceSources(SOURCE_TYPE = VIDCAP)` sırasından verir; bu sıra DEĞİŞEBİLİR (KD-1'de
Pusat indeks 1 → 0 oldu, dahili kamera yer değiştirdi). Burada AYNI çağrı (ctypes, aynı süreç) ile her indeksin Windows ADI ve
sembolik bağlantısı (aygıt yolu; içinde VID/PID) okunur → seçim ve kalibrasyon KİMLİĞE bağlanır, "indeks N" varsayımı yok.
Yöntem T2B'de (`DENETIM\\t2b\\betik\\t2b_kamera.py`) gerçek donanımda doğrulandı. Windows dışı / hata → boş liste (çağıran indekse düşer
ve bunu günlüğe yazar; kimlik bilinmeyince karşılaştırma YAPILMAZ).
"""

from __future__ import annotations

import logging
import re
import sys
import threading

logger = logging.getLogger(__name__)
_kilit = threading.Lock()


def vidpid(aygit_yolu: str | None) -> str | None:
    """`\\\\?\\usb#vid_1bcf&pid_28c4&mi_00#…` → `VID_1BCF&PID_28C4`; bulunamazsa None."""
    m = re.search(r"vid_([0-9a-f]{4})&pid_([0-9a-f]{4})", str(aygit_yolu or ""), re.IGNORECASE)
    return None if m is None else f"VID_{m.group(1).upper()}&PID_{m.group(2).upper()}"


def kimlik(ad: str | None, aygit_yolu: str | None) -> dict:
    return {"ad": ad, "vidpid": vidpid(aygit_yolu), "aygit_yolu": aygit_yolu}


def msmf_kameralar() -> list[dict]:
    """[{"indeks", "ad", "vidpid", "aygit_yolu"}] — OpenCV MSMF indeks sırası. Windows dışı / hata → [] (günlük)."""
    if sys.platform != "win32":
        return []
    with _kilit:
        try:
            return _msmf_kameralar()
        except Exception:
            logger.warning("kamera kimligi: MSMF aygit listesi okunamadi", exc_info=True)
            return []


def _msmf_kameralar() -> list[dict]:  # pragma: no cover — DONANIM: gerçek Media Foundation sorgusu (tezgâhta)
    import ctypes
    import ctypes.wintypes as wt
    import uuid

    class GUID(ctypes.Structure):
        _fields_ = [("Data1", wt.DWORD), ("Data2", wt.WORD), ("Data3", wt.WORD), ("Data4", ctypes.c_ubyte * 8)]

    def guid(s):
        return GUID.from_buffer_copy(uuid.UUID(s).bytes_le)

    def vt(obj, i, restype, *argtypes):
        tablo = ctypes.cast(obj, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
        return ctypes.WINFUNCTYPE(restype, ctypes.c_void_p, *argtypes)(tablo[i])

    kaynak_turu = guid("c60ac5fe-252a-478f-a0ef-bc8fa5f7cad3")
    vidcap = guid("8ac3587a-4ae7-42d8-99e0-0a6013eef90f")
    ad_anahtari = guid("60d0e559-52f8-4fa2-bbce-acdb34a8ec01")
    bag_anahtari = guid("58f0aad8-22bf-4f8a-bb3d-d2c4978c6e2f")
    ole32, mfplat, mf = ctypes.windll.ole32, ctypes.windll.mfplat, ctypes.windll.mf
    ole32.CoInitializeEx(None, 0)  # zaten başlatılmışsa S_FALSE / RPC_E_CHANGED_MODE — ikisi de sorun değil
    if mfplat.MFStartup(0x00020070, 0) != 0:
        raise OSError("MFStartup")
    try:
        attr = ctypes.c_void_p()
        if mfplat.MFCreateAttributes(ctypes.byref(attr), 1) != 0:
            raise OSError("MFCreateAttributes")
        try:
            vt(attr, 24, ctypes.HRESULT, ctypes.POINTER(GUID), ctypes.POINTER(GUID))(
                attr, kaynak_turu, vidcap
            )  # SetGUID
            pp, n = ctypes.POINTER(ctypes.c_void_p)(), wt.UINT()
            mf.MFEnumDeviceSources.argtypes = [
                ctypes.c_void_p,
                ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p)),
                ctypes.POINTER(wt.UINT),
            ]
            if mf.MFEnumDeviceSources(attr, ctypes.byref(pp), ctypes.byref(n)) != 0:
                raise OSError("MFEnumDeviceSources")
            out = []
            try:
                for i in range(n.value):
                    act = ctypes.c_void_p(pp[i])
                    degerler = []
                    for anahtar in (ad_anahtari, bag_anahtari):
                        s, ln = wt.LPWSTR(), wt.UINT()
                        hr = vt(
                            act,
                            13,
                            ctypes.HRESULT,
                            ctypes.POINTER(GUID),
                            ctypes.POINTER(wt.LPWSTR),
                            ctypes.POINTER(wt.UINT),
                        )(act, anahtar, ctypes.byref(s), ctypes.byref(ln))  # GetAllocatedString
                        degerler.append(s.value if hr == 0 else None)
                        if hr == 0:
                            ole32.CoTaskMemFree(s)
                    vt(act, 2, wt.ULONG)(act)  # Release
                    out.append({"indeks": i, **kimlik(degerler[0], degerler[1])})
            finally:
                ole32.CoTaskMemFree(pp)
            return out
        finally:
            vt(attr, 2, wt.ULONG)(attr)
    finally:
        mfplat.MFShutdown()


def esle(secim: dict, aygitlar: list[dict]) -> tuple[int | None, str]:
    """Saklı kimliği bugünkü aygıt listesinde bul. @return (indeks | None, yol): "yol" = aygıt yolu birebir · "ad_vidpid" = yol
    değişmiş (başka USB girişi) ama ad + VID/PID TEK aygıtta · "yok" = kimlik yok / birden çok aday (kamera AÇILMAZ)."""
    yol = (secim.get("aygit_yolu") or "").lower()
    if yol:
        for a in aygitlar:
            if (a.get("aygit_yolu") or "").lower() == yol:
                return int(a["indeks"]), "yol"
    ad = (secim.get("ad") or "").strip().lower()
    vp = (secim.get("vidpid") or "").upper()
    adaylar = [
        a for a in aygitlar if (a.get("ad") or "").strip().lower() == ad and (a.get("vidpid") or "").upper() == vp
    ]
    if ad and vp and len(adaylar) == 1:
        return int(adaylar[0]["indeks"]), "ad_vidpid"
    return None, "yok"
