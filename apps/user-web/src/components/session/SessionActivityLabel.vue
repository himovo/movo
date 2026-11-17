<script setup lang="ts">
import { computed } from 'vue'
import type { SessionSummary } from '../../api/sessions'
import { useLocale } from '../../composables/i18n'
import { formatFullConversationTime, formatSessionActivity } from '../../utils/conversationTime'

const props = defineProps<{ session: SessionSummary; now: number }>()
const { locale } = useLocale()
const value = computed(() => props.session.last_message_at || props.session.updated_at || props.session.created_at)
const label = computed(() => formatSessionActivity(props.session, locale.value, props.now))
const full = computed(() => formatFullConversationTime(value.value || undefined, locale.value))
</script>

<template>
  <time v-if="label" class="session-activity-label" :datetime="value || undefined" :title="full">{{ label }}</time>
</template>

<style scoped>
.session-activity-label{flex:none;max-width:84px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:#9ca3af;font-size:10px;font-weight:400}
</style>
