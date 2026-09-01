<script setup lang="ts">
import { computed } from 'vue';
import { t } from '@/composables/i18n';

const props = defineProps<{
  current: number;
}>();

const steps = computed(() => [
  t('部署检测'),
  t('组织与账号'),
  t('对话模型'),
  t('其他模型'),
  t('联网搜索'),
  t('完成'),
]);
</script>

<template>
  <nav class="progress-card" :aria-label="t('初始化进度')">
    <ol>
      <li
        v-for="(step, index) in steps"
        :key="step"
        :class="{ active: current === index + 1, complete: current > index + 1 }"
        :aria-current="current === index + 1 ? 'step' : undefined"
      >
        <span class="step-marker">
          <svg v-if="current > index + 1" viewBox="0 0 24 24" aria-hidden="true">
            <path d="m5 12 4 4L19 6" />
          </svg>
          <span v-else>{{ index + 1 }}</span>
        </span>
        <span class="step-label">{{ step }}</span>
      </li>
    </ol>
  </nav>
</template>

<style scoped>
.progress-card {
  padding: 16px 24px;
  border: 1px solid #dfe7f5;
  border-radius: 18px;
  background: rgba(255, 255, 255, .92);
  box-shadow: 0 12px 36px rgba(27, 55, 116, .08);
}

ol {
  display: grid;
  grid-template-columns: repeat(6, 1fr);
  margin: 0;
  padding: 0;
  list-style: none;
}

li {
  position: relative;
  display: flex;
  align-items: center;
  gap: 10px;
  color: #7b879f;
  font-size: 12px;
  font-weight: 600;
}

li:not(:last-child)::after {
  position: absolute;
  z-index: 0;
  top: 50%;
  right: 12px;
  left: 48px;
  height: 1px;
  background: #dfe7f5;
  content: '';
}

.step-marker {
  position: relative;
  z-index: 1;
  display: grid;
  width: 30px;
  height: 30px;
  flex: 0 0 30px;
  place-items: center;
  border: 1px solid #d7e0ef;
  border-radius: 50%;
  background: #fff;
}

.step-marker svg {
  width: 16px;
  fill: none;
  stroke: currentColor;
  stroke-linecap: round;
  stroke-linejoin: round;
  stroke-width: 2.4;
}

.step-label {
  position: relative;
  z-index: 1;
  padding-right: 10px;
  background: #fff;
  white-space: nowrap;
}

li.active { color: #2457d6; }
li.active .step-marker { border-color: #3568e8; background: #3568e8; color: #fff; box-shadow: 0 0 0 4px #e8efff; }
li.complete { color: #248466; }
li.complete .step-marker { border-color: #b7ead8; background: #e8f8f2; color: #168461; }
li.complete::after { background: #b7ead8; }

@media (max-width: 540px) {
  .progress-card { padding: 14px 16px; }
  li { align-items: flex-start; gap: 7px; font-size: 12px; }
  li:not(:last-child)::after { right: 8px; left: 38px; }
  .step-marker { width: 26px; height: 26px; flex-basis: 26px; }
  .step-label { display: none; }
}
</style>
