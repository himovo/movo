<template>
  <div v-if="iconSrc" class="file-icon-img-wrapper" :class="{ 'has-label': showLabel }">
    <img
      :src="iconSrc"
      :width="iconSize"
      :height="iconSize"
      class="file-icon-img"
      :class="{ 'file-icon-img-compact': compactIcon }"
      :alt="ext"
    />
    <span v-if="showLabel" class="file-icon-text">{{ displayLabel }}</span>
  </div>
  <n-tag v-else size="small" :bordered="false" class="file-fallback-tag">
    {{ displayLabel }}
  </n-tag>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { NTag } from 'naive-ui';

import docxIcon from '@/assets/images/docx-file.png';
import excelIcon from '@/assets/images/excel-48.png';
import pptIcon from '@/assets/images/ppt.png';
import pdfIcon from '@/assets/images/pdf-file-format.png';
import mdIcon from '@/assets/images/md.png';
import htmlIcon from '@/assets/images/html.png';
import textIcon from '@/assets/images/text.png';
import galleryIcon from '@/assets/images/gallery.png';

const props = withDefaults(
  defineProps<{
    ext?: string;
    size?: 'small' | 'medium' | 'large' | number;
    showLabel?: boolean;
  }>(),
  {
    ext: '',
    size: 'medium',
    showLabel: false,
  }
);

const normalizedExt = computed(() => {
  const e = props.ext || '';
  return e.toLowerCase().replace(/^\./, '').trim();
});

const displayLabel = computed(() => {
  return normalizedExt.value.toUpperCase() || 'FILE';
});

const iconSrc = computed(() => {
  const ext = normalizedExt.value;
  if (['doc', 'docx'].includes(ext)) return docxIcon;
  if (['xls', 'xlsx'].includes(ext)) return excelIcon;
  if (['ppt', 'pptx'].includes(ext)) return pptIcon;
  if (ext === 'pdf') return pdfIcon;
  if (['md', 'markdown'].includes(ext)) return mdIcon;
  if (['html', 'htm'].includes(ext)) return htmlIcon;
  if (ext === 'txt') return textIcon;
  if (['png', 'jpg', 'jpeg', 'webp', 'gif', 'bmp', 'svg'].includes(ext)) return galleryIcon;
  return null;
});

const compactIcon = computed(() => {
  return ['pdf', 'md', 'markdown', 'html', 'htm', 'txt'].includes(normalizedExt.value);
});

const iconSize = computed(() => {
  if (typeof props.size === 'number') {
    return props.size;
  }
  if (props.size === 'small') return 16;
  if (props.size === 'large') return 32;
  return 24; // 默认图片大小 24px，比较丰满大方
});
</script>

<style scoped>
.file-icon-img-wrapper {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  vertical-align: middle;
  transition: transform 0.2s cubic-bezier(0.4, 0, 0.2, 1);
}

.file-icon-img-wrapper:not(.has-label):hover {
  transform: scale(1.1);
  cursor: pointer;
}

.file-icon-img-wrapper.has-label {
  gap: 8px;
}

.file-icon-img {
  display: block;
  object-fit: contain;
}

.file-icon-img-compact {
  transform: scale(0.84);
}

.file-icon-text {
  font-size: 13px;
  font-weight: 650;
  color: #23324f;
  line-height: 1;
}

.file-fallback-tag {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  vertical-align: middle;
}
</style>
