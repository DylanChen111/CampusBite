import { test } from 'node:test'
import assert from 'node:assert/strict'
import { distance, hours, list, money, queryString, rating, risk, state, text, validateFilters } from '../src/format.js'
import { readApi } from '../src/api.js'

test('missing display fields use friendly placeholders', () => {
  assert.equal(text(undefined), '暂无数据')
  assert.equal(money(undefined), '暂无数据')
  assert.equal(distance(null), '暂无数据')
  assert.equal(rating(NaN), '暂无数据')
  assert.deepEqual(list(null), [])
  assert.equal(hours(null), '暂无数据')
})
test('unknown risk and business states are not converted to safe/open', () => {
  assert.equal(state('UNKNOWN'), '营业状态未知')
  assert.equal(state(undefined), '营业状态未知')
  assert.equal(state('FALSE'), '模拟未营业')
  assert.equal(risk(null), '未知，无法确认')
  assert.equal(risk([]), '无已声明项（模拟）')
})
test('price and hours formatting preserve actual values', () => {
  assert.equal(money(3.5), '¥3.50')
  assert.equal(money(18), '¥18')
  assert.equal(hours([['10:30', '14:00'], ['16:30', '20:00']]), '10:30–14:00 / 16:30–20:00')
})
test('invalid and empty budgets validated without crash', () => {
  for (const value of [-1, 0, 'abc', Infinity, true, '  ', 1.234]) assert.ok(validateFilters({ budget: value }).budget)
  assert.deepEqual(validateFilters({ budget: '' }), {})
  assert.deepEqual(validateFilters({ budget: '15.50' }), {})
})
test('distance and rating have valid boundaries', () => {
  assert.ok(validateFilters({ max_distance_m: -1 }).max_distance_m)
  assert.ok(validateFilters({ min_rating: 5.1 }).min_rating)
  assert.deepEqual(validateFilters({ max_distance_m: 0, min_rating: 5 }), {})
})
test('query keeps repeated restrictions and skips empty fields', () => {
  const query = new URLSearchParams(queryString({ keyword: '', budget: '', only_open: true, avoid: ['花生', '大豆'] }))
  assert.equal(query.get('only_open'), 'true')
  assert.deepEqual(query.getAll('avoid'), ['花生', '大豆'])
  assert.equal(query.has('budget'), false)
})

test('recommend POST sends actual preferences as JSON', async () => {
  const original = globalThis.fetch
  try {
    globalThis.fetch = async (url, options) => {
      assert.equal(url, '/api/recommend')
      assert.equal(options.method, 'POST')
      assert.equal(options.headers['Content-Type'], 'application/json')
      assert.deepEqual(JSON.parse(options.body), { budget: 20, tastes: ['清淡'], top_k: 3 })
      return { ok: true, json: async () => ({ items: [] }) }
    }
    assert.deepEqual(await readApi('/recommend', { method: 'POST', body: { budget: 20, tastes: ['清淡'], top_k: 3 } }), { items: [] })
  } finally { globalThis.fetch = original }
})
test('existing GET remains readable after POST support', async () => {
  const original = globalThis.fetch
  try {
    globalThis.fetch = async (url, options) => {
      assert.equal(url, '/api/dishes'); assert.equal(options.method, 'GET')
      assert.equal(options.body, undefined)
      return { ok: true, json: async () => ({ items: [{ id: 1 }] }) }
    }
    assert.deepEqual(await readApi('/dishes'), { items: [{ id: 1 }] })
  } finally { globalThis.fetch = original }
})
test('API errors and unreadable response have friendly messages', async () => {
  const original = globalThis.fetch
  try {
    globalThis.fetch = async () => ({ ok: false, status: 503, json: async () => ({ error: { message: '暂不可用' } }) })
    await assert.rejects(readApi('/recommend', { method: 'POST', body: {} }), /暂不可用/)
    globalThis.fetch = async () => ({ json: async () => { throw new Error('bad JSON') } })
    await assert.rejects(readApi('/recommend'), /无法读取的数据/)
  } finally { globalThis.fetch = original }
})
