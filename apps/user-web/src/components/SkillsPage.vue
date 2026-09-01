<script setup lang="ts">
import { ref } from 'vue'
import { NButton, NEmpty, NSpin, NSwitch, NTag } from 'naive-ui'
import { analyzeTemplate, generateSkill } from '../api/skills'
import { t } from '../composables/i18n'

const props = defineProps<{
  skills: any[]
  loading: boolean
  userId: string | null
}>()

const emit = defineEmits(['back', 'create', 'create-composite', 'configure', 'remove', 'toggle-active'])
const fileInput = ref<HTMLInputElement | null>(null)
const importing = ref(false)
const showSuccessToast = ref(false)

function categoryLabel(category?: string) {
  switch (category) {
    case 'Analysis & Reports':
      return t('skills.category.analysis_reports')
    case 'Specs & Product':
      return t('skills.category.specs_product')
    case 'Governance & SOPs':
      return t('skills.category.governance_sops')
    case 'Presentation & Visuals':
      return t('skills.category.presentation_visuals')
    case 'Coding & Engineering':
      return t('skills.category.coding_engineering')
    case 'Browser Automation':
      return t('skills.category.browser_automation')
    default:
      return category || t('skills.category.general')
  }
}

function statusLabel(skill: any) {
  return skill.is_active === false ? t('skills.status.disabled') : t('skills.status.enabled')
}

function triggerImport() {
  fileInput.value?.click()
}

async function handleImport(event: Event) {
  const target = event.target as HTMLInputElement
  if (!target.files?.length) return
  if (!props.userId) {
    alert(t('skills.login_first'))
    return
  }
  
  const file = target.files[0]
  importing.value = true
  try {
    const data = await analyzeTemplate(file)
    
    // Parse frontmatter with flexible regex
    const md = data.skill_markdown || ''
    // Allow for optional leading whitespace and variations in newlines
    const frontmatterMatch = md.match(/^\s*---\s*\n([\s\S]*?)\n---/)
    let metadata = {
      name: `Generated Skill ${new Date().toLocaleTimeString()}`,
      description: t('skills.summary.fallback'),
      category: 'Analysis & Reports'
    }

    if (frontmatterMatch) {
      const fmContent = frontmatterMatch[1]
      const nameMatch = fmContent.match(/name:\s*(.+)/)
      const descMatch = fmContent.match(/description:\s*(.+)/)
      const catMatch = fmContent.match(/category:\s*(.+)/)
      
      if (nameMatch) metadata.name = nameMatch[1].trim()
      if (descMatch) metadata.description = descMatch[1].trim()
      if (catMatch) metadata.category = catMatch[1].trim()
    }

    // Auto-create skill immediately
    const newSkill = await generateSkill({
      user_id: props.userId,
      ...metadata,
      summary: metadata.description,
      tags: ['generated'],
      visibility: 'private',
      formats: ['markdown'],
      notes: '',
      sources: [file.name],
      resources: data.resources || {},
      skill_markdown: md,
      advanced: {}
    })

    // Show success toast
    showSuccessToast.value = true
    setTimeout(() => {
      showSuccessToast.value = false
    }, 3000)

    // Refresh list and open config
    emit('create', newSkill)
    emit('configure', newSkill)
    
  } catch (error) {
    console.error('Import failed', error)
    alert(t('skills.import.failed'))
  } finally {
    importing.value = false
    if (fileInput.value) fileInput.value.value = ''
  }
}
</script>

<template>
  <div class="flex flex-col h-full w-full bg-[#f8fafc]">
    <!-- Header -->
    <header class="h-16 border-b border-gray-200 bg-white/80 backdrop-blur-sm flex items-center px-8 justify-between shrink-0 sticky top-0 z-10">
      <div>
        <h1 class="text-lg font-semibold text-gray-900 leading-none">{{ t('skills.title') }}</h1>
        <p class="text-xs text-gray-500 font-medium mt-1">{{ t('skills.subtitle') }}</p>
      </div>
      <div class="flex items-center gap-3">
        <input 
          type="file" 
          ref="fileInput" 
          class="hidden" 
          accept=".docx,.pdf,.pptx,.xlsx,.txt,.md"
          @change="handleImport"
        />
        <n-button :loading="importing" :disabled="importing" @click="triggerImport">
          <template #icon>
            <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/></svg>
          </template>
          {{ t('skills.import_template') }}
        </n-button>
        <div class="h-6 w-px bg-gray-200 mx-1"></div>
        <n-button @click="emit('back')">{{ t('skills.back_to_chat') }}</n-button>
        <n-button @click="emit('create-composite')">
          <template #icon>
            <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 3h7v7H3zM14 3h7v7h-7zM14 14h7v7h-7zM3 14h7v7H3z"/></svg>
          </template>
          {{ t('skills.new_composite_skill') }}
        </n-button>
        <n-button type="primary" @click="emit('create')">
          <template #icon>
            <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12h14m-7-7v14"/></svg>
          </template>
          {{ t('skills.new_skill') }}
        </n-button>
      </div>
    </header>

    <!-- Main Content Area -->
    <div class="flex-1 overflow-y-auto p-6 lg:p-8 custom-scrollbar">
      <div class="max-w-[1400px] mx-auto h-full">
        
        <!-- Loading State -->
        <div v-if="loading" class="flex flex-col items-center justify-center h-64 space-y-4">
          <n-spin size="large" />
          <p class="text-sm font-medium text-gray-400 uppercase tracking-widest">{{ t('skills.loading') }}</p>
        </div>

        <!-- Empty State -->
        <div v-else-if="skills.length === 0" class="py-20 bg-white rounded-3xl border border-dashed border-gray-200 shadow-sm">
          <n-empty :description="t('skills.empty_title')" size="huge">
            <template #extra>
              <p class="text-gray-500 text-sm max-w-sm text-center mb-4">{{ t('skills.empty_desc') }}</p>
              <n-button type="primary" size="large" @click="emit('create')">
                {{ t('skills.empty_create') }}
              </n-button>
            </template>
          </n-empty>
        </div>

        <!-- Skills Grid -->
            <!-- Success Toast -->
            <div 
              v-if="showSuccessToast" 
              class="fixed top-24 right-8 z-50 bg-green-500 text-white px-6 py-3 rounded-xl shadow-lg flex items-center gap-3 animate-slide-in"
            >
              <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>
              <span class="font-medium">{{ t('skills.import.success') }}</span>
            </div>

            <div class="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4 gap-5">
          <div
            v-for="skill in skills"
            :key="skill.id"
            class="group bg-white rounded-2xl border border-gray-200 p-5 shadow-sm hover:shadow-lg hover:shadow-gray-200/40 hover:border-blue-200 transition-all flex flex-col h-full relative overflow-hidden"
          >
            <!-- Background Decoration -->
            <div class="absolute -right-4 -top-4 w-20 h-20 bg-blue-50/50 rounded-full blur-2xl group-hover:bg-blue-100/50 transition-colors"></div>

            <div class="flex items-start justify-between mb-3 relative z-10">
              <div class="w-10 h-10 rounded-xl bg-gray-50 border border-gray-100 flex items-center justify-center text-gray-600 group-hover:bg-blue-50 group-hover:border-blue-100 group-hover:text-blue-600 transition-all">
                <!-- 1. Analysis & Reports -->
                <svg v-if="skill.category === 'Analysis & Reports'" xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="20" x2="18" y2="10"/><line x1="12" y1="20" x2="12" y2="4"/><line x1="6" y1="20" x2="6" y2="14"/></svg>
                <!-- 2. Specs & Product -->
                <svg v-else-if="skill.category === 'Specs & Product'" xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/><polyline points="10 9 9 9 8 9"/></svg>
                <!-- 3. Governance & SOPs -->
                <svg v-else-if="skill.category === 'Governance & SOPs'" xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
                <!-- 4. Presentation & Visuals -->
                <svg v-else-if="skill.category === 'Presentation & Visuals'" xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="3" width="20" height="14" rx="2" ry="2"/><line x1="8" y1="21" x2="16" y2="21"/><line x1="12" y1="17" x2="12" y2="21"/></svg>
                <!-- 5. Coding & Engineering -->
                <svg v-else-if="skill.category === 'Coding & Engineering'" xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/></svg>
                <!-- 6. Browser Automation -->
                <svg v-else-if="skill.category === 'Browser Automation'" xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/></svg>
                <!-- Fallback -->
                <svg v-else xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg>
              </div>
              <div class="flex items-center gap-2">
                <n-tag size="small" :bordered="false" round type="default">
                  {{ categoryLabel(skill.category) }}
                </n-tag>
                <n-tag
                  size="small"
                  :bordered="false"
                  round
                  :type="skill.is_active === false ? 'error' : 'success'"
                >
                  {{ skill.is_active === false ? t('skills.status.disabled') : (skill.skill_type || 'skill') }}
                </n-tag>
              </div>
            </div>

            <div class="flex-1 min-w-0 relative z-10">
              <h3 class="text-sm font-bold text-gray-900 mb-0.5 truncate group-hover:text-blue-700 transition-colors">{{ skill.name }}</h3>
              <p class="text-[11px] text-gray-500 line-clamp-2 leading-relaxed min-h-[32px]">
                {{ skill.summary || skill.description || t('skills.summary.fallback') }}
              </p>
            </div>

            <div class="mt-4 pt-4 border-t border-gray-50 flex items-center justify-between relative z-10">
              <div class="flex items-center gap-3 min-w-0">
                 <div class="flex -space-x-1.5">
                   <div v-if="skill.resources?.knowledge?.length" class="w-5 h-5 rounded-full border-2 border-white bg-blue-50 flex items-center justify-center text-[9px] font-extrabold text-blue-500" :title="t('skills.resource.knowledge_docs')">K</div>
                   <div v-if="skill.resources?.tools?.length" class="w-5 h-5 rounded-full border-2 border-white bg-green-50 flex items-center justify-center text-[9px] font-extrabold text-green-500" :title="t('skills.resource.custom_tools')">T</div>
                 </div>
                 <div class="flex items-center gap-2 text-[11px] font-medium text-gray-500">
                   <span>{{ statusLabel(skill) }}</span>
                   <n-switch
                     :value="skill.is_active !== false"
                     size="small"
                     @update:value="(value) => emit('toggle-active', skill, value)"
                     @click.stop
                   />
                 </div>
              </div>
              <div class="flex items-center gap-1.5">
                <n-button size="tiny" type="primary" ghost @click="emit('configure', skill)">
                  {{ t('skills.configure') }}
                </n-button>
              </div>
            </div>
          </div>
        </div>

      </div>
    </div>
  </div>
</template>


<style scoped>
.custom-scrollbar::-webkit-scrollbar {
  width: 6px;
}
.custom-scrollbar::-webkit-scrollbar-track {
  background: transparent;
}
.custom-scrollbar::-webkit-scrollbar-thumb {
  background: #e2e8f0;
  border-radius: 10px;
}
.custom-scrollbar::-webkit-scrollbar-thumb:hover {
  background: #cbd5e1;
}

.line-clamp-3 {
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;  
  overflow: hidden;
}
</style>
