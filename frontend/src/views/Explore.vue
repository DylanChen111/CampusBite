<script setup>
import { computed, onBeforeUnmount, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Search, SlidersHorizontal, RotateCcw } from 'lucide-vue-next'
import { readApi } from '../api'
import { queryString, validateFilters } from '../format'
import DishCard from '../components/DishCard.vue'
import DataNotice from '../components/DataNotice.vue'
import RequestState from '../components/RequestState.vue'

const route = useRoute(), router = useRouter()
const defaults = () => ({ keyword: '', budget: '', taste: '', cuisine: '', max_distance_m: '', min_rating: '', meal_period: '', only_open: false, sort: 'id', avoid: [] })
const filters = reactive(defaults())
const data = ref({ items: [], total: 0, options: {}, metadata: {} })
const loading = ref(false), error = ref(''), errors = ref({})
let request
const visible = computed(() => !loading.value && !error.value && !Object.keys(errors.value).length)

async function load() {
  request?.abort()
  const current = new AbortController(); request = current
  loading.value = true; error.value = ''
  try {
    const result = await readApi(`/dishes?${queryString(filters)}`, { signal: current.signal })
    if (!Array.isArray(result.items)) throw new Error('餐饮列表格式不完整，请重试。')
    if (!current.signal.aborted) data.value = { ...result, total: result.total ?? result.items.length }
  } catch (e) { if (!current.signal.aborted) error.value = e.message }
  finally { if (!current.signal.aborted) loading.value = false }
}
async function apply() {
  errors.value = validateFilters(filters)
  if (Object.keys(errors.value).length) { request?.abort(); loading.value = false; return }
  const query = {}
  for (const [key, value] of Object.entries(filters)) {
    if (Array.isArray(value) ? value.length : value !== '' && value !== false && value !== undefined && value !== null) query[key] = Array.isArray(value) ? value : String(value)
  }
  if (JSON.stringify(query) === JSON.stringify(route.query)) await load()
  else await router.replace({ path: '/explore', query })
}
async function reset() {
  Object.assign(filters, defaults()); errors.value = {}
  if (Object.keys(route.query).length) await router.replace('/explore')
  else await load()
}
watch(() => route.query, (query) => {
  Object.assign(filters, defaults())
  for (const key of Object.keys(filters)) {
    if (key === 'avoid') filters.avoid = query.avoid ? (Array.isArray(query.avoid) ? query.avoid : [query.avoid]) : []
    else if (key === 'only_open') filters.only_open = query.only_open === 'true'
    else if (query[key] !== undefined) filters[key] = Array.isArray(query[key]) ? query[key][0] : query[key]
  }
  errors.value = validateFilters(filters)
  if (!Object.keys(errors.value).length) load()
}, { immediate: true })
onBeforeUnmount(() => request?.abort())
</script>
<template>
  <div class="page-container explore-page">
    <div class="page-heading"><span class="eyebrow">FIND YOUR NEXT BITE</span><h1>美食探索</h1><p>按预算和口味，把这一餐选得刚刚好。</p></div>
    <form class="explore-search" @submit.prevent="apply"><Search :size="20" /><el-input v-model="filters.keyword" aria-label="关键词" placeholder="搜索菜品、场所、菜系或口味" clearable @clear="apply" /><el-button type="primary" native-type="submit">搜索</el-button></form>
    <div class="explore-layout">
      <aside class="filter-panel"><div class="filter-title"><h2><SlidersHorizontal :size="18" />筛选条件</h2><el-tooltip content="重置筛选"><button class="icon-button" type="button" aria-label="重置筛选" @click="reset"><RotateCcw :size="17" /></button></el-tooltip></div>
        <el-form label-position="top" @submit.prevent="apply">
          <el-form-item label="预算上限（元）" :error="errors.budget"><el-input v-model="filters.budget" aria-label="预算上限" inputmode="decimal" placeholder="不限" @keyup.enter="apply" /></el-form-item>
          <el-form-item label="菜系"><el-select v-model="filters.cuisine" aria-label="菜系" placeholder="全部菜系" clearable @change="apply"><el-option v-for="v in data.options?.cuisines || []" :key="v" :label="v" :value="v" /></el-select></el-form-item>
          <el-form-item label="口味"><el-select v-model="filters.taste" aria-label="口味" placeholder="全部口味" clearable @change="apply"><el-option v-for="v in data.options?.tastes || []" :key="v" :label="v" :value="v" /></el-select></el-form-item>
          <el-form-item label="最大参考距离（米）" :error="errors.max_distance_m"><el-input v-model="filters.max_distance_m" aria-label="最大参考距离" inputmode="numeric" placeholder="不限" @keyup.enter="apply" /></el-form-item>
          <el-form-item label="最低模拟评分" :error="errors.min_rating"><el-input v-model="filters.min_rating" aria-label="最低模拟评分" inputmode="decimal" placeholder="0–5" @keyup.enter="apply" /></el-form-item>
          <el-form-item label="用餐时段"><el-select v-model="filters.meal_period" aria-label="用餐时段" placeholder="全部时段" clearable @change="apply"><el-option v-for="v in data.options?.meal_periods || []" :key="v" :label="v" :value="v" /></el-select></el-form-item>
          <el-form-item label="严格忌口 / 过敏原排除"><el-select v-model="filters.avoid" aria-label="严格忌口" placeholder="选择不吃的食材" multiple clearable @change="apply"><el-option v-for="v in data.options?.avoid || []" :key="v" :label="v" :value="v" /></el-select><p class="field-note">含有、可能含有及信息未知的菜品均排除；不代表现实安全保证。</p></el-form-item>
          <el-checkbox v-model="filters.only_open" @change="apply">仅看模拟营业中</el-checkbox>
          <el-button class="apply-button" type="primary" @click="apply">应用筛选</el-button>
        </el-form>
      </aside>
      <section class="results-area"><div class="result-toolbar"><h2>餐饮列表 <span v-if="visible" data-testid="result-count">{{ data.total }} 道菜品</span></h2><el-select v-model="filters.sort" aria-label="排序方式" @change="apply"><el-option label="默认排序" value="id" /><el-option label="价格从低到高" value="price" /><el-option label="距离从近到远" value="distance" /><el-option label="评分从高到低" value="rating" /></el-select></div>
        <el-alert v-if="Object.keys(errors).length" title="请修正筛选输入后重试" type="error" :closable="false" role="alert" />
        <RequestState :loading="loading" :error="error" :empty="visible && !data.items.length" @retry="load" @reset="reset" />
        <div v-if="visible && data.items.length" class="dish-grid explore-grid"><DishCard v-for="dish in data.items" :key="dish.id" :dish="dish" /></div>
      </section>
    </div>
    <DataNotice :metadata="data.metadata" />
  </div>
</template>
