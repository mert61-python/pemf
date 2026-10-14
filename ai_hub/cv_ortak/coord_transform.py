# Author: mertaygn, cglrgrkn
"""coord_transform.py — TEK ArUco marker tabanli cabin-frame transform.

Kedi (inference_cat_organ/lib/qr.py + pose.py) paterni:
    1. detect_aruco_marker: ID en kucuk marker'i yakala (id=0 onerilen)
    2. solvePnP (4-kose <-> 4-3D marker kose)
    3. (rvec, tvec) -> kamera <- marker transformu
    4. marker -> cabin origin: qr_to_origin_cm vektoru
    5. Piksel -> cabin (mm): plate_z duzleminde ray-plane intersection
"""
from __future__ import annotations
from dataclasses import dataclass

import cv2
import numpy as np

from .cabin_config import ArucoCfg, CabinConfig, GeometryCfg, PnpCfg


# OpenCV ArUco dict enum esleme
_ARUCO_DICT_MAP = {
    "DICT_4X4_50":   cv2.aruco.DICT_4X4_50,
    "DICT_4X4_100":  cv2.aruco.DICT_4X4_100,
    "DICT_5X5_50":   cv2.aruco.DICT_5X5_50,
    "DICT_5X5_100":  cv2.aruco.DICT_5X5_100,
    "DICT_5X5_250":  cv2.aruco.DICT_5X5_250,
    "DICT_6X6_50":   cv2.aruco.DICT_6X6_50,
    "DICT_6X6_250":  cv2.aruco.DICT_6X6_250,
    "DICT_APRILTAG_36h11": cv2.aruco.DICT_APRILTAG_36h11,
}

_PNP_METHOD_MAP = {
    "EPNP":      cv2.SOLVEPNP_EPNP,
    "ITERATIVE": cv2.SOLVEPNP_ITERATIVE,
    "SQPNP":     cv2.SOLVEPNP_SQPNP,
}


class KesisimGecersiz(ValueError):
    """D1.100 (B-5.16 · İG-5.72): pikselin ışını hedef düzlemi GEÇERLİ bir noktada kesmiyor — kameranın arkasında,
    düzleme paralel ya da kesişim kabin DIŞINDA. Konum ÜRETİLMEZ (çağıran o bölgeyi "konum çözülemedi" sayar)."""


@dataclass
class CameraIntrinsics:
    K: np.ndarray                       # (3, 3)
    D: np.ndarray                       # (5,) distortion
    image_size: tuple[int, int]         # (W, H)
    rms: float                          # reproj. error (calibrate_camera.py)

    @classmethod
    def from_npz(cls, path: str) -> "CameraIntrinsics":
        npz = np.load(path)
        return cls(
            K=npz["K"].astype(np.float64),
            D=npz["D"].astype(np.float64).flatten(),
            image_size=tuple(int(x) for x in npz["image_size"]),
            rms=float(npz["rms"]),
        )


@dataclass
class MarkerDetection:
    """Tespit edilen TEK ArUco marker."""
    marker_id: int
    corners_px: np.ndarray              # (4, 2) TL, TR, BR, BL OpenCV sirasi
    center_px: tuple[float, float]
    edge_px_mean: float                 # ortalama 4 kenar piksel
    cm_per_px: float                    # marker real_cm / edge_px (approx, planar)


@dataclass
class CabinPose:
    """Marker pose'undan turetilmis cabin-frame transformu.

    rvec, tvec: kamera <- MARKER transformu (OpenCV native).
    Origin cabin frame'inde (0,0,0); marker konumu marker_pos_cabin.

    Cabin frame'inde bir nokta P_c'yi camera frame'e cevirmek:
        P_cam = R @ (P_c - marker_pos_cabin) + tvec
    veya tersi:
        P_c   = R^T @ (P_cam - tvec) + marker_pos_cabin
    """
    marker_id: int
    rvec: np.ndarray                    # (3, 1) Rodrigues
    tvec: np.ndarray                    # (3, 1) mm — kamera <- marker
    R: np.ndarray                       # (3, 3)
    reproj_error_px: float
    marker_pos_cabin_mm: np.ndarray     # (3,) marker merkez cabin-frame'de


def _marker_object_points(real_mm: float) -> np.ndarray:
    """Marker 4 kosesinin marker-LOCAL frame'inde 3D koordinati.

    OpenCV ArUco sirasi: TL, TR, BR, BL. Marker yuzeyi XY duzlemi, normal +Z.
    Marker merkezi origin (0,0,0); kenar real_mm.
    """
    half = real_mm / 2.0
    return np.array([
        [-half, +half, 0.0],   # TL
        [+half, +half, 0.0],   # TR
        [+half, -half, 0.0],   # BR
        [-half, -half, 0.0],   # BL
    ], dtype=np.float32)


def detect_aruco_marker(image_bgr: np.ndarray,
                        aruco_cfg: ArucoCfg) -> MarkerDetection | None:
    """En kucuk ID'li ArUco marker'i tespit et (kedi qr.py paterni).

    Returns: MarkerDetection veya None
    """
    if aruco_cfg.dict not in _ARUCO_DICT_MAP:
        raise ValueError(f"Bilinmeyen ArUco dict: {aruco_cfg.dict}")
    aruco_dict = cv2.aruco.getPredefinedDictionary(_ARUCO_DICT_MAP[aruco_cfg.dict])

    params = cv2.aruco.DetectorParameters()
    if aruco_cfg.refine_corners:
        params.cornerRefinementMethod = cv2.aruco.CORNER_REFINE_SUBPIX
    if aruco_cfg.use_apriltag_corners:
        params.cornerRefinementMethod = cv2.aruco.CORNER_REFINE_APRILTAG

    detector = cv2.aruco.ArucoDetector(aruco_dict, params)
    corners_all, ids, _ = detector.detectMarkers(image_bgr)
    if ids is None or len(ids) == 0:
        return None

    # Birden cok marker varsa en kucuk ID'liyi sec (kedi paterni)
    idx = int(np.argmin(ids.flatten()))
    c = corners_all[idx][0].astype(np.float32)          # (4, 2)
    edges = [float(np.linalg.norm(c[i] - c[(i + 1) % 4])) for i in range(4)]
    edge_mean = float(np.mean(edges))
    center = c.mean(axis=0)
    cm_per_px = aruco_cfg.real_cm / max(edge_mean, 1e-6)

    return MarkerDetection(
        marker_id=int(ids.flatten()[idx]),
        corners_px=c,
        center_px=(float(center[0]), float(center[1])),
        edge_px_mean=edge_mean,
        cm_per_px=cm_per_px,
    )


def solve_cabin_pose(image_bgr: np.ndarray,
                     intrinsics: CameraIntrinsics,
                     aruco_cfg: ArucoCfg,
                     geom_cfg: GeometryCfg,
                     pnp_cfg: PnpCfg) -> CabinPose | None:
    """Tek-marker solvePnP (kedi pose.py paterni).

    Adimlar:
        1. ArUco detect (en kucuk ID)
        2. Object points: marker-LOCAL frame'de 4 kose (real_mm)
        3. solvePnP (ITERATIVE / EPNP / SQPNP)
        4. opsiyonel solvePnPRefineLM
        5. Marker pos cabin-frame'de = -qr_to_origin (mm)
    """
    det = detect_aruco_marker(image_bgr, aruco_cfg)
    if det is None:
        return None

    obj_pts = _marker_object_points(aruco_cfg.real_mm)
    img_pts = det.corners_px.astype(np.float32)

    pnp_method = _PNP_METHOD_MAP.get(pnp_cfg.method.upper(),
                                     cv2.SOLVEPNP_ITERATIVE)
    ok, rvec, tvec = cv2.solvePnP(
        obj_pts, img_pts, intrinsics.K, intrinsics.D,
        flags=pnp_method,
    )
    if not ok:
        return None

    if pnp_cfg.refine_lm:
        try:
            rvec, tvec = cv2.solvePnPRefineLM(
                obj_pts, img_pts, intrinsics.K, intrinsics.D, rvec, tvec)
        except cv2.error:
            pass

    # Reprojection error
    proj, _ = cv2.projectPoints(obj_pts, rvec, tvec,
                                intrinsics.K, intrinsics.D)
    err = np.linalg.norm(img_pts - proj.reshape(-1, 2), axis=1)
    reproj = float(np.mean(err))
    if reproj > pnp_cfg.reprojection_error_px * 5:    # 5x tolerans
        # Cok zayif fit
        pass    # uyari ama yine dondur (kedi paternine sadik)

    R, _ = cv2.Rodrigues(rvec)
    marker_pos_cabin = -geom_cfg.qr_to_origin_mm

    return CabinPose(
        marker_id=det.marker_id,
        rvec=rvec, tvec=tvec, R=R,
        reproj_error_px=reproj,
        marker_pos_cabin_mm=marker_pos_cabin,
    )


def pixel_to_cabin_mm(px: tuple[float, float],
                      pose: CabinPose,
                      intrinsics: CameraIntrinsics,
                      cfg: CabinConfig) -> np.ndarray:
    """Piksel (u, v) -> cabin-frame (X_mm, Y_mm, Z_mm) ray-plane intersection.

    Yapilan donusumler:
        1. Piksel undistort -> normalize image plane
        2. Camera-frame ray (K^-1 ile)
        3. Camera -> marker frame: P_marker = R^T(P_cam - tvec)
        4. Marker -> cabin: P_cabin = R_axis @ P_marker + marker_pos_cabin (+ plane_offset) — isin VE kamera orijini
        5. Cabin'de hedef duzlemine ray-plane intersection

    Gecersiz kesisim (kameranin ARKASI, duzleme paralel, kabin DISI) -> `KesisimGecersiz` (ValueError).
    """
    u, v = px
    # 1) Undistort tek nokta
    pt = np.array([[[u, v]]], dtype=np.float32)
    und = cv2.undistortPoints(pt, intrinsics.K, intrinsics.D, P=intrinsics.K)
    u_u, v_u = und[0, 0]

    # 2) Camera-frame ray
    Kinv = np.linalg.inv(intrinsics.K)
    ray_cam = Kinv @ np.array([u_u, v_u, 1.0])
    ray_cam /= np.linalg.norm(ray_cam)

    # 3) Camera -> marker frame
    R = pose.R
    t = pose.tvec.flatten()
    Rt = R.T

    cam_origin_marker = -Rt @ t
    ray_marker = Rt @ ray_cam

    # 4) Marker -> cabin frame (rotate + translate + plane offset)
    # Marker yuzeyinin normal yonu cabin frame'de aruco.normal_axis_in_cabin
    # plane_offset_cm: marker plane -> ek z-ofset (marker plane'i kalin ise)
    plane_off_vec = np.array(
        _axis_vec(cfg.aruco.normal_axis_in_cabin), dtype=np.float64
    ) * (cfg.aruco.plane_offset_cm * 10.0)

    # ray_marker -> ray_cabin: MARKER EKSENLERI KABIN EKSENLERI DEGILDIR.
    # 2026-09-09 (karar #6): eskiden `ray_cabin = ray_marker` yaziliydi, yani marker cercevesi
    # kabin cercevesiyle AYNI varsayiliyordu. Marker arka duvarda ve normali -Z oldugundan bu
    # varsayim X ve Z eksenlerinin ISARETINI atliyor: isin ters yone gidiyor ve kesisim yanlis
    # noktada bulunuyordu. Marker DUZ yapistirildiginda (kurulum kilavuzu sarti) eksenler
    # hizalidir ama isaretler farklidir -> dogru donusum bir isaret/permutasyon matrisidir.
    R_axis = _marker_to_cabin_R(cfg)
    ray_cabin = R_axis @ ray_marker
    # ⚠️ D1.100 (B-5.16): kamera ORIJINI de ayni donusumle kabine tasinir. Eskiden `cam_origin_cabin` donduruLMEDEN
    # hesaplaniyor, donduruLMUS orijin bir satir sonra OLU bir degiskene yaziliyordu → fiziksel tutarli pozda hedef
    # ~1,5 m kayiyordu (olculdu: 1472 mm; karakterizasyon golden'inin R = I pozu kamerayi marker'in ARKASINA koydugu
    # icin bunu goremiyordu).
    cam_origin_cabin = R_axis @ cam_origin_marker + pose.marker_pos_cabin_mm + plane_off_vec

    # 5) HEDEF DUZLEMI ile ray-plane intersection (2026-09-09, karar #6)
    # Duzlem ARTIK YAPILANDIRILABILIR: fantom/petri kabinde YATAY duruyorsa dogru duzlem
    # "Y = taban + kalinlik"tir; eski kod her zaman kabin Z=0 (DIKEY orta duzlem) ile
    # kesistiriyordu ve yatay bir plakada konumu yanlis veriyordu. Yaml'da alan yoksa eski
    # davranis (eksen "Z", plate_z_cm) AYNEN korunur.
    eksen = cfg.phantom_plate.hedef_duzlem_indeksi
    duzlem = cfg.phantom_plate.hedef_duzlem_mm
    # ⚠️ D1.100 + İG-5.72: gecersiz kesisim SAYI OLARAK DONMEZ. Eskiden paralel isinda `s = 1e6` (~1 km uzak nokta),
    # kameranin ARKASINDAKI kesisim (s ≤ 0) ve kabin DISI nokta (olculdu: gercek ArUco pozunda pikselin %9'u > 5 m)
    # oldugu gibi donuyor, oneriye/surus hedefine gidebiliyordu. Kabin siniri D1.85 ile ayni olcut: kabin orijin
    # merkezli, yari boyut = `cabin_extent_cm` / 2; `|a| > yari` → DISARI.
    if abs(ray_cabin[eksen]) < 1e-9:
        raise KesisimGecersiz("isin hedef duzlemine paralel — kesisim yok")
    s = (duzlem - cam_origin_cabin[eksen]) / ray_cabin[eksen]
    if s <= 0:
        raise KesisimGecersiz(f"isin hedef duzlemini kameranin ARKASINDA kesiyor (s={s:.1f} mm)")
    p_cabin = cam_origin_cabin + s * ray_cabin
    yari = [float(v) * 10.0 / 2.0 for v in cfg.geometry.cabin_extent_cm]
    disari = [e for e, a, h in zip("xyz", p_cabin, yari) if abs(float(a)) > h]
    if disari:
        raise KesisimGecersiz(
            f"kesisim kabin DISINDA {tuple(round(float(a), 1) for a in p_cabin)} mm (eksen {''.join(disari)})"
        )
    return p_cabin.astype(np.float64)


def _marker_to_cabin_R(cfg) -> "np.ndarray":
    """Marker cercevesinden kabin cercevesine ISARET/PERMUTASYON matrisi.

    Kurulum sarti (KABIN_KURULUM_KILAVUZU): marker arka duvara DUZ yapistirilir, kenarlari kabin
    kenarlarina paralel, "ust" oku tavana bakar. O halde:
        marker-Z (yuzey normali, disa) = cfg.aruco.normal_axis_in_cabin  (arka duvarda "-Z")
        marker-Y (yukari, "ust" oku)   = cfg.camera.up_cabin             (kabin "+Y")
        marker-X                        = marker-Y x marker-Z            (sag-el kurali)
    Sutunlar bu birim vektorlerdir; carpim marker-cercevesi vektorunu kabin cercevesine tasir.

    ⚠️ Marker EGIK yapistirilirsa bu matris yetmez (tam rotasyon rvec'ten turetilmelidir) —
    kilavuz bu yuzden "duz ve paralel" sartini koyar ve kurulum kontrol adimi ekler.
    """
    z = np.array(_axis_vec(cfg.aruco.normal_axis_in_cabin), dtype=np.float64)
    y = np.array(getattr(cfg.camera, "up_cabin", [0.0, 1.0, 0.0]), dtype=np.float64)
    # y'yi z'ye dik hale getir (Gram-Schmidt) — kilavuz disi kurulumda bile tutarli kalsin.
    y = y - z * float(np.dot(y, z))
    n = float(np.linalg.norm(y))
    if n < 1e-6:
        # ⚠️ TD4 (tezgâh Oturum 13): up_cabin işaret normaline PARALEL (tavan / taban işareti, up_cabin verilmemiş →
        # varsayılan +Y) ya da sıfır. Eskiden y = +Y'ye, x = +X'e düşülüyordu → matris TEKİL (det 0): kabin konumları
        # bir düzleme çöküyor, uyarı yoktu. Yükleme (`load_cabin_config`) bunu reddeder; programatik yapılandırma burada.
        raise ValueError(
            "camera.up_cabin işaret normaline paralel ya da sıfır — tavan / taban işaretinde up_cabin, işaretin ÜST "
            "kenarının baktığı kabin eksenini vermeli (ör. [0, 0, -1])"
        )
    y = y / n
    x = np.cross(y, z)
    return np.column_stack([x, y, z])


#: TD4: düz (üst kenarı tavana bakan) duvar işaretinde R[1, 1] ≈ −0,85, 180° ters yapıştırılmışta ≈ +0,85 (saha geometrisinde
#: sentetik görüntüyle ölçüldü). 0,5 eşiği yana (90°) yatırılmış işaretle ya da hafif eğik kamerayla karar VERMEZ.
ISARET_TERS_ESIGI = 0.5


def isaret_ters_mi(pose, cfg) -> bool:
    """TD4 (tezgâh 2026-10-14: saha kabininde işaret kâğıdı 180° TERS bulundu): `_marker_to_cabin_R` işaretin ÜST kenarının
    `up_cabin`e (duvar işaretinde tavan, +Y) baktığını VARSAYAR; ters kâğıtla kabin X ve Y aynalanır (ölçüldü: her hedef
    "kabin dışında" reddedildi, neden söylenmeden). Ölçüt rvec'ten: işaretin +Y ekseninin kameradaki yönü (R'nin 2. sütunu)
    görüntüde AŞAĞIYI (kamera +y) gösteriyorsa ters. Kamera dik (görüntünün üstü tavana) varsayılır. Tavan / taban işaretinde
    (`up_cabin` yatay) kameranın "yukarısı" ölçüt değildir → False."""
    up = np.asarray(getattr(cfg.camera, "up_cabin", [0.0, 1.0, 0.0]), dtype=np.float64).reshape(3)
    n = float(np.linalg.norm(up))
    if n < 1e-9 or float(up[1]) / n < 0.9:
        return False
    R = getattr(pose, "R", None)
    if R is None:
        return False  # rotasyon taşımayan poz nesnesi (ör. test ikizi) — karar verilmez
    R = np.asarray(R, dtype=np.float64)
    return bool(R[1, 1] > ISARET_TERS_ESIGI)


def _axis_vec(axis_str: str) -> list[float]:
    """Bagimsiz: cabin axis string -> 3-vector (cabin_config.axis_to_vector mirror).
    """
    from .cabin_config import axis_to_vector
    return axis_to_vector(axis_str)


def olcekli_intrinsics(intrinsics: CameraIntrinsics, w: int, h: int) -> CameraIntrinsics:
    """K'yı (fx, fy, cx, cy — piksel) kalibrasyon çözünürlüğünden kare çözünürlüğüne ÖLÇEKLE (petri v2 kuralı, 2026-09-09).

    ⚠️ TD4: `intrinsics_npz` başka çözünürlükte üretildiyse ölçeklenmemiş K ile solvePnP mesafeyi çözünürlük oranı kadar
    yanlış verir (ölçüldü: fantom v3 2560×1440 kalibrasyonu 1280×720 karede f = 1000 kullanıyordu). Aynı çözünürlükte ya da
    boyut bilinmiyorsa (0) değişmeden döner."""
    kw, kh = (int(v) for v in intrinsics.image_size)
    if (kw, kh) == (int(w), int(h)) or kw <= 0 or kh <= 0:
        return intrinsics
    sx, sy = float(w) / float(kw), float(h) / float(kh)
    Kx = np.array(intrinsics.K, dtype=np.float64).copy()
    Kx[0, 0] *= sx
    Kx[0, 2] *= sx
    Kx[1, 1] *= sy
    Kx[1, 2] *= sy
    return CameraIntrinsics(K=Kx, D=intrinsics.D, image_size=(int(w), int(h)), rms=intrinsics.rms)


def undistort_image(image_bgr: np.ndarray,
                    intrinsics: CameraIntrinsics) -> np.ndarray:
    """Tum goruntuyu undistort et."""
    h, w = image_bgr.shape[:2]
    new_K, _ = cv2.getOptimalNewCameraMatrix(
        intrinsics.K, intrinsics.D, (w, h), 0)
    return cv2.undistort(image_bgr, intrinsics.K, intrinsics.D, None, new_K)


def approx_intrinsics_from_marker(image_bgr: np.ndarray,
                                  cfg: CabinConfig) -> CameraIntrinsics | None:
    """Eger .npz yoksa, to_marker_cm + marker.real_cm'den focal_length approx.

    Kedi `has_perspective_data` paterni: intrinsics_npz YOK ama to_marker_cm VAR
    ise pinhole approx ile gecici bir K matrisi uret.
    """
    if cfg.camera.intrinsics_npz:
        return None    # Gercek kalibrasyon var
    if cfg.camera.to_marker_cm is None:
        return None    # Approx icin yeterli veri yok
    h, w = image_bgr.shape[:2]
    det = detect_aruco_marker(image_bgr, cfg.aruco)
    if det is None:
        return None
    # Pinhole: f_px ≈ (real_mm * f_px) / Z_mm   ;  marker_size_px = f_px * real_mm / Z_mm
    # => f_px ≈ marker_size_px * Z_mm / real_mm
    z_mm = cfg.camera.to_marker_cm * 10.0
    f_px = det.edge_px_mean * z_mm / cfg.aruco.real_mm
    K = np.array([[f_px, 0,    w / 2.0],
                  [0,    f_px, h / 2.0],
                  [0,    0,    1.0]], dtype=np.float64)
    D = np.zeros(5, dtype=np.float64)
    return CameraIntrinsics(K=K, D=D, image_size=(w, h), rms=float("nan"))
