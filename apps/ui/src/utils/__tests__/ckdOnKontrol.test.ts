// Author: mertaygn, cglrgrkn
/** B5 (2026-09-03): CKD gönderim-öncesi ön-kontrol — klinik_asgari.py kuralının istemci paritesi. */
import { CKD_CEKIRDEK, CKD_MIN_ALAN, ckdOnKontrol } from "../ckdOnKontrol";

const ETIKET: Record<string, string> = { sc: "Kreatinin", bu: "Üre", sg: "İdrar öz.ağ.", al: "Albümin", hemo: "Hemoglobin" };

describe("ckdOnKontrol (B5)", () => {
  it("KRITIK: yalnız 10 bulgu düğmesi → eyleme dönük mesaj (sunucu bunu 422 ile reddediyordu, UI jenerik hata basıyordu)", () => {
    const yalnizToggle = { rbc: "normal", pc: "normal", pcc: "notpresent", ba: "notpresent", htn: "no", dm: "no", cad: "no", appet: "good", pe: "no", ane: "no" };
    const m = ckdOnKontrol(yalnizToggle, (k) => ETIKET[k] ?? k);
    expect(m).not.toBeNull();
    expect(m).toMatch(/en az 6 alan/);
    expect(m).toMatch(/şu an 10/);            // alan sayısı doğru raporlanır
    expect(m).toMatch(/Kreatinin, Üre/);       // eksik çekirdek etiketle listelenir
    expect(m).toMatch(/Bulgu düğmeleri tek başına yeterli değildir/);
  });

  it("6 sayısal alan + çekirdek (sc) → null (gönderilebilir)", () => {
    expect(ckdOnKontrol({ sg: 1.02, al: 0, su: 0, bgr: 100, bu: 30, sc: 1.0 })).toBeNull();
  });

  it("6 alan var ama ÇEKİRDEK yok → mesaj (sunucu kuralıyla parite)", () => {
    const m = ckdOnKontrol({ su: 0, bgr: 100, sod: 140, pot: 4.5, pcv: 45, wc: 8000 });
    expect(m).not.toBeNull();
    expect(m).toMatch(/böbrek işlevine dair en az bir değer/);
  });

  it("çekirdek var ama 6'dan az alan → mesaj; `explain` bayrağı alan SAYILMAZ", () => {
    const m = ckdOnKontrol({ sc: 1.0, bu: 30, explain: true });
    expect(m).not.toBeNull();
    expect(m).toMatch(/şu an 2/);
  });

  it("sabitler klinik_asgari.py ile eşlenmiş (6 / sc,bu,sg,al,hemo)", () => {
    expect(CKD_MIN_ALAN).toBe(6);
    expect([...CKD_CEKIRDEK]).toEqual(["sc", "bu", "sg", "al", "hemo"]);
  });
});
