import { test, expect } from '@playwright/test'
import { mkdir } from 'node:fs/promises'
import { fileURLToPath } from 'node:url'
const screenshots = process.env.CAMPUSBITE_EVIDENCE ? process.env.CAMPUSBITE_EVIDENCE + '/screenshots/' : fileURLToPath(new URL('../../../docs/evidence/round03/screenshots/', import.meta.url))
let consoleErrors, pageErrors
test.beforeEach(async ({ page }) => {
  consoleErrors = []; pageErrors = []
  page.on('console', msg => { if (msg.type() === 'error') consoleErrors.push(msg.text()) })
  page.on('pageerror', error => pageErrors.push(error.message))
  await mkdir(screenshots, { recursive: true })
})
test.afterEach(async ({}, testInfo) => {
  await testInfo.attach('browser-console', { body: JSON.stringify({ consoleErrors, pageErrors }), contentType: 'application/json' })
  expect(pageErrors).toEqual([])
  const deliberateError = /不存在|API 失败/.test(testInfo.title)
  const unexpected = deliberateError ? consoleErrors.filter(s => !/^Failed to load resource:/.test(s)) : consoleErrors
  expect(unexpected).toEqual([])
})
async function expectedIds(page, params = '') {
  const response = await page.request.get(`/api/dishes${params ? '?' + params : ''}`)
  expect(response.ok()).toBeTruthy()
  return (await response.json()).items.map(d => d.id)
}
async function cardIds(page) {
  return page.getByTestId('dish-card').evaluateAll(cards => cards.map(card => Number(card.getAttribute('href').split('/').pop())))
}
async function checkIds(page, expected) {
  await expect(page.getByTestId('dish-card')).toHaveCount(expected.length)
  expect(await cardIds(page)).toEqual(expected)
}
async function choose(page, label, option) {
  const input = page.getByRole('combobox', { name: label, exact: true })
  await page.locator('.el-select').filter({ has: input }).click()
  await page.getByRole('option', { name: option, exact: true }).click()
  await page.getByRole('heading', { name: '美食探索', exact: true }).click()
}

test('首页加载数据库餐单并提供有效导航', async ({ page }) => {
  await page.goto('/')
  await expect(page.getByRole('heading', { name: '今天吃什么？' })).toBeVisible()
  await expect(page.getByText('30 道模拟菜品，慢慢挑一餐喜欢的。')).toBeVisible()
  await expect(page.getByTestId('dish-card')).toHaveCount(8)
  await expect(page.locator('.category-link')).toHaveCount(6)
  await page.getByTestId('dish-card').last().scrollIntoViewIfNeeded()
  await expect.poll(() => page.locator('.dish-image img').evaluateAll(images => images.every(img => img.complete && img.naturalWidth > 0))).toBeTruthy()
  await page.evaluate(() => scrollTo(0, 0))
  await page.screenshot({ path: screenshots + 'home_desktop.png', fullPage: true })
  await page.locator('.category-link').filter({ hasText: '轻食' }).click()
  await checkIds(page, await expectedIds(page, 'cuisine=' + encodeURIComponent('轻食')))
})

test('首页搜索及探索空搜索实际生效', async ({ page }) => {
  await page.goto('/')
  await page.getByRole('textbox', { name: '首页美食搜索' }).fill('面')
  await page.getByRole('button', { name: '搜索美食' }).click()
  await checkIds(page, await expectedIds(page, 'keyword=' + encodeURIComponent('面')))
  await page.getByRole('textbox', { name: '关键词', exact: true }).fill('')
  await page.getByRole('button', { name: '搜索', exact: true }).click()
  await checkIds(page, await expectedIds(page))
})

test('预算和距离筛选生效并可重置', async ({ page }) => {
  await page.goto('/explore')
  await checkIds(page, await expectedIds(page))
  await page.getByRole('textbox', { name: '预算上限', exact: true }).fill('10')
  await page.getByRole('button', { name: '应用筛选' }).click()
  await checkIds(page, await expectedIds(page, 'budget=10'))
  await page.getByRole('textbox', { name: '最大参考距离', exact: true }).fill('200')
  await page.getByRole('button', { name: '应用筛选' }).click()
  await checkIds(page, await expectedIds(page, 'budget=10&max_distance_m=200'))
  await page.getByRole('button', { name: '重置筛选', exact: true }).first().click()
  await checkIds(page, await expectedIds(page))
})

test('口味营业与预算距离组合筛选正确', async ({ page }) => {
  await page.goto('/explore')
  await checkIds(page, await expectedIds(page))
  await page.getByRole('textbox', { name: '预算上限', exact: true }).fill('15')
  await page.getByRole('textbox', { name: '最大参考距离', exact: true }).fill('500')
  await choose(page, '口味', '清淡')
  await page.getByText('仅看模拟营业中', { exact: true }).click()
  await expect(page.getByRole('checkbox', { name: '仅看模拟营业中' })).toBeChecked()
  await checkIds(page, [4, 7, 9])
})

test('评分排序与最低评分筛选生效', async ({ page }) => {
  await page.goto('/explore')
  await checkIds(page, await expectedIds(page))
  await choose(page, '排序方式', '评分从高到低')
  await checkIds(page, await expectedIds(page, 'sort=rating'))
  await page.getByRole('textbox', { name: '最低模拟评分', exact: true }).fill('4.5')
  await page.getByRole('button', { name: '应用筛选' }).click()
  await checkIds(page, await expectedIds(page, 'sort=rating&min_rating=4.5'))
})

test('清除单项口味筛选恢复完整列表', async ({ page }) => {
  await page.goto('/explore')
  await checkIds(page, await expectedIds(page))
  await choose(page, '口味', '清淡')
  await checkIds(page, await expectedIds(page, 'taste=' + encodeURIComponent('清淡')))
  const control = page.locator('.el-select').filter({ has: page.getByRole('combobox', { name: '口味', exact: true }) })
  await control.hover()
  await control.locator('.el-select__clear').click()
  await checkIds(page, await expectedIds(page))
})

test('严格忌口排除明确可能和未知风险', async ({ page }) => {
  await page.goto('/explore')
  await checkIds(page, await expectedIds(page))
  await choose(page, '严格忌口', '花生')
  await checkIds(page, await expectedIds(page, 'avoid=' + encodeURIComponent('花生')))
  const ids = await cardIds(page)
  for (const forbidden of [1, 8, 29, 30]) expect(ids).not.toContain(forbidden)
  await page.screenshot({ path: screenshots + 'explore_strict_desktop.png', fullPage: true })
  await page.screenshot({ path: screenshots + 'explore_strict_desktop_viewport.png' })
})

test('无结果显示友好提示并允许重置', async ({ page }) => {
  await page.goto('/explore?keyword=' + encodeURIComponent('不存在的菜品'))
  await expect(page.getByRole('heading', { name: '暂无匹配结果' })).toBeVisible()
  await expect(page.getByTestId('result-count')).toHaveText('0 道菜品')
  await page.getByRole('button', { name: '重置筛选', exact: true }).first().click()
  await checkIds(page, await expectedIds(page))
})

test('非法预算输入有提示且不崩溃', async ({ page }) => {
  await page.goto('/explore')
  await checkIds(page, await expectedIds(page))
  for (const invalid of ['-1', 'abc', '0']) {
    await page.getByRole('textbox', { name: '预算上限', exact: true }).fill(invalid)
    await page.getByRole('button', { name: '应用筛选' }).click()
    await expect(page.getByText('请修正筛选输入后重试')).toBeVisible()
    await expect(page.getByText('预算须为大于零的有效数值')).toBeVisible()
    await expect(page.getByTestId('dish-card')).toHaveCount(0)
  }
})

test('详情显示对应数据库记录及未知过敏原', async ({ page }) => {
  await page.goto('/dishes/1')
  await expect(page.getByRole('heading', { name: '宫保鸡丁饭', exact: true })).toBeVisible()
  await expect(page.locator('.detail-price')).toContainText('¥18')
  for (const value of ['模拟川味窗口', '虚构校园 A 区一层', '10:30–14:00 / 16:30–20:00', '¥16', '花生']) await expect(page.locator('.detail-sections')).toContainText(value)
  await page.screenshot({ path: screenshots + 'detail_desktop.png', fullPage: true })
  await page.goto('/dishes/30')
  await expect(page.getByRole('heading', { name: '模拟配方待补全饭' })).toBeVisible()
  await expect(page.locator('.detail-sections')).toContainText('未知，无法确认')
})

test('不存在的菜品显示友好页面', async ({ page }) => {
  await page.goto('/dishes/999')
  await expect(page.getByRole('heading', { name: '这道菜品不存在' })).toBeVisible()
  await expect(page.getByRole('link', { name: '探索其他美食' })).toBeVisible()
})

test('API 失败提示且重试可恢复', async ({ page }) => {
  await page.route('**/api/dishes*', route => route.abort())
  await page.goto('/explore')
  await expect(page.getByRole('heading', { name: '暂时无法加载' })).toBeVisible()
  await expect(page.getByText('服务暂时不可用，请稍后重试。')).toBeVisible()
  await page.unroute('**/api/dishes*')
  await page.getByRole('button', { name: '重试', exact: true }).click()
  await checkIds(page, await expectedIds(page))
})

test('字段缺失显示占位与未知状态', async ({ page }) => {
  await page.route('**/api/dishes/1', route => route.fulfill({ json: { item: { id: 1 }, metadata: {} } }))
  await page.goto('/dishes/1')
  await expect(page.locator('.detail-summary h1')).toHaveText('暂无数据')
  await expect(page.locator('.detail-facts')).toContainText('营业状态未知')
  await expect(page.locator('.detail-sections')).toContainText('未知，无法确认')
  const body = await page.locator('body').innerText()
  expect(body).not.toMatch(/undefined|null/)
})

test('列表字段缺失不导致卡片崩溃', async ({ page }) => {
  await page.route('**/api/dishes?*', route => route.fulfill({ json: { items: [{ id: 1 }], total: 1, options: {}, metadata: {} } }))
  await page.goto('/explore')
  await expect(page.getByTestId('dish-card')).toHaveCount(1)
  await expect(page.getByTestId('dish-card')).toContainText('暂无数据')
  await expect(page.getByTestId('dish-card')).toContainText('营业状态未知')
  expect(await page.locator('body').innerText()).not.toMatch(/undefined|null/)
})

test('数据加载中有可见状态', async ({ page }) => {
  await page.route('**/api/dishes', async route => {
    await new Promise(resolve => setTimeout(resolve, 900))
    await route.continue()
  })
  await page.goto('/', { waitUntil: 'domcontentloaded' })
  await expect(page.getByTestId('loading')).toBeVisible()
  await expect(page.getByTestId('dish-card')).toHaveCount(8)
})

test('推荐页等待提交且默认返回五条真实结果', async ({ page }) => {
  const posts = []
  page.on('request', request => { if (request.method() === 'POST') posts.push(request.url()) })
  await page.goto('/recommend')
  await expect(page.getByRole('button', { name: '生成推荐', exact: true })).toBeEnabled()
  await page.getByRole('textbox', { name: '推荐预算' }).fill('20')
  await expect(page.getByRole('heading', { name: '推荐结果', exact: true })).toBeVisible()
  await expect(page.getByTestId('dish-card')).toHaveCount(0)
  expect(posts).toEqual([])
  await page.getByRole('button', { name: '生成推荐', exact: true }).click()
  await expect(page.getByTestId('recommend-item')).toHaveCount(5)
  const expected = await page.request.post('/api/recommend', { data: { budget: 20 } })
  expect(await cardIds(page)).toEqual((await expected.json()).items.map(item => item.dish.id))
  await expect(page.getByTestId('recommend-item').first()).toContainText('所属场所模拟评分为')
  await page.screenshot({ path: screenshots + 'recommend_desktop.png', fullPage: true })
})

test('移动端四页不溢出且图片正常加载', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  for (const [path, name] of [['/', 'home'], ['/explore', 'explore'], ['/dishes/1', 'detail'], ['/recommend', 'recommend']]) {
    await page.goto(path)
    await expect(page.getByTestId('loading')).toHaveCount(0)
    if (path === '/' || path === '/explore') await expect(page.getByTestId('dish-card').first()).toBeVisible()
    if (path.startsWith('/dishes')) await expect(page.locator('.detail-summary h1')).toHaveText('宫保鸡丁饭')
    const size = await page.evaluate(() => ({ width: innerWidth, scroll: document.documentElement.scrollWidth }))
    expect(size.scroll).toBeLessThanOrEqual(size.width)
    await page.screenshot({ path: screenshots + `${name}_mobile.png`, fullPage: true })
    await page.screenshot({ path: screenshots + `${name}_mobile_viewport.png` })
  }
})
