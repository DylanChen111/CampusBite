export const text = (value, fallback = '暂无数据') => typeof value === 'string' && value.trim() ? value : fallback
export const list = (value) => Array.isArray(value) ? value.filter(v => typeof v === 'string') : []
export const money = (value) => typeof value === 'number' && Number.isFinite(value) ? `¥${value.toFixed(2).replace(/\.00$/, '')}` : '暂无数据'
export const distance = (value) => typeof value === 'number' && Number.isFinite(value) ? `${value} 米` : '暂无数据'
export const rating = (value) => typeof value === 'number' && Number.isFinite(value) ? value.toFixed(1) : '暂无数据'
export const state = (value) => ({ TRUE: '模拟营业中', FALSE: '模拟未营业', UNKNOWN: '营业状态未知' })[value] || '营业状态未知'
export const risk = (value) => Array.isArray(value) ? (list(value).join('、') || '无已声明项（模拟）') : '未知，无法确认'
export function hours(value) {
  if (!Array.isArray(value) || !value.length) return '暂无数据'
  return value.map(period => Array.isArray(period) && period.length === 2 ? `${text(period[0])}–${text(period[1])}` : '暂无数据').join(' / ')
}

export function photo(cuisine) {
  const images = { 川菜: 'sichuan', 面食: 'noodles', 米饭: 'rice', 轻食: 'salad', 早餐: 'breakfast', 夜宵: 'night' }
  return `/images/${images[cuisine] || 'rice'}.jpg`
}

export function validateFilters(filters) {
  const errors = {}
  for (const [key, label, positive] of [['budget', '预算', true], ['max_distance_m', '距离', false], ['min_rating', '评分', false]]) {
    const raw = filters[key]
    if (raw === '' || raw === null || raw === undefined) continue
    const value = Number(raw)
    if (typeof raw === 'boolean' || !String(raw).trim() || !Number.isFinite(value) || (positive ? value <= 0 : value < 0)) errors[key] = `${label}须为${positive ? '大于零的' : '非负'}有效数值`
    else if (key === 'budget' && (value >= 1000000000 || Math.abs(value * 100 - Math.round(value * 100)) > 0.00001)) errors[key] = '预算须小于十亿元且最多两位小数'
    else if (key === 'min_rating' && value > 5) errors[key] = '评分须在 0–5 之间'
  }
  return errors
}

export function queryString(filters) {
  const query = new URLSearchParams()
  for (const [key, value] of Object.entries(filters)) {
    if (Array.isArray(value)) value.forEach(item => query.append(key, item))
    else if (value !== '' && value !== null && value !== undefined && value !== false) query.set(key, String(value))
  }
  return query.toString()
}
