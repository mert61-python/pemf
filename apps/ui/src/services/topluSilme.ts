// Author: mertaygn
/**
 * TOPLU SİLME ONAY PAROLASI — arayüz ↔ backend tek kaynak.
 *
 * ⚠️ Backend kazara/otomatik bir POST'un onlarca kaydı silmesini engellemek için gövdede
 * bu dizgiyi ZORUNLU tutar (audit B-8.2 deseni; `delete_all`daki "DELETE_ALL" ile aynı fikir).
 * İki uç (`/api/history/delete_bulk`, `/api/patients/delete_bulk`) AYNI dizgiyi bekler.
 *
 * ⚠️ NEDEN SABİT, NEDEN HER ÇAĞRIDA ELLE YAZILMIYOR: iki ekranda iki kopya yazılırsa birinde
 * bir harf kayar ve o ekranın "Sil" düğmesi sessizce 400 alır — kullanıcıya "başarısız" der,
 * sebebini söylemez. `tests/test_toplu_silme.py` backend tarafını, `topluSilme.test.ts`
 * bu dosyanın backend ile aynı dizgiyi taşıdığını kilitler.
 */
export const TOPLU_SILME_ONAYI = "DELETE_SELECTED";
