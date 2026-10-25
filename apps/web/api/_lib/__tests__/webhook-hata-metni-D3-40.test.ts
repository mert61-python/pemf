// Author: mertaygn, cglrgrkn
/**
 * D3.40 (B-7.3) — webhook iç hata metnini KİMLİKSİZ çağırana döndürmez (FREE_MODE'da UYKUDA; iyzico sahte, ağ yok).
 * Ölçülen (HEAD): 500 gövdesi `e.message` (eksik env adı `IYZICO_…`, PostgREST `PGRST…`, iç ağ hedefi `ECONNREFUSED 10.…`).
 */
import { describe, it, expect, beforeEach, vi } from 'vitest'

vi.mock('../iyzico.js', () => ({
  subRetrieveByToken: vi.fn(),
  subRetrieveByRef: vi.fn(),
  planMeta: vi.fn(),
  verifyWebhookSignature: vi.fn().mockReturnValue(false),
}))

import * as iyzico from '../iyzico.js'

function sahteRes() {
  const res: Record<string, unknown> = { statusCode: 0, govde: null }
  res.status = vi.fn().mockImplementation((k: number) => ((res.statusCode = k), res))
  res.json = vi.fn().mockImplementation((g: unknown) => ((res.govde = g), res))
  return res as unknown as { statusCode: number; govde: unknown } & Record<string, ReturnType<typeof vi.fn>>
}

beforeEach(() => vi.restoreAllMocks())

describe('D3.40 webhook 500 gövdesi', () => {
  it('KRİTİK: imzasız gövde + iç hata → 500 gövdesinde IYZICO_ / PGRST / ECONNREFUSED / iç adres YOK', async () => {
    vi.mocked(iyzico.subRetrieveByRef).mockRejectedValue(
      new Error('IYZICO_URI tanımsız; PGRST116 ECONNREFUSED 10.0.0.5:5432'),
    )
    const { default: handler } = await import('../../webhook.js')
    const res = sahteRes()
    await handler({ method: 'POST', body: { subscriptionReferenceCode: 'sub-d340' }, headers: {} } as never, res as never)
    expect(res.statusCode).toBe(500)
    const metin = JSON.stringify(res.govde)
    for (const sizinti of ['IYZICO_', 'PGRST', 'ECONNREFUSED', '10.0.0.5']) expect(metin).not.toContain(sizinti)
  })
})
