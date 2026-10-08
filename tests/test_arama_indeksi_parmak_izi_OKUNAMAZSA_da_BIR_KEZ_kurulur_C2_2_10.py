# -*- coding: utf-8 -*-
"""C2-2.10 (2-C inceleme A2 · Y101 1cd770c) — arama indeksi parmak izi dosyası VAR ama OKUNAMIYORSA (izin) dolu indeks her
açılışta DEĞİL, BİR KEZ yeniden kurulur.

ÖLÇÜLEN (HEAD 1cd770c, `_inceleme/kayit/sonda_k7.txt`): sentetik `.patient_search_keyfp`'ye GERÇEK Windows ACL (`icacls /deny
<kullanıcı>:(R)` ya da `(RD)`) → 3 açılışta **3 yeniden kurulum** (Y101 öncesi 0). Kök: okuma hatası `_stored_fp = ""` sayılır →
kurulum → `_parmak_izini_yaz` aynı dosyanın ÜSTÜNE yazar (içerik değişir, ACL kalır) → sonraki açılış yine okuyamaz. Büyük indekste
kurulum açılışı uzatır (ölçüldü: 2000 hasta 0,86 sn, 6000 hasta 2,94 sn; hasta DB'si `HeadlessCore` kurucusunda — HTTP sunucusu,
dolayısıyla ACİL DURDUR ucu, ondan SONRA açılır) ve bu HER açılışta tekrarlar. Y101 kararı "bir kez".
DÜZELTME: parmak izi geçici dosyaya yazılıp `os.replace` ile yerine konur (yeni dosya dizinin iznini miras alır) → bir kez kurulum.
GERÇEK: `PatientDatabase` (geçici, şifresiz), GERÇEK ACL (yalnız bu testin tmp'sindeki sentetik dosya; sonda `icacls /reset` +
yeniden okuma ölçülür — kilitli artık bırakılmaz).
"""

from __future__ import annotations

import getpass
import os
import subprocess

import pytest


def _pdb(monkeypatch):
    import database.patient_database as pdb

    monkeypatch.setattr(pdb, "import_sqlcipher", lambda: None)
    monkeypatch.setattr(pdb, "get_sqlcipher_key", lambda *a, **k: "")
    monkeypatch.delenv("PEMF_ENCRYPT_AT_REST", raising=False)
    return pdb


def _say(monkeypatch, pdb):
    s = {"n": 0}
    gercek = pdb.PatientDatabase._rebuild_search_index

    def _sayan(self, cursor):
        s["n"] += 1
        return gercek(self, cursor)

    monkeypatch.setattr(pdb.PatientDatabase, "_rebuild_search_index", _sayan)
    return s


@pytest.mark.skipif(os.name != "nt", reason="Windows ACL")
def test_KRITIK_parmak_izi_OKUNAMAZKEN_uc_acilista_EN_COK_BIR_yeniden_kurulum(tmp_path, monkeypatch):
    pdb = _pdb(monkeypatch)
    yol = tmp_path / "patients.db"
    db = pdb.PatientDatabase(str(yol))
    for i in range(20):
        db.add_patient({"name": f"Hasta{i}", "owner": "S", "species": "Kedi"})
    db._reset_thread_conn()
    fp = db._key_dir / ".patient_search_keyfp"
    kullanici = os.environ.get("USERNAME") or getpass.getuser()
    s = _say(monkeypatch, pdb)
    assert subprocess.run(["icacls", str(fp), "/deny", f"{kullanici}:(R)"], capture_output=True).returncode == 0
    try:
        with pytest.raises(PermissionError):  # aparat kanıtı: süreç gerçekten okuyamıyor
            fp.read_text(encoding="utf-8")
        for _ in range(3):
            pdb.PatientDatabase(str(yol))._reset_thread_conn()
    finally:
        for g in (fp, fp.with_name(fp.name + ".tmp")):
            if g.exists():
                subprocess.run(["icacls", str(g), "/reset", "/Q"], capture_output=True)
    assert fp.read_text(encoding="utf-8").strip(), "temizlik: parmak izi geri okunabilir olmalı"
    assert s["n"] <= 1, f"parmak izi okunamazken {s['n']} açılışta {s['n']} kez yeniden kuruldu (Y101: bir kez)"


def test_KARSIT_parmak_izi_YOKSA_bir_kez_kurulur_sonra_KURULMAZ(tmp_path, monkeypatch):
    pdb = _pdb(monkeypatch)
    yol = tmp_path / "patients.db"
    db = pdb.PatientDatabase(str(yol))
    db.add_patient({"name": "Mia", "owner": "S", "species": "Kedi"})
    db._reset_thread_conn()
    fp = db._key_dir / ".patient_search_keyfp"
    fp.unlink()
    s = _say(monkeypatch, pdb)
    for _ in range(3):
        pdb.PatientDatabase(str(yol))._reset_thread_conn()
    assert s["n"] == 1 and fp.exists(), (s["n"], fp.exists())
