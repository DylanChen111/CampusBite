<script setup>
import { onMounted, onBeforeUnmount, reactive, ref, watch } from 'vue'
import { Sparkles, SlidersHorizontal } from 'lucide-vue-next'
import { readApi } from '../api'
import { validateFilters } from '../format'
import DataNotice from '../components/DataNotice.vue'
import DishCard from '../components/DishCard.vue'
const preferences = reactive({ budget: '', tastes: [], max_distance_m: '', min_rating: '', meal_period: '', avoid: [], only_open: false, top_k: 5 })
const options = ref({}), metadata = ref({}), errors = ref({}), loadError = ref(''), requestError = ref('')
const loading = ref(false), submitted = ref(false), result = ref(null), stale = ref(false), ready = ref(false)
let controller, revision = 0
watch(preferences, () => {
  revision++; stale.value = submitted.value; controller?.abort(); loading.value = false
  result.value = null; requestError.value = ''; errors.value = {}
}, { flush: 'sync' })
async function load() {
  loadError.value = ''; ready.value = false
  try { const data = await readApi('/dishes'); options.value = data.options || {}; metadata.value = data.metadata; ready.value = true }
  catch (e) { loadError.value = e.message }
}
async function generate() {
  errors.value = validateFilters(preferences)
  if (Object.keys(errors.value).length) { result.value = null; return }
  controller?.abort(); controller = new AbortController()
  const signal = controller.signal, version = revision
  const body = { ...preferences }
  for (const key of ['budget', 'max_distance_m', 'min_rating']) body[key] = preferences[key] === '' ? null : Number(preferences[key])
  body.meal_period = preferences.meal_period || null
  loading.value = true; submitted.value = true; stale.value = false; requestError.value = ''; result.value = null
  try {
    const data = await readApi('/recommend', { method: 'POST', body, signal })
    if (!Array.isArray(data?.items) || !Number.isInteger(data.total_candidates) || data.total_candidates < data.items.length || data.items.some(item => !item?.dish || !Number.isInteger(item.dish.id) || !Number.isFinite(item.score) || item.score < 0 || item.score > 100 || !item.dimensions || ['T', 'P', 'D', 'R'].some(key => !Number.isFinite(item.dimensions[key]) || item.dimensions[key] < 0 || item.dimensions[key] > 100) || !Array.isArray(item.reasons) || item.reasons.some(reason => typeof reason !== 'string'))) throw new Error('推荐数据不完整，请稍后重试。')
    if (version === revision) { result.value = data; metadata.value = data.metadata || metadata.value }
  } catch (e) { if (!signal.aborted) requestError.value = e.message }
  finally { if (version === revision) loading.value = false }
}
onMounted(load)
onBeforeUnmount(() => controller?.abort())
</script>
<template>
  <div class="page-container recommend-page"><div class="page-heading"><span class="eyebrow">A LITTLE MORE YOU</span><h1>智能推荐</h1><p>这一餐，留给你的口味和预算。</p></div>
    <el-alert v-if="loadError" :title="loadError" type="error" :closable="false"><el-button @click="load">重试</el-button></el-alert>
    <div class="recommend-layout"><section class="preference-panel"><h2><SlidersHorizontal :size="19" />我的用餐偏好</h2><el-form label-position="top" @submit.prevent="generate">
      <el-form-item label="预算上限（元）" :error="errors.budget"><el-input v-model="preferences.budget" aria-label="推荐预算" inputmode="decimal" placeholder="例如 20" @input="errors = validateFilters(preferences)" /></el-form-item>
      <el-form-item label="喜欢的口味"><el-select v-model="preferences.tastes" aria-label="推荐口味" placeholder="不限口味" multiple clearable><el-option v-for="v in options.tastes || []" :key="v" :label="v" :value="v" /></el-select></el-form-item>
      <el-form-item label="最大参考距离（米）" :error="errors.max_distance_m"><el-input v-model="preferences.max_distance_m" aria-label="推荐距离" inputmode="numeric" placeholder="例如 500" @input="errors = validateFilters(preferences)" /></el-form-item>
      <el-form-item label="用餐时段"><el-select v-model="preferences.meal_period" aria-label="推荐用餐时段" placeholder="不限时段" clearable><el-option v-for="v in options.meal_periods || []" :key="v" :label="v" :value="v" /></el-select></el-form-item>
      <el-form-item label="最低场所模拟评分" :error="errors.min_rating"><el-input v-model="preferences.min_rating" aria-label="推荐最低评分" placeholder="0 至 5" inputmode="decimal" /></el-form-item>
      <el-form-item label="严格忌口 / 过敏原排除"><el-select v-model="preferences.avoid" aria-label="推荐忌口" placeholder="选择不吃的食材" multiple clearable><el-option v-for="v in options.avoid || []" :key="v" :label="v" :value="v" /></el-select></el-form-item>
      <el-checkbox v-model="preferences.only_open">仅看模拟营业中</el-checkbox>
      <el-form-item label="推荐数量"><el-radio-group v-model="preferences.top_k" aria-label="推荐数量"><el-radio-button v-for="k in [3, 4, 5]" :key="k" :value="k">Top {{ k }}</el-radio-button></el-radio-group></el-form-item>
      <el-button class="apply-button" type="primary" :loading="loading" :disabled="!ready" @click="generate"><Sparkles :size="17" />生成推荐</el-button>
    </el-form></section><section class="recommend-results" aria-live="polite">
      <h2>推荐结果</h2>
      <div v-if="loading" class="loading-area" data-testid="recommend-loading"><el-skeleton :rows="6" animated /><p>正在挑选这一餐…</p></div>
      <div v-else-if="requestError" class="empty-state"><h3>暂时无法推荐</h3><p>{{ requestError }}</p><el-button @click="generate">重新推荐</el-button></div>
      <div v-else-if="Object.keys(errors).length" class="empty-state"><h3>请修正推荐输入后重试</h3></div>
      <template v-else-if="result">
        <p class="recommend-count" data-testid="recommend-count">{{ result.items.length }} 条推荐 · {{ result.total_candidates }} 道符合硬约束的菜品</p>
        <p v-if="result.items.length && result.items.length < preferences.top_k" class="recommend-count">{{ result.message }}</p>
        <div v-if="!result.items.length" class="empty-state"><h3>暂无符合条件的推荐</h3><p>{{ result.message }}</p></div>
        <div v-else class="recommend-list"><article v-for="item in result.items" :key="item.dish.id" class="recommend-item" data-testid="recommend-item">
          <DishCard :dish="item.dish" /><div class="recommend-explanation"><strong>综合适配分 {{ item.score.toFixed(2) }}</strong><p class="score-breakdown">口味 {{ Number(item.dimensions.T).toFixed(1) }} · 价格 {{ Number(item.dimensions.P).toFixed(1) }} · 距离 {{ Number(item.dimensions.D).toFixed(1) }} · 场所评分 {{ Number(item.dimensions.R).toFixed(1) }}</p><ul><li v-for="reason in item.reasons" :key="reason">{{ reason }}</li></ul></div>
        </article></div>
      </template>
      <div v-else class="empty-state"><Sparkles :size="36" /><h3>{{ stale ? '偏好已变更' : '为这一餐做个选择' }}</h3><p>{{ stale ? '重新生成推荐，获取当前条件的结果。' : '等待你的用餐偏好。' }}</p></div>
    </section></div>
    <DataNotice :metadata="metadata" />
  </div>
</template>

<style scoped>
@media(min-width:701px){.preference-panel{position:sticky;top:16px;max-height:calc(100dvh - 32px);overflow-y:auto;scrollbar-gutter:stable}}
.recommend-results{min-width:0}.recommend-results>h2{font-size:19px;margin:10px 0 20px}.recommend-count{font-size:12px;color:#67745e;margin-bottom:16px}.recommend-list{display:grid;gap:26px}.recommend-item{display:grid;grid-template-columns:minmax(160px,230px) minmax(0,1fr);gap:20px;border-bottom:1px solid #e2e8db;padding-bottom:24px}.recommend-explanation{min-width:0;padding-top:8px}.recommend-explanation strong{color:#28734d;font-size:17px}.score-breakdown{font-size:11px;color:#7c856e;margin-top:10px;overflow-wrap:anywhere}.recommend-explanation ul{padding-left:18px;font-size:12px;color:#5c6854;line-height:1.8;margin-top:14px}.recommend-explanation li{margin-bottom:7px;overflow-wrap:anywhere}
@media(max-width:1000px){.recommend-layout{grid-template-columns:290px minmax(0,1fr);gap:25px}.recommend-item{grid-template-columns:1fr}.recommend-item .dish-card{max-width:340px}}
@media(max-width:700px){.recommend-layout{grid-template-columns:1fr}.recommend-item{grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:12px}.recommend-explanation strong{font-size:14px}.recommend-explanation ul{font-size:11px}}
</style>
