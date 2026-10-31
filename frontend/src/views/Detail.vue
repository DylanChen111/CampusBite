<script setup>
import { onBeforeUnmount, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { ArrowLeft, Clock, MapPin, Star, Utensils } from 'lucide-vue-next'
import { readApi } from '../api'
import { distance, hours, list, money, photo, rating, risk, state, text } from '../format'
import DataNotice from '../components/DataNotice.vue'
import RequestState from '../components/RequestState.vue'
const route = useRoute()
const dish = ref(null), metadata = ref({}), loading = ref(false), error = ref(''), notFound = ref(false)
let request
async function load() {
  request?.abort(); const current = new AbortController(); request = current
  loading.value = true; error.value = ''; notFound.value = false; dish.value = null
  try {
    const result = await readApi(`/dishes/${encodeURIComponent(route.params.id)}`, { signal: current.signal })
    if (!result.item || typeof result.item !== 'object') throw new Error('菜品详情不完整，请稍后重试。')
    if (!current.signal.aborted) { dish.value = result.item; metadata.value = result.metadata }
  } catch (e) {
    if (!current.signal.aborted) { if (e.status === 404) notFound.value = true; else error.value = e.message }
  } finally { if (!current.signal.aborted) loading.value = false }
}
watch(() => route.params.id, load, { immediate: true })
onBeforeUnmount(() => request?.abort())
</script>
<template>
  <div class="page-container detail-page">
    <RouterLink to="/explore" class="back-link"><ArrowLeft :size="17" />返回美食探索</RouterLink>
    <RequestState :loading="loading" :error="error" @retry="load" />
    <div v-if="notFound" class="empty-state"><Utensils :size="32" /><h1>这道菜品不存在</h1><p>它可能已被移除，去看看其他菜品吧。</p><RouterLink to="/explore" class="text-link">探索其他美食</RouterLink></div>
    <template v-if="dish && !loading && !error">
      <div class="detail-top"><div class="detail-photo"><img :src="photo(dish.cuisine)" :alt="`${text(dish.cuisine)}类别示意图`" /><span class="image-label">类别示意图 · 非菜品实拍</span></div>
        <section class="detail-summary"><span class="eyebrow">CAMPUS MENU</span><h1>{{ text(dish.name) }}</h1><p class="detail-restaurant">{{ text(dish.restaurant?.name) }}</p><div class="tag-row"><span class="food-tag">{{ text(dish.cuisine) }}</span><span v-for="tag in list(dish.taste_tags)" :key="tag" class="food-tag neutral">{{ tag }}</span><span v-for="tag in list(dish.dietary_tags)" :key="tag" class="food-tag">{{ tag }}</span></div>
          <div class="detail-price"><strong>{{ money(dish.price) }}</strong><span>菜品参考价格</span></div>
          <dl class="detail-facts"><div><dt><MapPin :size="17" />参考距离</dt><dd>{{ distance(dish.restaurant?.distance_m) }}</dd></div><div><dt><Star :size="17" />场所模拟评分</dt><dd>{{ rating(dish.restaurant?.rating) }} / 5</dd></div><div><dt><Clock :size="17" />模拟营业状态</dt><dd>{{ state(dish.restaurant?.is_open) }}</dd></div></dl>
          <p class="detail-description">{{ text(dish.description) }}</p>
        </section>
      </div>
      <div class="detail-sections"><section><h2>餐饮场所</h2><dl class="info-list"><div><dt>所属场所</dt><dd>{{ text(dish.restaurant?.name) }}</dd></div><div><dt>位置</dt><dd>{{ text(dish.restaurant?.location) }}</dd></div><div><dt>模拟营业时间</dt><dd>{{ hours(dish.restaurant?.business_hours) }}</dd></div><div><dt>用餐时段</dt><dd>{{ list(dish.restaurant?.meal_periods).join('、') || '暂无数据' }}</dd></div><div><dt>参考人均价</dt><dd>{{ money(dish.restaurant?.avg_price) }}</dd></div><div><dt>模拟状态对应时刻</dt><dd>{{ text(dish.restaurant?.status_at) }}</dd></div></dl></section>
        <section><h2>食材与过敏原</h2><dl class="info-list"><div><dt>主要食材</dt><dd>{{ risk(dish.ingredients) }}</dd></div><div><dt>忌口标签</dt><dd>{{ risk(dish.avoid_tags) }}</dd></div><div><dt>已声明过敏原</dt><dd>{{ risk(dish.allergens) }}</dd></div><div><dt>可能含有</dt><dd>{{ risk(dish.possible_allergens) }}</dd></div><div><dt>饮食标签</dt><dd>{{ list(dish.dietary_tags).join('、') || '无已声明标签' }}</dd></div></dl><p class="risk-note">未知信息不等于不含过敏原。素食标签允许蛋奶；模拟配方不提供现实食品安全保证。</p></section></div>
    </template>
    <DataNotice :metadata="metadata" />
  </div>
</template>
