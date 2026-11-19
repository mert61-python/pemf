# -*- coding: utf-8 -*-
"""TA T4 (Y137 · S-D3.9) · test belirteçleri GERÇEK ES256 imzalı — jeton kapısı JWT imzasını YERELDE (JWKS) doğrular.

Anahtar süreç başına BİR KEZ yerelde üretilir (depoda anahtar / belirteç biçimli dizge DURMAZ — gitleaks `jwt` kuralı).
`conftest.py` (`_jeton_jwks_test_anahtari`) jeton modülünün JWKS taşımasını (`servers.jeton._jwks_getir` — EN ALT kat, ağ GET'i)
`TEST_JWKS`e bağlar; imza / kid / exp / alg / iss kolları gerçek doğrulama kodunda koşar (tests/test_TA_T4_jwt_imza_JWKS.py).
"""

from __future__ import annotations

import base64
import json
import time

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature

TEST_KID = "pemf-test-es256"
_ANAHTAR = ec.generate_private_key(ec.SECP256R1())


def b64u(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode("ascii").rstrip("=")


def ec_jwk(anahtar: ec.EllipticCurvePrivateKey, kid: str) -> dict:
    n = anahtar.public_key().public_numbers()
    return {
        "kty": "EC",
        "crv": "P-256",
        "alg": "ES256",
        "use": "sig",
        "kid": kid,
        "x": b64u(n.x.to_bytes(32, "big")),
        "y": b64u(n.y.to_bytes(32, "big")),
    }


TEST_JWKS = {"keys": [ec_jwk(_ANAHTAR, TEST_KID)]}


def es256_imzala(govde: dict, *, anahtar=None, kid: str = TEST_KID, baslik: dict | None = None) -> str:
    """`govde`yi (varsayılan: test anahtarı, `kid`) ES256 ile imzalar; JWS imzası ham r‖s (64 bayt)."""
    bas = baslik if baslik is not None else {"alg": "ES256", "typ": "JWT", "kid": kid}
    girdi = b64u(json.dumps(bas).encode("utf-8")) + "." + b64u(json.dumps(govde).encode("utf-8"))
    r, s = decode_dss_signature((anahtar or _ANAHTAR).sign(girdi.encode("ascii"), ec.ECDSA(hashes.SHA256())))
    return girdi + "." + b64u(r.to_bytes(32, "big") + s.to_bytes(32, "big"))


def imzali_jwt(govde: dict) -> str:
    """Test belirteci: verilen gövde + (yoksa) 1 saat sonra biten `exp`; test anahtarıyla ES256 imzalı."""
    g = dict(govde)
    g.setdefault("exp", int(time.time()) + 3600)
    return es256_imzala(g)
