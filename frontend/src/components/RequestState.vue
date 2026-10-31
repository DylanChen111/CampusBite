<script setup>
import { RefreshCw, SearchX } from 'lucide-vue-next'
defineProps({ loading: Boolean, error: String, empty: Boolean })
defineEmits(['retry', 'reset'])
</script>
<template>
  <div v-if="loading" class="loading-area" role="status" data-testid="loading"><el-skeleton :rows="5" animated /><p>正在加载餐饮信息…</p></div>
  <div v-else-if="error" class="empty-state" role="alert"><RefreshCw :size="30" /><h2>暂时无法加载</h2><p>{{ error }}</p><el-button type="primary" @click="$emit('retry')">重试</el-button></div>
  <div v-else-if="empty" class="empty-state"><SearchX :size="36" /><h2>暂无匹配结果</h2><p>可以调整预算、口味或距离；严格忌口条件不会自动放宽。</p><el-button @click="$emit('reset')">重置筛选</el-button></div>
</template>
