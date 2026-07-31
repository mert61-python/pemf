/* iyzipay-node (2.0.x) tip bildirimi — paket kendi tiplerini içermez. `_types` → Vercel yok sayar. */
declare module 'iyzipay' {
  type IyzipayResult = Record<string, unknown> & {
    status?: string
    errorMessage?: string
    errorCode?: string
    token?: string
    checkoutFormContent?: string
    tokenExpireTime?: number
    referenceCode?: string
    parentReferenceCode?: string
    customerReferenceCode?: string
    subscriptionStatus?: string
    pricingPlanReferenceCode?: string
  }
  type IyzipayCallback = (err: unknown, result: IyzipayResult) => void

  interface SubscriptionCheckoutForm {
    initialize(request: Record<string, unknown>, cb: IyzipayCallback): void
    retrieve(request: { checkoutFormToken: string }, cb: IyzipayCallback): void
  }
  interface SubscriptionOps {
    cancel(request: { subscriptionReferenceCode: string }, cb: IyzipayCallback): void
    retrieve(request: { subscriptionReferenceCode: string }, cb: IyzipayCallback): void
  }

  export default class Iyzipay {
    constructor(options: { apiKey: string; secretKey: string; uri: string })
    subscriptionCheckoutForm: SubscriptionCheckoutForm
    subscription: SubscriptionOps
    static LOCALE: { TR: string; EN: string }
    static SUBSCRIPTION_INITIAL_STATUS: { ACTIVE: string; PENDING: string }
  }
}
