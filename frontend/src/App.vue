<script setup>
import { Compass, Leaf, Sparkles } from 'lucide-vue-next'
</script>
<template>
  <header class="site-header"><div class="nav-inner">
    <RouterLink to="/" class="brand"><span class="brand-mark"><Leaf :size="24" /></span><span>校园食光<small>CampusBite</small></span></RouterLink>
    <nav aria-label="主导航"><RouterLink to="/">首页</RouterLink><RouterLink to="/explore"><Compass :size="16" />美食探索</RouterLink><RouterLink to="/recommend"><Sparkles :size="16" />智能推荐</RouterLink></nav>
  </div></header>
  <main><RouterView /></main>
  <footer class="site-footer"><span>校园食光 CampusBite</span><span>一餐一刻，校园里的小确幸。</span><span>课程演示 · 模拟数据</span></footer>
</template>
