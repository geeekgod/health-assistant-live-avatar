const INDIAN_MOBILE_RE = /^[6-9]\d{9}$/

export function parseIndianMobile(phone: unknown): string | null {
  const digits = String(phone ?? '').replace(/\D/g, '')
  let ten = digits
  if (digits.startsWith('91') && digits.length === 12) ten = digits.slice(2)
  if (ten.length === 11 && ten.startsWith('0')) ten = ten.slice(1)
  return INDIAN_MOBILE_RE.test(ten) ? ten : null
}

export function formatIndianPhone(phone: unknown): string {
  const ten = parseIndianMobile(phone)
  return ten ? `+91${ten}` : String(phone ?? '')
}

export function formatToolPayload(payload: Record<string, unknown>): Record<string, unknown> {
  const out = { ...payload }
  if ('phone' in out && out.phone != null) {
    out.phone = formatIndianPhone(out.phone)
  }
  return out
}
