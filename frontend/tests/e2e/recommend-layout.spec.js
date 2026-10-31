import { test, expect } from '@playwright/test'
import { mkdir } from 'node:fs/promises'

const folder = process.env.CAMPUSBITE_EVIDENCE || '../docs/evidence/recommend_sticky'
test.beforeEach(async ({ page }) => {
  await page.goto('/recommend')
  const button = page.getByRole('button', { name: '生成推荐', exact: true })
  await expect(button).toBeEnabled()
  await button.click()
  await expect(page.getByTestId('recommend-item')).toHaveCount(5)
  await mkdir(`${folder}/screenshots`, { recursive: true })
})

test('桌面滚动结果时左侧偏好吸附且不遮挡菜品', async ({ page }) => {
  const panel = page.locator('.preference-panel')
  await page.evaluate(() => scrollTo(0, 650))
  await expect.poll(async () => (await panel.boundingBox()).y).toBeCloseTo(16, 0)
  const first = await panel.boundingBox()
  await page.mouse.move(1100, 650)
  await page.mouse.wheel(0, 300)
  await expect.poll(async () => (await panel.boundingBox()).y).toBeCloseTo(16, 0)
  const results = await page.locator('.recommend-results').boundingBox()
  expect(first.x + first.width).toBeLessThan(results.x)
  await expect(page.getByRole('heading', { name: '我的用餐偏好' })).toBeInViewport()
  await expect(page.getByRole('button', { name: '生成推荐', exact: true })).toBeInViewport()
  await page.screenshot({ path: `${folder}/screenshots/sticky_desktop.png` })
})

test('矮桌面侧栏内部可滚动且底部生成按钮可用', async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 600 })
  const panel = page.locator('.preference-panel')
  await page.evaluate(() => scrollTo(0, 650))
  await expect.poll(async () => (await panel.boundingBox()).y).toBeCloseTo(16, 0)
  const box = await panel.boundingBox()
  expect(box.height).toBeLessThanOrEqual(568)
  expect(await panel.evaluate(el => el.scrollHeight > el.clientHeight)).toBeTruthy()
  await page.mouse.move(box.x + 100, box.y + 100)
  await page.mouse.wheel(0, 700)
  await expect.poll(() => panel.evaluate(el => el.scrollTop)).toBeGreaterThan(0)
  const button = page.getByRole('button', { name: '生成推荐', exact: true })
  await expect(button).toBeInViewport()
  await button.click()
  await expect(page.getByTestId('recommend-item')).toHaveCount(5)
  await page.screenshot({ path: `${folder}/screenshots/sticky_short_desktop.png` })
})

test('手机端偏好表单正常滚走不挡推荐结果', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  const panel = page.locator('.preference-panel')
  expect(await panel.evaluate(el => getComputedStyle(el).position)).toBe('static')
  await page.getByTestId('recommend-item').first().scrollIntoViewIfNeeded()
  await expect(page.getByRole('heading', { name: '我的用餐偏好' })).not.toBeInViewport()
  await expect(page.getByTestId('recommend-item').first()).toBeInViewport()
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy()
  await page.screenshot({ path: `${folder}/screenshots/sticky_mobile.png` })
})
