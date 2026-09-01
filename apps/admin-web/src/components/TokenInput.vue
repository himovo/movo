<template>
  <div class="token-input">
    <div v-if="suggestionsToShow.length" class="token-suggestions">
      <button
        v-for="item in suggestionsToShow"
        :key="item"
        type="button"
        class="token-suggestion"
        @click="addSuggestion(item)"
      >
        {{ item }}
      </button>
    </div>
    <div class="token-values">
      <span
        v-for="token in modelValue"
        :key="token"
        class="token-chip"
      >
        {{ token }}
        <button type="button" class="token-remove" @click="removeToken(token)">×</button>
      </span>
      <textarea
        v-if="multiline"
        v-model="draft"
        class="token-editor token-editor-textarea"
        :placeholder="placeholder"
        rows="4"
        @keydown.enter.prevent="commitDraft"
        @paste="handlePaste"
        @blur="commitDraft"
      />
      <input
        v-else
        v-model="draft"
        type="text"
        class="token-editor"
        :placeholder="placeholder"
        @keydown.enter.prevent="commitDraft"
        @blur="commitDraft"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue';

const props = defineProps<{
  modelValue: string[];
  placeholder?: string;
  suggestions?: string[];
  multiline?: boolean;
}>();

const emit = defineEmits(['update:modelValue']);
const draft = ref('');

function commitDraft() {
  const nextItems = splitDraftToTokens(draft.value);
  if (!nextItems.length) {
    draft.value = '';
    return;
  }
  const values = [...props.modelValue];
  let changed = false;
  nextItems.forEach((item) => {
    if (!values.some((existing) => existing.toLowerCase() === item.toLowerCase())) {
      values.push(item);
      changed = true;
    }
  });
  if (changed) {
    emit('update:modelValue', values);
  }
  draft.value = '';
}

function splitDraftToTokens(value: string): string[] {
  return String(value || '')
    .split(/\r?\n/)
    .map((item) => item.trim().replace(/^[\-\u2022\u00b7\s]+/, '').replace(/[;,，；]+$/, '').trim())
    .filter(Boolean);
}

function removeToken(token: string) {
  emit(
    'update:modelValue',
    props.modelValue.filter((item) => item !== token),
  );
}

function addSuggestion(value: string) {
  const next = String(value || '').trim();
  if (!next) return;
  if (!props.modelValue.some((item) => item.toLowerCase() === next.toLowerCase())) {
    emit('update:modelValue', [...props.modelValue, next]);
  }
}

function handlePaste(event: ClipboardEvent) {
  if (!props.multiline) {
    return;
  }
  const text = event.clipboardData?.getData('text/plain') || '';
  if (!text.includes('\n')) {
    return;
  }
  event.preventDefault();
  draft.value = text;
  commitDraft();
}

const suggestionsToShow = computed(() =>
  (props.suggestions || []).filter(
    (item) => !props.modelValue.some((token) => token.toLowerCase() === item.toLowerCase()),
  ),
);
</script>

<style scoped>
.token-input {
  display: flex;
  min-height: 136px;
  flex-direction: column;
  gap: 10px;
  border: 1px solid #d8e1f0;
  border-radius: 12px;
  background: #fff;
  padding: 12px;
}

.token-suggestions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.token-suggestion {
  border: 1px solid #dfe7f5;
  border-radius: 999px;
  background: #f7f9fd;
  color: #52627f;
  cursor: pointer;
  font-size: 12px;
  line-height: 1;
  padding: 7px 10px;
  transition: all 0.18s ease;
}

.token-suggestion:hover {
  border-color: #b9cbee;
  background: #edf3ff;
  color: #2a4d9b;
}

.token-values {
  display: flex;
  flex: 1;
  flex-wrap: wrap;
  align-content: flex-start;
  gap: 8px;
}

.token-chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  border-radius: 999px;
  background: #edf3ff;
  color: #2450a6;
  font-size: 12px;
  font-weight: 600;
  padding: 7px 10px;
}

.token-remove {
  border: 0;
  background: transparent;
  color: #4d73ba;
  cursor: pointer;
  font-size: 12px;
  padding: 0;
}

.token-editor {
  min-width: 140px;
  flex: 1;
  border: 0;
  color: #172033;
  font-size: 13px;
  outline: none;
  padding: 6px 0;
}

.token-editor-textarea {
  min-height: 96px;
  resize: vertical;
  font-family: inherit;
  line-height: 1.6;
}
</style>
