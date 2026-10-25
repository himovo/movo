<template>
  <n-spin :show="loading">
    <div class="feedback-head">
      <span>{{ t('legacy.feedback_from_organization_members') }}</span>
      <n-tag :bordered="false" type="info">{{ t('legacy.likes', { count: summary.likes }) }}</n-tag>
    </div>
    <n-empty v-if="!summary.items.length" :description="t('legacy.no_comments_yet')" />
    <div v-else class="comment-list">
      <article v-for="item in summary.items" :key="item.id" class="comment-card">
        <div class="comment-meta">
          <strong>{{ item.author.displayName || t('legacy.organization_member') }}</strong>
          <span>{{ item.likes ? `♥ ${item.likes} · ` : '' }}{{ formatAdminDateTime(item.createdAt, '') }}</span>
        </div>
        <p>{{ item.content }}</p>
      </article>
    </div>
  </n-spin>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue';
import { NEmpty, NSpin, NTag, useMessage } from 'naive-ui';
import { fetchSkillFeedback, type SkillFeedbackSummary } from '@/api/skills';
import { formatAdminDateTime } from '@/composables/adminTimezone';
import { t } from '@/composables/i18n';

const props = defineProps<{ skillId: string }>();
const message = useMessage();
const loading = ref(false);
const summary = ref<SkillFeedbackSummary>({ items: [], likes: 0 });

onMounted(async () => {
  loading.value = true;
  try {
    summary.value = await fetchSkillFeedback(props.skillId);
  } catch (error: any) {
    message.error(error?.response?.data?.detail || error?.message || t('legacy.failed_to_load_comments'));
  } finally {
    loading.value = false;
  }
});
</script>

<style scoped>
.feedback-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 16px; color: #17233d; font-weight: 600; }
.comment-list { display: grid; gap: 10px; max-height: 520px; overflow: auto; }
.comment-card { padding: 13px 15px; border: 1px solid #e4eaf4; border-radius: 10px; background: #fafbfe; }
.comment-meta { display: flex; justify-content: space-between; gap: 16px; color: #17233d; }
.comment-meta span { color: #9aa5b8; font-size: 12px; }
.comment-card p { margin: 8px 0 0; color: #52627d; line-height: 1.65; white-space: pre-wrap; overflow-wrap: anywhere; }
</style>
