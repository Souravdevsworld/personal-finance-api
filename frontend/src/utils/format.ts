import type { Money } from '../types'

const inr = new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 2 })
export const num = (v: Money | null | undefined) => Number(v ?? 0)
export const formatINR = (v: Money | null | undefined) => inr.format(num(v))
export const formatPercent = (v: Money) => `${num(v).toFixed(1)}%`

export const formatDate = (iso: string) => {
  const d = new Date(iso.length === 10 ? `${iso}T00:00:00` : iso)
  return isNaN(d.getTime()) ? iso : d.toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' })
}
export const formatMonth = (ym: string) => {
  const d = new Date(`${ym.slice(0, 7)}-01T00:00:00`)
  return isNaN(d.getTime()) ? ym : d.toLocaleDateString('en-IN', { month: 'short', year: '2-digit' })
}
// Backend accepts up to 10 integer digits and 2 decimals
export const isValidAmount = (v: string) => /^\d{1,10}(\.\d{1,2})?$/.test(v.trim()) && Number(v) > 0
export const AMOUNT_ERROR = 'Enter an amount above 0 with up to 10 digits and 2 decimals.'
export const currentMonth = () => new Date().toISOString().slice(0, 7)
export const today = () => new Date().toISOString().slice(0, 10)
