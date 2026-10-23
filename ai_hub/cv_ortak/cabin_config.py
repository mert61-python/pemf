# Author: mertaygn, cglrgrkn
"""cabin_config.py — Fantom kabin YAML loader.

Kedi (inference_cat_organ/lib/cabin_config.py) paterniyle birebir uyumlu.
TEK ArUco marker + cabin_extent_cm + qr_to_origin_cm + camera fixed_position_cm.

Anatomik eksen:
    +X lateral   +Y dorsal (yukari)   +Z Helmholtz aks (sag/kamera tarafi)
"""
from __future__ import annotations
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import yaml


_DIR = Path(__file__).parent.resolve()
#: ⚠️ ORTAK PAKETTE ORNEK YAML YOKTUR — bu yol var olmayabilir.
#: 2026-09-19 (A2): bu modul `phantom_cv/`den `cv_ortak/`a tasindi. Eskiden
#: `Path(__file__).parent` PROFILIN dizinini gosteriyordu ve `load_cabin_config(None)`
#: o profilin ornek YAML'ina dusuyordu. Iki profilin ornegi FARKLI (192 vs 206
#: satir) ve `load_cabin_config(None)` URETIMDE DORT yerden cagriliyor:
#:   apps/backend/servers/ai_router.py:985,1009 · ai_service/predictors.py:104,115
#: Bu yuzden varsayilan artik CAGIRANDAN gelir (`varsayilan_yaml`); profil kabugu
#: kendi `_DIR`ini gecirir. Kapi: tests/test_cv_ortak_tek_uygulama.py
DEFAULT_CONFIG_YAML = _DIR / "cabin_config_example.yaml"

#: Profil kimligi kabuktan gelir; ortak varsayilan notr kalir.
VARSAYILAN_CLIENT_ID = "cv_pipeline"


# Cabin frame ekseni string -> 3-vector
_AXIS_MAP: dict[str, list[float]] = {
    "+X": [1.0, 0.0, 0.0], "-X": [-1.0, 0.0, 0.0],
    "+Y": [0.0, 1.0, 0.0], "-Y": [0.0, -1.0, 0.0],
    "+Z": [0.0, 0.0, 1.0], "-Z": [0.0, 0.0, -1.0],
}


def axis_to_vector(axis_str: str) -> list[float]:
    """ '+Y' -> [0, 1, 0]. Bilinmeyen -> [0, 1, 0]. """
    return list(_AXIS_MAP.get(str(axis_str).upper(), [0.0, 1.0, 0.0]))


# -----------------------------------------------------------------------------
# Dataclass tabanli config (kedi-pattern raw dict yerine tip-guvenli)
# -----------------------------------------------------------------------------

@dataclass
class HsvRange:
    h_min: int; h_max: int
    s_min: int; s_max: int
    v_min: int; v_max: int

    def as_lower_upper(self):
        lo = np.array([self.h_min, self.s_min, self.v_min], dtype=np.uint8)
        hi = np.array([self.h_max, self.s_max, self.v_max], dtype=np.uint8)
        return lo, hi


@dataclass
class ArucoCfg:
    dict: str
    real_cm: float                        # marker bir kenar uzunlugu
    plane_offset_cm: float
    normal_axis_in_cabin: str             # "+X/-X/+Y/-Y/+Z/-Z"
    refine_corners: bool = True
    use_apriltag_corners: bool = False

    @property
    def real_mm(self) -> float:
        return self.real_cm * 10.0


@dataclass
class GeometryCfg:
    qr_to_origin_cm: list[float]          # marker -> origin vektoru (cabin frame)
    cabin_extent_cm: list[float]          # [X, Y, Z]
    axes: str                             # "x=...,y=...,z=..."

    @property
    def qr_to_origin_mm(self) -> np.ndarray:
        return np.array(self.qr_to_origin_cm, dtype=np.float64) * 10.0


@dataclass
class CameraCfg:
    fixed_position_cm: list[float] | None
    look_at_cm: list[float]
    up_cabin: list[float]
    to_marker_cm: float | None
    to_origin_cm: float | None
    intrinsics_npz: str | None
    device_index: int = 0
    fps: int = 30
    resolution: tuple[int, int] = (1920, 1080)

    @property
    def fixed_position_mm(self) -> np.ndarray | None:
        if self.fixed_position_cm is None:
            return None
        return np.array(self.fixed_position_cm, dtype=np.float64) * 10.0


@dataclass
class PhantomPlateCfg:
    plate_z_cm: float
    width_cm: float
    height_cm: float
    # HEDEF DUZLEMI (2026-09-09, sahip karari #6): kamera isini bu duzlemle kesistirilir.
    #   "Y" = YATAY yuzey (fantom/petri tabanda/tepside duruyor) -> deger = taban + kalinlik
    #   "Z" = eski davranis (kabinin DIKEY orta duzlemi); plate_z_cm kullanilir
    # Yatay yerlesimde "Z" kullanmak hedefi yanlis noktaya tasir (dikey perde ile kesisim).
    hedef_duzlem_eksen: str = "Z"
    hedef_duzlem_cm: float = 0.0

    @property
    def plate_z_mm(self) -> float:
        return self.plate_z_cm * 10.0

    @property
    def hedef_duzlem_mm(self) -> float:
        """Kesisim duzleminin mm degeri (eksen "Z" ise geriye-uyumlu plate_z)."""
        if (self.hedef_duzlem_eksen or "Z").strip().upper() == "Z":
            return self.plate_z_cm * 10.0
        return self.hedef_duzlem_cm * 10.0

    @property
    def hedef_duzlem_indeksi(self) -> int:
        """Kabin ekseni indeksi: X=0, Y=1, Z=2."""
        return {"X": 0, "Y": 1, "Z": 2}.get((self.hedef_duzlem_eksen or "Z").strip().upper(), 2)


@dataclass
class SegmentationCfg:
    cancer_blue: HsvRange
    healthy_white: HsvRange
    open_kernel: int
    close_kernel: int
    iterations: int
    adaptive_enabled: bool
    adaptive_block_size: int
    adaptive_C: int
    min_area_px: int
    max_area_px: int


@dataclass
class PnpCfg:
    method: str                           # ITERATIVE / EPNP / SQPNP
    reprojection_error_px: float
    refine_lm: bool


@dataclass
class PhantomPhysicsCfg:
    achieved_B: float
    duty_sum: float


@dataclass
class OutputCfg:
    json_enabled: bool
    json_path: str
    json_pretty: bool
    fastapi_enabled: bool
    fastapi_host: str
    fastapi_port: int
    mqtt_enabled: bool
    mqtt_broker: str
    mqtt_port: int
    mqtt_tls: bool
    mqtt_qos: int
    mqtt_keepalive: int
    mqtt_client_id: str
    mqtt_topic_state: str
    mqtt_topic_cmd: str
    mqtt_username: str | None
    mqtt_password: str | None


@dataclass
class MultiwellCfg:
    """Cok kuyucuklu plaka modu (hocanin petri v2'si, 2026-10-02). YAML'da `multiwell:` bolumu opsiyonel;
    yoksa varsayilan (plate_type None = tekil petri / YOLO kipi) — eski profil YAML'lari aynen yuklenir."""
    plate_type: int | None = None            # 12/24/48/96; None = tekil petri (YOLO)
    a1_corner: str = "auto"                  # auto / tl / tr / br / bl
    # PEMF icin kabin konumu (ArUco yoksa). Plaka sabit tutucudaysa bir kez olc:
    #   cabin = a1_cabin_mm + col_mm * col_axis_cabin + row_mm * row_axis_cabin
    a1_cabin_mm: list[float] | None = None
    col_axis_cabin: list[float] = field(default_factory=lambda: [1.0, 0.0, 0.0])
    row_axis_cabin: list[float] = field(default_factory=lambda: [0.0, -1.0, 0.0])
    # Kanser siniflandirma (goreli renk)
    cancer_frac: float = 0.02
    cancer_db: float = 8.0
    cancer_abs_b: float = -5.0
    control_healthy: list[str] = field(default_factory=list)   # orn. ["A1", "D6"]
    control_cancer: list[str] = field(default_factory=list)    # orn. ["B2"]


@dataclass
class PhantomV2Cfg:
    """Hocanin fantom v3 ayarlari (YAML anahtari geriye uyum icin `phantom_v2:`). Bolum yoksa varsayilan."""
    # Yesil Helmholtz halkasi ile olcek (ArUco yoksa varsayilan kalibrasyon)
    ring_enabled: bool = True
    ring_diameter_mm: float = 184.0          # petri plakasindan capraz kalibre; serit metreyle dogrula
    # Paralaks: tumorler halka duzleminin h mm ustunde (fantom ust yuzeyi)
    parallax_height_mm: float = 31.3         # 8 goruntuden fit (CV %4.4 -> %3.0); olculurse gir
    focal_equiv_mm: float = 26.0             # telefon ana kamera (35 mm esdeger)
    # Tumor yerlesim referansi (kimlik + dusuk cozunurluk + QC); "" = kapali
    layout_file: str = "phantom_layout_2026-10-02.json"
    # PEMF icin cercevenin kabin konumu (cerceve origin'i: halka merkezi veya fantom merkezi)
    #   kabin_xyz = origin_cabin_mm + X_mm * x_axis_cabin + Y_mm * y_axis_cabin
    origin_cabin_mm: list[float] | None = None
    x_axis_cabin: list[float] = field(default_factory=lambda: [0.0, 1.0, 0.0])
    y_axis_cabin: list[float] = field(default_factory=lambda: [0.0, 0.0, 1.0])
    # PEMF varsayilan yerlesim: CST fantom egitim kutusu (training_data_phantom_v7.csv)
    #   x [-56.6,-30.6] (26 mm kalinlik), y [-60.8,61.2] (122 mm), z [-37.7,44.3] (82 mm)
    #   fantom merkezi -> box_center ; fantom uzun ekseni (u) -> axis_u ; kisa (v) -> axis_v
    # ⚠️ EKSEN ISARETI VARSAYIMDIR (hoca §4 madde 2, laboratuvar maddesi) — sonuc `pemf_axis_sign_assumed` uyarisi tasir.
    cst_box_enabled: bool = True
    cst_box_center_mm: list[float] = field(default_factory=lambda: [-43.645, 0.215, 3.335])
    cst_axis_u: list[float] = field(default_factory=lambda: [0.0, 1.0, 0.0])
    cst_axis_v: list[float] = field(default_factory=lambda: [0.0, 0.0, 1.0])
    # Tumor renk esikleri
    navy_s_min: int = 45
    navy_v_min: int = 20
    navy_a_max: int = 12
    core_v_max: int = 35


@dataclass
class CabinConfig:
    cabin_id: str
    aruco: ArucoCfg
    geometry: GeometryCfg
    camera: CameraCfg
    phantom_plate: PhantomPlateCfg
    segmentation: SegmentationCfg
    pnp: PnpCfg
    phantom: PhantomPhysicsCfg
    output: OutputCfg
    source_path: str = ""
    # AI-2 (hoca petri v2 / fantom v3, 2026-10-12): iki bolum de OPSIYONEL — A2 tek uygulamasina tasindi (§3.4),
    # profil kopyasi alinmadi. Kapi: tests/test_cv_ortak_PLAKA_ve_FANTOM_v3_bolumleri_AI2_C1.py
    multiwell: MultiwellCfg = field(default_factory=MultiwellCfg)
    phantom_v2: PhantomV2Cfg = field(default_factory=PhantomV2Cfg)

    # ----- yardimcilar -----
    def is_camera_anchored(self) -> bool:
        """fixed_position_cm dolu mu? (kedi paterninden)"""
        return self.camera.fixed_position_cm is not None

    def _intrinsics_adayi(self) -> Path:
        """Göreli yol önce YAML dizinine, orada yoksa `ai_hub` köküne göre (T2D-2: petri / fantom / kedi YAML'ı derinlikleri farklı
        olsa da AYNI dizgeyi taşır — `cv_ortak/kalibrasyon/…`; kedi hattı `intrinsics_yolu` ile aynı kural)."""
        p = Path(self.camera.intrinsics_npz)
        if p.is_absolute():
            return p
        yaml_yani = Path(self.source_path).parent / p
        if yaml_yani.exists():
            return yaml_yani
        kok = Path(__file__).resolve().parents[1] / p
        return kok if kok.exists() else yaml_yani

    def has_intrinsics(self) -> bool:
        if not self.camera.intrinsics_npz:
            return False
        return self._intrinsics_adayi().exists()

    def intrinsics_path(self) -> Path:
        """Mutlak yol olarak intrinsics .npz dondur (yoksa exception)."""
        if not self.camera.intrinsics_npz:
            raise FileNotFoundError(
                "camera.intrinsics_npz yapilandirilmamis. "
                "Once calibrate_camera.py calistir.")
        p = self._intrinsics_adayi()
        if not p.exists():
            raise FileNotFoundError(f"Kalibrasyon .npz yok: {p}")
        return p

    def marker_position_in_cabin_mm(self) -> np.ndarray:
        """Marker merkezinin kabin frame'indeki konumu (mm).

        qr_to_origin_cm: marker -> origin vektoru
        marker_pos     = -qr_to_origin (mm)
        """
        return -self.geometry.qr_to_origin_mm

    def summary(self) -> str:
        g = self.geometry
        a = self.aruco
        c = self.camera
        return (
            f"cabin={self.cabin_id} "
            f"aruco={a.dict}/{a.real_cm}cm "
            f"qr_off={g.qr_to_origin_cm} "
            f"ext={g.cabin_extent_cm} "
            f"cam_fp={c.fixed_position_cm} "
            f"cam_to_orig={c.to_origin_cm}cm "
            f"K_npz={'yes' if self.has_intrinsics() else 'no'}"
        )


# -----------------------------------------------------------------------------
# YAML loader
# -----------------------------------------------------------------------------

def _hsv(d: dict[str, int]) -> HsvRange:
    return HsvRange(
        h_min=int(d["h_min"]), h_max=int(d["h_max"]),
        s_min=int(d["s_min"]), s_max=int(d["s_max"]),
        v_min=int(d["v_min"]), v_max=int(d["v_max"]),
    )


def _sonlu_yapilandirma(kaynak, alanlar: dict) -> None:
    """D1.E07 (İG-5.80): sayısal kabin alanları SONLU olmalı. None = isteğe bağlı alan verilmemiş (geçer)."""
    import math

    for ad, v in alanlar.items():
        if v is None:
            continue
        for x in v if isinstance(v, (list, tuple)) else [v]:
            try:
                sonlu = math.isfinite(float(x))
            except (TypeError, ValueError):
                sonlu = False
            if not sonlu:
                raise ValueError(f"Kabin yapılandırması geçersiz ({kaynak}): '{ad}' sonlu bir sayı değil ({x!r})")


#: Y73: kabin YAML'ının yanındaki kimlik dosyası (`utils.mqtt_kimlik.KABIN_KIMLIK_ADI` ile AYNI ad — ai_hub backend'i
#: içe aktarmaz; ad `tests/test_kabin_CV_mqtt_kimligi_pemf_cv_Y73.py` ile kilitli).
KABIN_KIMLIK_DOSYASI = "cabin_mqtt_kimlik.yaml"


def _kabin_mqtt_kimligi(dizin: Path) -> tuple[str | None, str | None]:
    """Y73: kabin YAML'ının dizinindeki `cabin_mqtt_kimlik.yaml` → (kullanıcı, parola); yoksa/okunamazsa (None, None).
    ⚠️ Değer hiçbir yere YAZILMAZ / loglanmaz."""
    yol = Path(dizin) / KABIN_KIMLIK_DOSYASI
    if not yol.is_file():
        return None, None
    try:
        ham = yaml.safe_load(yol.read_text(encoding="utf-8")) or {}
        kullanici, parola = ham.get("username"), ham.get("password")
    except Exception:
        return None, None
    if not (isinstance(kullanici, str) and kullanici and isinstance(parola, str) and parola):
        return None, None
    return kullanici, parola


def load_cabin_config(
    yaml_path: str | os.PathLike | None = None,
    *,
    varsayilan_yaml: str | os.PathLike | None = None,
    varsayilan_client_id: str = VARSAYILAN_CLIENT_ID,
) -> CabinConfig:
    """YAML cabin config dosyasini oku, CabinConfig dataclass'a doldur.

    yaml_path None ise default `cabin_config_example.yaml` kullanilir.
    """
    # ⚠️ Sira onemli: acik yol > cagiranin varsayilani > modul-yani (cv_ortak'ta YOK).
    p = Path(yaml_path) if yaml_path else Path(varsayilan_yaml or DEFAULT_CONFIG_YAML)
    if not p.exists():
        raise FileNotFoundError(f"Cabin config bulunamadi: {p}")
    with open(p, "r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)

    ar_r = raw["aruco"]
    geo_r = raw["geometry"]
    cam_r = raw["camera"]
    plate_r = raw["phantom_plate"]
    seg_r = raw["segmentation"]
    morph = seg_r["morphology"]
    adap = seg_r["adaptive"]
    pnp_r = raw["pnp"]
    ph_r = raw["phantom"]
    out_r = raw["output"]
    mq = out_r["mqtt"]
    # ⚠️ Y73 (sahip, S-G8): kabin MQTT kimliği YAML'ın İÇİNDE değil YANINDAKİ ayrı dosyada (`cabin_mqtt_kimlik.yaml`,
    # gitignore; `PEMF_Backend.exe --mqtt-kimlik hazirla --kabin <bu dizin>` yazar — ESP başlığı gibi). YAML'da AÇIK
    # kullanıcı adı varsa o geçerli (elle verilen kimlik ezilmez). Kabin MQTT'si `output.mqtt.enabled` ile varsayılan KAPALI.
    mqtt_kullanici, mqtt_parola = mq.get("username"), mq.get("password")
    if not mqtt_kullanici:
        mqtt_kullanici, mqtt_parola = _kabin_mqtt_kimligi(p.parent)

    aruco = ArucoCfg(
        dict=ar_r["dict"],
        real_cm=float(ar_r["real_cm"]),
        plane_offset_cm=float(ar_r.get("plane_offset_cm", 0.0)),
        normal_axis_in_cabin=str(ar_r.get("normal_axis_in_cabin", "+Z")),
        refine_corners=bool(ar_r.get("refine_corners", True)),
        use_apriltag_corners=bool(ar_r.get("use_apriltag_corners", False)),
    )

    geom = GeometryCfg(
        qr_to_origin_cm=list(geo_r["qr_to_origin_cm"]),
        cabin_extent_cm=list(geo_r["cabin_extent_cm"]),
        axes=str(geo_r.get("axes", "x=lateral,y=dorsal,z=axial")),
    )

    cam = CameraCfg(
        fixed_position_cm=(
            list(cam_r["fixed_position_cm"])
            if cam_r.get("fixed_position_cm") is not None else None
        ),
        look_at_cm=list(cam_r.get("look_at_cm", [0.0, 0.0, 0.0])),
        up_cabin=list(cam_r.get("up_cabin", [0.0, 1.0, 0.0])),
        to_marker_cm=(float(cam_r["to_marker_cm"])
                      if cam_r.get("to_marker_cm") is not None else None),
        to_origin_cm=(float(cam_r["to_origin_cm"])
                      if cam_r.get("to_origin_cm") is not None else None),
        intrinsics_npz=cam_r.get("intrinsics_npz"),
        device_index=int(cam_r.get("device_index", 0)),
        fps=int(cam_r.get("fps", 30)),
        resolution=tuple(cam_r.get("resolution", [1920, 1080])),
    )

    plate = PhantomPlateCfg(
        plate_z_cm=float(plate_r.get("plate_z_cm", 0.0)),
        # Karar #6: yaml'da verilmezse ESKI davranis ("Z" + plate_z_cm) korunur.
        hedef_duzlem_eksen=str(plate_r.get("hedef_duzlem_eksen", "Z")),
        hedef_duzlem_cm=float(plate_r.get("hedef_duzlem_cm", 0.0)),
        width_cm=float(plate_r.get("width_cm", 8.5)),
        height_cm=float(plate_r.get("height_cm", 13.0)),
    )

    seg = SegmentationCfg(
        cancer_blue=_hsv(seg_r["cancer_blue"]),
        healthy_white=_hsv(seg_r["healthy_white"]),
        open_kernel=int(morph["open_kernel"]),
        close_kernel=int(morph["close_kernel"]),
        iterations=int(morph["iterations"]),
        adaptive_enabled=bool(adap["enabled"]),
        adaptive_block_size=int(adap["block_size"]),
        adaptive_C=int(adap["C"]),
        min_area_px=int(seg_r["min_area_px"]),
        max_area_px=int(seg_r["max_area_px"]),
    )

    pnp = PnpCfg(
        method=str(pnp_r.get("method", "ITERATIVE")),
        reprojection_error_px=float(pnp_r.get("reprojection_error_px", 3.0)),
        refine_lm=bool(pnp_r.get("refine_lm", True)),
    )

    ph = PhantomPhysicsCfg(
        achieved_B=float(ph_r["achieved_B"]),
        duty_sum=float(ph_r["duty_sum"]),
    )

    out = OutputCfg(
        json_enabled=bool(out_r["json"]["enabled"]),
        json_path=out_r["json"]["path"],
        json_pretty=bool(out_r["json"].get("pretty", True)),
        fastapi_enabled=bool(out_r["fastapi"]["enabled"]),
        fastapi_host=out_r["fastapi"]["host"],
        fastapi_port=int(out_r["fastapi"]["port"]),
        mqtt_enabled=bool(mq["enabled"]),
        mqtt_broker=mq["broker"],
        mqtt_port=int(mq["port"]),
        mqtt_tls=bool(mq.get("tls", False)),
        mqtt_qos=int(mq.get("qos", 1)),
        mqtt_keepalive=int(mq.get("keepalive", 60)),
        mqtt_client_id=mq.get("client_id", varsayilan_client_id),
        mqtt_topic_state=mq["topic_state"],
        mqtt_topic_cmd=mq["topic_cmd"],
        mqtt_username=mqtt_kullanici,
        mqtt_password=mqtt_parola,
    )

    mw = _multiwell(raw.get("multiwell") or {})
    pv2 = _phantom_v2(raw.get("phantom_v2") or {})

    # ⚠️ D1.E07 (İG-5.80): `.nan` / `.inf` YAML değeri YÜKLEMEDE reddedilir. `float(.nan)` sessizce geçiyordu; B/duty
    # ya da geometri NaN iken öngörücü "makul görünen" bir doz üretiyordu (ölçüldü). Hata, bozuk ANAHTARI söyler.
    # AI-2: hocanın v2/v3 bölümlerinin sayısal alanları da (kabin yerleşimi, eksenler, halka çapı, paralaks, CST kutusu,
    # kanser eşikleri) AYNI kurala tabidir — NaN yerleşim konumu dozu sessizce "makul" bir noktaya götürürdü.
    _sonlu_yapilandirma(
        p,
        {
            "multiwell.placement.a1_cabin_mm": mw.a1_cabin_mm,
            "multiwell.placement.col_axis_cabin": mw.col_axis_cabin,
            "multiwell.placement.row_axis_cabin": mw.row_axis_cabin,
            "multiwell.cancer.frac": mw.cancer_frac,
            "multiwell.cancer.delta_b": mw.cancer_db,
            "multiwell.cancer.abs_b": mw.cancer_abs_b,
            "phantom_v2.coil_ring.diameter_mm": pv2.ring_diameter_mm,
            "phantom_v2.parallax.height_mm": pv2.parallax_height_mm,
            "phantom_v2.parallax.focal_equiv_mm": pv2.focal_equiv_mm,
            "phantom_v2.placement.origin_cabin_mm": pv2.origin_cabin_mm,
            "phantom_v2.placement.x_axis_cabin": pv2.x_axis_cabin,
            "phantom_v2.placement.y_axis_cabin": pv2.y_axis_cabin,
            "phantom_v2.cst_box.center_mm": pv2.cst_box_center_mm,
            "phantom_v2.cst_box.axis_u": pv2.cst_axis_u,
            "phantom_v2.cst_box.axis_v": pv2.cst_axis_v,
        },
    )
    _sonlu_yapilandirma(
        p,
        {
            "aruco.real_cm": aruco.real_cm,
            "aruco.plane_offset_cm": aruco.plane_offset_cm,
            "geometry.qr_to_origin_cm": geom.qr_to_origin_cm,
            "geometry.cabin_extent_cm": geom.cabin_extent_cm,
            "camera.fixed_position_cm": cam.fixed_position_cm,
            "camera.look_at_cm": cam.look_at_cm,
            "camera.up_cabin": cam.up_cabin,
            "camera.to_marker_cm": cam.to_marker_cm,
            "camera.to_origin_cm": cam.to_origin_cm,
            "phantom_plate.plate_z_cm": plate.plate_z_cm,
            "phantom_plate.hedef_duzlem_cm": plate.hedef_duzlem_cm,
            "phantom_plate.width_cm": plate.width_cm,
            "phantom_plate.height_cm": plate.height_cm,
            "pnp.reprojection_error_px": pnp.reprojection_error_px,
            "phantom.achieved_B": ph.achieved_B,
            "phantom.duty_sum": ph.duty_sum,
        },
    )

    _up_cabin_denetle(p, aruco.normal_axis_in_cabin, cam_r.get("up_cabin"))

    return CabinConfig(
        cabin_id=str(raw["cabin_id"]),
        aruco=aruco, geometry=geom, camera=cam,
        phantom_plate=plate, segmentation=seg, pnp=pnp,
        phantom=ph, output=out, source_path=str(p),
        multiwell=mw, phantom_v2=pv2,
    )


def _up_cabin_denetle(kaynak, normal: str, up_ham) -> None:
    """TD4 (tezgâh Oturum 13): tavan / taban işaretinde (normal ±Y) `camera.up_cabin` ZORUNLU ve hiçbir işarette normale
    PARALEL olamaz. Eskiden varsayılan +Y tavan işaretinin normaline paralel kalıyor, `_marker_to_cabin_R` sessizce TEKİL
    (det 0) dönüşüm kuruyordu — kabin konumları bir düzleme çöker. Hata bozuk ANAHTARI ve ne yazılacağını söyler."""
    nv = np.array(axis_to_vector(normal), dtype=np.float64)
    if up_ham is None:
        if abs(float(nv[1])) > 0.5:
            raise ValueError(
                f"Kabin yapılandırması geçersiz ({kaynak}): tavan / taban işaretinde (normal_axis_in_cabin {normal}) "
                "'camera.up_cabin' ZORUNLU — işaretin ÜST kenarının baktığı kabin eksenini yazın (ör. [0, 0, -1])"
            )
        return
    up = np.array([float(v) for v in up_ham], dtype=np.float64)
    nu = float(np.linalg.norm(up))
    if nu < 1e-9 or float(np.linalg.norm(np.cross(up / nu, nv))) < 1e-3:
        raise ValueError(
            f"Kabin yapılandırması geçersiz ({kaynak}): 'camera.up_cabin' {list(up_ham)} işaret normaline "
            f"({normal}) paralel ya da sıfır — işaretin ÜST kenarının baktığı kabin eksenini yazın"
        )


def _multiwell(m: dict) -> MultiwellCfg:
    """`multiwell:` bölümü (hocanın petri v2 `cabin_config.py::_multiwell`, birebir)."""
    d = MultiwellCfg()
    pl = m.get("placement") or {}
    cn = m.get("cancer") or {}
    return MultiwellCfg(
        plate_type=(int(m["plate_type"]) if m.get("plate_type") else None),
        a1_corner=str(m.get("a1_corner", d.a1_corner)),
        a1_cabin_mm=([float(v) for v in pl["a1_cabin_mm"]]
                     if pl.get("a1_cabin_mm") is not None else None),
        col_axis_cabin=[float(v) for v in pl.get("col_axis_cabin", d.col_axis_cabin)],
        row_axis_cabin=[float(v) for v in pl.get("row_axis_cabin", d.row_axis_cabin)],
        cancer_frac=float(cn.get("frac", d.cancer_frac)),
        cancer_db=float(cn.get("delta_b", d.cancer_db)),
        cancer_abs_b=float(cn.get("abs_b", d.cancer_abs_b)),
        control_healthy=[str(w).upper() for w in cn.get("control_healthy") or []],
        control_cancer=[str(w).upper() for w in cn.get("control_cancer") or []],
    )


def _phantom_v2(m: dict) -> PhantomV2Cfg:
    """`phantom_v2:` bölümü (hocanın fantom v3 `cabin_config.py::_phantom_v2`, birebir)."""
    d = PhantomV2Cfg()
    ring = m.get("coil_ring") or {}
    pl = m.get("placement") or {}
    tu = m.get("tumor") or {}
    cst = m.get("cst_box") or {}
    par = m.get("parallax") or {}
    return PhantomV2Cfg(
        ring_enabled=bool(ring.get("enabled", d.ring_enabled)),
        ring_diameter_mm=float(ring.get("diameter_mm", d.ring_diameter_mm)),
        parallax_height_mm=float(par.get("height_mm", d.parallax_height_mm)),
        focal_equiv_mm=float(par.get("focal_equiv_mm", d.focal_equiv_mm)),
        layout_file=str(m.get("layout_file", d.layout_file) or ""),
        origin_cabin_mm=([float(v) for v in pl["origin_cabin_mm"]]
                         if pl.get("origin_cabin_mm") is not None else None),
        x_axis_cabin=[float(v) for v in pl.get("x_axis_cabin", d.x_axis_cabin)],
        y_axis_cabin=[float(v) for v in pl.get("y_axis_cabin", d.y_axis_cabin)],
        cst_box_enabled=bool(cst.get("enabled", d.cst_box_enabled)),
        cst_box_center_mm=[float(v) for v in cst.get("center_mm", d.cst_box_center_mm)],
        cst_axis_u=[float(v) for v in cst.get("axis_u", d.cst_axis_u)],
        cst_axis_v=[float(v) for v in cst.get("axis_v", d.cst_axis_v)],
        navy_s_min=int(tu.get("navy_s_min", d.navy_s_min)),
        navy_v_min=int(tu.get("navy_v_min", d.navy_v_min)),
        navy_a_max=int(tu.get("navy_a_max", d.navy_a_max)),
        core_v_max=int(tu.get("core_v_max", d.core_v_max)),
    )


# Geriye uyum: eski API
load_config = load_cabin_config
