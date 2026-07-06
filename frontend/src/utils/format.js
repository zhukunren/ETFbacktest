export const formatNumber = (num, digits = 2) => {
  const value = Number(num)
  if (!Number.isFinite(value)) return '--'
  return new Intl.NumberFormat('zh-CN', {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits
  }).format(value)
}

export const formatPercent = (num, digits = 2) => {
  const value = Number(num)
  if (!Number.isFinite(value)) return '--'
  return `${value.toFixed(digits)}%`
}
