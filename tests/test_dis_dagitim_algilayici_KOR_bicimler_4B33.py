# -*- coding: utf-8 -*-
"""4B-3.3 (A3 inceleme, S-4B.4 `302682c1`) — dış dağıtım algılayıcısı yaygın dağıtım biçimlerini ve `needs:` atlamalarını GÖRMÜYOR.

`tests/test_ci_DIS_DAGITIM_isi_TEST_onkosullu_S4B4.py::korumasiz_dagitim_isleri` "dış dağıtım servisine yükleyen hiçbir CI işi test
süitini atlayamaz" iddiasının ölçüm aracıdır. Ölçüldü (HEAD `0ef16a1e`): bu projenin kendi kanallarına denk gelen biçimler (Expo `eas
submit` / `--auto-submit` / `eas update`, `amondnet/vercel-action`, `ncipollo/release-action`, `fastlane supply`, …) hiç dağıtım
sayılmıyor; `needs: [test]` olan iş, test işi `continue-on-error`/`if: false`/`pytest … || true`/yalnız `pip install pytest` olsa da ya da
dağıtım işi `if: always()` ile test düşse de koşsa da "korumalı" sayılıyor. Geçici iş akışıyla gerçek kapı YEŞİL kaldı (`kayit/
k2_s4b4_gecici_sonda.txt`). Ters yönde dolaylı zincir (yayın → derle → test) yanlış KIRMIZI.

Kapı GERÇEK algılayıcı işlevini sentetik iş akışı belgeleriyle çağırır (ağ yok).
"""

from __future__ import annotations

import pytest
from test_ci_DIS_DAGITIM_isi_TEST_onkosullu_S4B4 import korumasiz_dagitim_isleri

TEST_IS = {"runs-on": "ubuntu-latest", "steps": [{"run": "python -m pytest tests -q"}]}
ALTOOL = {"run": "xcrun altool --upload-app -f a.ipa"}


def _belge(adim: dict, needs=None, is_ek: dict | None = None, test_is: dict | None = None) -> dict:
    yayin = {"runs-on": "ubuntu-latest", "steps": [adim], **(is_ek or {})}
    if needs:
        yayin["needs"] = needs
    return {"jobs": {"test": test_is or TEST_IS, "yayin": yayin}}


DAGITIM_BICIMLERI = {
    "twine upload": {"run": "twine upload dist/*"},
    "npm publish": {"run": "npm publish --access public"},
    "eas submit": {"run": "npx eas-cli submit -p ios --latest"},
    "eas build --auto-submit": {"run": "eas build -p android --auto-submit"},
    "eas update (OTA)": {"run": "eas update --branch production --message x"},
    "fastlane supply": {"run": "bundle exec fastlane supply --aab app.aab"},
    "upload_to_play_store": {"run": "fastlane run upload_to_play_store aab:app.aab"},
    "firebase appdistribution": {"run": "firebase appdistribution:distribute app.apk --app 1:2:android:3"},
    "ncipollo/release-action": {"uses": "ncipollo/release-action@v1"},
    "actions/upload-release-asset": {"uses": "actions/upload-release-asset@v1"},
    "amondnet/vercel-action": {"uses": "amondnet/vercel-action@v25"},
    "vercel (ciplak)": {"run": "npx vercel --token $T"},
    "scp": {"run": "scp base.zip deploy@sunucu.invalid:/srv/"},
    "rsync": {"run": "rsync -avz dist/ deploy@sunucu.invalid:/var/www/"},
    "curl -T": {"run": "curl -T base.zip https://depo.invalid/up/"},
    "curl --upload-file": {"run": "curl --upload-file base.zip https://depo.invalid/up/"},
    "aws s3 sync": {"run": "aws s3 sync dist/ s3://pemf-yayin/"},
}

ETKISIZ_KORUMA = {
    "test isi continue-on-error": _belge(ALTOOL, ["test"], test_is={**TEST_IS, "continue-on-error": True}),
    "test isi if: false": _belge(ALTOOL, ["test"], test_is={**TEST_IS, "if": False}),
    "pytest adimi continue-on-error": _belge(
        ALTOOL, ["test"], test_is={"runs-on": "u", "steps": [{"run": "pytest tests", "continue-on-error": True}]}
    ),
    "pytest || true": _belge(ALTOOL, ["test"], test_is={"runs-on": "u", "steps": [{"run": "pytest tests || true"}]}),
    "yalniz pip install pytest": _belge(
        ALTOOL, ["test"], test_is={"runs-on": "u", "steps": [{"run": "pip install pytest"}]}
    ),
    "pytest --collect-only": _belge(
        ALTOOL, ["test"], test_is={"runs-on": "u", "steps": [{"run": "pytest --collect-only -q"}]}
    ),
    "yayin if: always()": _belge(ALTOOL, ["test"], is_ek={"if": "${{ always() }}"}),
    "yayin if: !cancelled()": _belge(ALTOOL, ["test"], is_ek={"if": "${{ !cancelled() }}"}),
}


@pytest.mark.parametrize("ad", sorted(DAGITIM_BICIMLERI))
def test_KRITIK_korumasiz_dagitim_bicimi_ALGILANIR(ad):
    assert korumasiz_dagitim_isleri(_belge(DAGITIM_BICIMLERI[ad])) == ["yayin"], (
        f"'{ad}' dağıtım adımı test işine bağlı DEĞİL ama algılayıcı görmüyor (Y30 dışı yayın yolu kapıdan geçer)"
    )


@pytest.mark.parametrize("ad", sorted(ETKISIZ_KORUMA))
def test_KRITIK_etkisiz_test_onkosulu_KORUMA_sayilmaz(ad):
    assert korumasiz_dagitim_isleri(ETKISIZ_KORUMA[ad]) == ["yayin"], (
        f"'{ad}': `needs: test` var ama test düşse de dağıtım koşar — algılayıcı korumalı sayıyor"
    )


def test_KARSIT_dolayli_zincir_KORUMALI():
    belge = {
        "jobs": {
            "test": TEST_IS,
            "derle": {"runs-on": "u", "needs": ["test"], "steps": [{"run": "make"}]},
            "yayin": {"runs-on": "u", "needs": ["derle"], "steps": [ALTOOL]},
        }
    }
    assert korumasiz_dagitim_isleri(belge) == [], "yayın → derle → test zinciri korumalı; yanlış kırmızı"


def test_KARSIT_dogrudan_korumali_ve_yorum_yanlis_kirmizi_vermez():
    assert korumasiz_dagitim_isleri(_belge(ALTOOL, ["test"])) == []
    assert (
        korumasiz_dagitim_isleri({"jobs": {"x": {"steps": [{"run": "pip install twine-olmayan-araclar && make"}]}}})
        == []
    )
    import yaml

    yorumda = yaml.safe_load(
        "jobs:\n  x:\n    steps:\n      - run: echo hazir  # xcrun altool, eas submit burada degil\n"
    )
    assert korumasiz_dagitim_isleri(yorumda) == []
    assert korumasiz_dagitim_isleri({"jobs": {"x": {"steps": [{"run": "pip install ruff && ruff check ."}]}}}) == []
