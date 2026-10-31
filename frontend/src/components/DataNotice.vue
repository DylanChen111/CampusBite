<script setup>
import { Info } from 'lucide-vue-next'
defineProps({ metadata: Object })
</script>
<template>
  <div class="data-notice"><Info :size="18" aria-hidden="true" /><p><strong>模拟数据 · 仅用于课程演示</strong><span>{{ metadata?.notice || '场所、价格、距离、评分及营业信息均为虚构；不提供实时营业或现实食品安全保证。' }} 图片为类别示意图，并非对应菜品实拍。</span><small v-if="metadata?.data_version">数据版本 {{ metadata.data_version }}</small></p></div>
</template>
