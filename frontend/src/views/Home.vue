<script setup>
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ArrowRight, Search, Sparkles, Soup, Leaf, Flame, Utensils, Coffee } from 'lucide-vue-next'
import { readApi } from '../api'
import DishCard from '../components/DishCard.vue'
import DataNotice from '../components/DataNotice.vue'
import RequestState from '../components/RequestState.vue'
const router = useRouter()
const keyword = ref('')
const data = ref({ items: [], total: 0, metadata: {}, options: {} })
const loading = ref(true)
const error = ref('')
const icons = { 川菜: Flame, 面食: Soup, 米饭: Utensils, 轻食: Leaf, 早餐: Coffee, 夜宵: Utensils }
async function load() {
  loading.value = true; error.value = ''
  try {
    const result = await readApi('/dishes')
    if (!Array.isArray(result.items)) throw new Error('餐饮列表格式不完整，请重试。')
    data.value = result
  } catch (e) { error.value = e.message }
  finally { loading.value = false }
}
function search() { router.push({ path: '/explore', query: keyword.value.trim() ? { keyword: keyword.value.trim() } : {} }) }
onMounted(load)
</script>
<template>
  <section class="welcome-band"><div class="welcome-content">
    <span class="eyebrow">CAMPUS LIFE, ONE BITE AT A TIME</span>
    <h1>今天吃什么？</h1><p class="hero-name">校园食光 <span>CampusBite</span></p>
    <p class="welcome-copy">把选择留给口味，把好心情留给这一餐。</p>
    <form class="hero-search" @submit.prevent="search"><Search :size="20" /><input v-model="keyword" aria-label="首页美食搜索" placeholder="搜索菜品、食堂或喜欢的口味" /><button type="submit" aria-label="搜索美食"><ArrowRight :size="22" /></button></form>
  </div></section>
  <div class="page-container home-content">
    <section class="category-section"><div class="section-heading"><h2>跟着口味去探索</h2><RouterLink to="/explore">全部美食 <ArrowRight :size="16" /></RouterLink></div>
      <div class="category-list"><RouterLink v-for="cuisine in data.options?.cuisines || []" :key="cuisine" :to="{ path: '/explore', query: { cuisine } }" class="category-link"><component :is="icons[cuisine] || Utensils" :size="25" /><span>{{ cuisine }}</span><ArrowRight :size="15" /></RouterLink></div>
      <div class="taste-shortcuts"><span>今天的口味</span><RouterLink v-for="taste in ['清淡', '香辣', '麻辣', '鲜香']" :key="taste" :to="{ path: '/explore', query: { taste } }">{{ taste }}</RouterLink></div>
    </section>
    <section class="home-dishes"><div class="section-heading"><div><h2>校园餐单</h2><p v-if="!loading && !error">{{ data.total }} 道模拟菜品，慢慢挑一餐喜欢的。</p></div><RouterLink to="/explore">去探索 <ArrowRight :size="16" /></RouterLink></div>
      <RequestState :loading="loading" :error="error" @retry="load" />
      <div v-if="!loading && !error" class="dish-grid"><DishCard v-for="dish in data.items.slice(0, 8)" :key="dish.id" :dish="dish" /></div>
    </section>
    <section class="recommend-band"><Sparkles :size="28" /><div><h2>给下一餐留一点期待</h2><p>智能推荐 · 找到这一餐的好选择</p></div><RouterLink to="/recommend">填写口味偏好 <ArrowRight :size="18" /></RouterLink></section>
    <DataNotice :metadata="data.metadata" />
  </div>
</template>
