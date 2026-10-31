<script setup>
import { ArrowUpRight, MapPin, Star } from 'lucide-vue-next'
import { distance, hours, list, money, photo, rating, state, text } from '../format'
defineProps({ dish: { type: Object, required: true } })
</script>

<template>
  <RouterLink :to="`/dishes/${dish.id}`" class="dish-card" data-testid="dish-card">
    <div class="dish-image">
      <img :src="photo(dish.cuisine)" :alt="`${text(dish.cuisine)}类别示意图`" loading="lazy" />
      <span class="image-label">类别示意图</span>
      <span class="status-label" :class="dish.restaurant?.is_open === 'TRUE' ? 'open' : ''">{{ state(dish.restaurant?.is_open) }}</span>
    </div>
    <div class="dish-body">
      <div class="card-title"><h3>{{ text(dish.name) }}</h3><ArrowUpRight :size="18" aria-hidden="true" /></div>
      <p class="restaurant-name">{{ text(dish.restaurant?.name) }}</p>
      <div class="tag-row"><span class="food-tag">{{ text(dish.cuisine) }}</span><span v-for="tag in list(dish.taste_tags)" :key="tag" class="food-tag neutral">{{ tag }}</span><span v-if="list(dish.dietary_tags).includes('素食')" class="food-tag">素食</span></div>
      <div class="card-meta"><span><MapPin :size="14" />{{ distance(dish.restaurant?.distance_m) }}</span><span><Star :size="14" />{{ rating(dish.restaurant?.rating) }}<small>场所模拟评分</small></span></div>
      <p class="card-hours">{{ hours(dish.restaurant?.business_hours) }}</p>
      <div class="card-bottom"><strong data-testid="dish-price">{{ money(dish.price) }}</strong><span>场所参考人均 {{ money(dish.restaurant?.avg_price) }}</span></div>
    </div>
  </RouterLink>
</template>
