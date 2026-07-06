export const normalizeCode = (code) => {
  const value = String(code || '').trim().toUpperCase()
  if (value.includes('.')) return value
  if (/^\d{6}$/.test(value)) {
    if (value.startsWith('15') || value.startsWith('16') || value.startsWith('18')) {
      return `${value}.SZ`
    }
    return `${value}.SH`
  }
  return value
}
