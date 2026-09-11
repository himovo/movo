<template>
  <n-modal :show="show" preset="card" :title="t('从 ZIP 安装企业 Skill')" style="width: 620px" @update:show="emit('update:show', $event)">
    <div class="zip-dropzone" :class="{ dragging }" @dragenter.prevent="dragging = true" @dragover.prevent @dragleave.prevent="dragging = false" @drop.prevent="onDrop" @click="input?.click()">
      <input ref="input" hidden type="file" accept=".zip,application/zip" @change="onChoose" />
      <strong>{{ file?.name || t('拖拽 ZIP 到这里，或点击选择文件') }}</strong>
      <span>{{ t('安装后默认禁用，管理员配置岗位权限后再启用；ZIP 最大 5 MiB') }}</span>
    </div>
    <n-alert v-if="result" class="install-result" type="success" :title="result.duplicate ? t('该版本已安装') : t('企业 Skill 安装成功')">
      {{ result.name }} · {{ result.version }} · {{ t('skills.install_file_count', { count: result.fileCount }) }}
      <template v-if="result.childCount"> · {{ t('skills.install_child_count', { count: result.childCount }) }}</template>
      <div v-if="result.children.length" class="expert-children">
        <n-tag v-for="child in result.children" :key="child.slug" size="small" :bordered="false">{{ child.name }} · {{ child.version }}</n-tag>
      </div>
      <ul v-if="result.warnings.length"><li v-for="warning in result.warnings" :key="warning.code + (warning.tool || '')">{{ localizeSkillInstallWarning(warning) }}</li></ul>
    </n-alert>
    <n-alert v-else-if="failure" class="install-result" type="error" :title="failureTitle || t('Skill 安装失败')">{{ failure }}</n-alert>
    <template #footer>
      <n-space justify="end">
        <n-button v-if="!result" @click="close">{{ t('取消') }}</n-button>
        <n-button v-if="result" type="primary" @click="close">{{ t('关闭') }}</n-button>
        <n-button v-else type="primary" :disabled="!file" :loading="installing" @click="install">{{ t('安装 Skill') }}</n-button>
      </n-space>
    </template>
  </n-modal>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue';
import { NAlert, NButton, NModal, NSpace, NTag } from 'naive-ui';
import { installSkillZip, type SkillInstallResult } from '@/api/skills';
import { t } from '@/composables/i18n';
import { localizeSkillInstallError, localizeSkillInstallWarning } from './skillInstallError';

const props = defineProps<{ show: boolean }>();
const emit = defineEmits<{ 'update:show': [value: boolean]; installed: [result: SkillInstallResult] }>();
const input = ref<HTMLInputElement | null>(null);
const file = ref<File | null>(null);
const dragging = ref(false);
const installing = ref(false);
const result = ref<SkillInstallResult | null>(null);
const failure = ref('');
const failureTitle = ref('');
function close() { emit('update:show', false); }
function select(candidate?: File) { if (!candidate) return; if (!candidate.name.toLowerCase().endsWith('.zip')) { file.value = null; result.value = null; failureTitle.value = t('安装包校验未通过'); failure.value = t('请选择 ZIP 格式的 Skill 安装包'); return; } file.value = candidate; result.value = null; failure.value = ''; failureTitle.value = ''; }
function onChoose(event: Event) { const target = event.target as HTMLInputElement; select(target.files?.[0]); target.value = ''; }
function onDrop(event: DragEvent) { dragging.value = false; select(event.dataTransfer?.files?.[0]); }
async function install() { if (!file.value) return; installing.value = true; failure.value = ''; failureTitle.value = ''; try { result.value = await installSkillZip(file.value); emit('installed', result.value); } catch (error: any) { const localized = localizeSkillInstallError(error); failureTitle.value = localized.title; failure.value = localized.message; } finally { installing.value = false; } }
watch(() => props.show, visible => { if (!visible) { file.value = null; result.value = null; failure.value = ''; failureTitle.value = ''; } });
defineExpose({ select });
</script>

<style scoped>
.zip-dropzone { min-height: 180px; border: 2px dashed #cbd8ee; border-radius: 12px; background: #f8fbff; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 10px; cursor: pointer; color: #52627d; }
.zip-dropzone.dragging { border-color: #2d63ff; background: #edf3ff; }
.zip-dropzone strong { color: #17233d; font-size: 16px; }
.zip-dropzone span { font-size: 12px; }
.install-result { margin-top: 16px; }
.expert-children { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 10px; }
</style>
