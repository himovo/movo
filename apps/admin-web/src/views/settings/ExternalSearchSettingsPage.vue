<template>
  <div class="settings-page">
    <aside class="settings-nav" aria-label="settings sections">
      <button
        class="settings-nav-item"
        :class="{ active: activeSection === 'general' }"
        type="button"
        @click="switchSection('general')"
      >
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="nav-icon">
          <line x1="4" y1="21" x2="4" y2="14" />
          <line x1="4" y1="10" x2="4" y2="3" />
          <line x1="12" y1="21" x2="12" y2="12" />
          <line x1="12" y1="8" x2="12" y2="3" />
          <line x1="20" y1="21" x2="20" y2="16" />
          <line x1="20" y1="12" x2="20" y2="3" />
          <line x1="1" y1="14" x2="7" y2="14" />
          <line x1="9" y1="8" x2="15" y2="8" />
          <line x1="17" y1="16" x2="23" y2="16" />
        </svg>
        <span>{{ t('legacy.general_settings') }}</span>
      </button>
      <button
        class="settings-nav-item"
        :class="{ active: activeSection === 'shortcuts' }"
        type="button"
        @click="switchSection('shortcuts')"
      >
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="nav-icon"><rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/></svg>
        <span>{{ t('legacy.quick_access') }}</span>
      </button>
      <button
        class="settings-nav-item"
        :class="{ active: activeSection === 'presentation' }"
        type="button"
        @click="switchSection('presentation')"
      >
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="nav-icon">
          <rect x="3" y="3" width="18" height="14" rx="2" />
          <path d="M8 21h8M12 17v4M7 8h4M7 12h10" />
        </svg>
        <span>{{ t('legacy.ppt_generation') }}</span>
      </button>
      <button
        class="settings-nav-item"
        :class="{ active: activeSection === 'external-search' }"
        type="button"
        @click="switchSection('external-search')"
      >
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="nav-icon">
          <circle cx="12" cy="12" r="10" />
          <path d="M12 2a14.5 14.5 0 0 0 0 20 14.5 14.5 0 0 0 0-20" />
          <path d="M2 12h20" />
        </svg>
        <span>{{ t('legacy.web_search_b84b2fd') }}</span>
      </button>
      <button
        class="settings-nav-item"
        :class="{ active: activeSection === 'page-collection' }"
        type="button"
        @click="switchSection('page-collection')"
      >
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="nav-icon">
          <path d="M2 17 12 22 22 17M2 12 12 17 22 12M12 2 2 7 12 12 22 7 12 2Z" />
        </svg>
        <span>{{ t('legacy.page_collection') }}</span>
      </button>
      <button
        class="settings-nav-item"
        :class="{ active: activeSection === 'knowledge' }"
        type="button"
        @click="switchSection('knowledge')"
      >
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="nav-icon">
          <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20" />
          <path d="M4 4.5A2.5 2.5 0 0 1 6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5Z" />
          <path d="M9 8h6" />
          <path d="M9 12h6" />
          <path d="M9 16h4" />
        </svg>
        <span>{{ t('knowledgeSource.pageTitle') }}</span>
      </button>
      <button class="settings-nav-item" :class="{ active: activeSection === 'topic-admission' }" type="button" @click="switchSection('topic-admission')">
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="nav-icon"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10Z"/><path d="m9 12 2 2 4-4"/></svg>
        <span>{{ t('taskAdmission.title') }}</span>
      </button>
    </aside>

    <main v-if="activeSection === 'general'" class="settings-main">
      <div class="settings-header">
        <div>
          <div class="settings-title">{{ t('legacy.general_settings') }}</div>
          <div class="settings-subtitle">{{ t('legacy.configure_the_language_timezone_and_theme_display_of_the') }}</div>
        </div>
        <n-space>
          <n-button type="primary" @click="saveGeneralSettings">{{ t('legacy.save_817af18') }}</n-button>
        </n-space>
      </div>

      <div class="general-settings-content">
        <n-form class="provider-form" label-placement="top">
          <n-grid :cols="2" :x-gap="16" :y-gap="16">
            <n-grid-item :span="2">
              <n-form-item :label="t('legacy.interface_language')">
                <n-select v-model:value="generalForm.language" :options="languageSelectOptions">
                  <template #prefix>
                    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="input-prefix-icon">
                      <circle cx="12" cy="12" r="10" />
                      <path d="M12 2a14.5 14.5 0 0 0 0 20 14.5 14.5 0 0 0 0-20" />
                      <path d="M2 12h20" />
                    </svg>
                  </template>
                </n-select>
              </n-form-item>
            </n-grid-item>

            <n-grid-item :span="2">
              <n-form-item :label="t('legacy.system_timezone')">
                <n-select v-model:value="generalForm.timezone" :options="timezoneSelectOptions" filterable>
                  <template #prefix>
                    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="input-prefix-icon">
                      <circle cx="12" cy="12" r="10" />
                      <polyline points="12 6 12 12 16 14" />
                    </svg>
                  </template>
                </n-select>
              </n-form-item>
            </n-grid-item>

            <n-grid-item :span="2">
              <n-form-item :label="t('legacy.interface_theme')">
                <div class="theme-radio-wrapper">
                  <n-radio-group v-model:value="generalForm.themeMode" @update:value="handleThemeChange">
                    <n-radio-button value="light">{{ t('legacy.light_mode') }}</n-radio-button>
                    <n-radio-button value="dark">{{ t('legacy.dark_mode') }}</n-radio-button>
                    <n-radio-button value="system">{{ t('legacy.follow_system') }}</n-radio-button>
                  </n-radio-group>
                </div>
              </n-form-item>
            </n-grid-item>
          </n-grid>
        </n-form>
      </div>
    </main>

    <main v-else-if="activeSection === 'shortcuts'" class="settings-main">
      <div v-if="hasShortcutSchemes" class="shortcut-page-tabs" role="tablist" :aria-label="t('legacy.quick_access')">
        <button type="button" :class="{ active: shortcutView === 'schemes' }" @click="switchShortcutView('schemes')">{{ t('legacy.schemes') }}</button>
        <button type="button" :class="{ active: shortcutView === 'default' }" @click="switchShortcutView('default')">{{ t('legacy.default_shortcuts') }}</button>
      </div>
      <ShortcutSchemeOverview v-if="hasShortcutSchemes && shortcutView === 'schemes'" :on-edit-default="() => switchShortcutView('default')" />
      <ShortcutSettingsPanel v-else ref="shortcutSettingsRef" />
    </main>

    <main v-else-if="activeSection === 'presentation'" class="settings-main">
      <PresentationSettingsPanel />
    </main>

    <main v-else-if="activeSection === 'topic-admission'" class="settings-main">
      <TopicAdmissionPanel />
    </main>

    <main v-else-if="activeSection === 'external-search'" class="settings-main">
      <div class="settings-header">
        <div>
          <div class="settings-title">{{ t('legacy.web_search_b84b2fd') }}</div>
          <div class="settings-subtitle">{{ t('legacy.configure_the_external_search_provider_used_by_web_search') }}</div>
        </div>
        <n-space>
          <n-button secondary :loading="loading" @click="loadProviders">{{ t('legacy.refresh') }}</n-button>
          <n-button type="primary" :loading="saving" @click="saveCurrent">{{ t('legacy.save_817af18') }}</n-button>
        </n-space>
      </div>

      <n-spin :show="loading">
        <div class="provider-layout">
          <section class="provider-list">
            <button
              v-for="item in providers"
              :key="item.provider"
              class="provider-row"
              :class="{ selected: item.provider === selectedProvider }"
              type="button"
              @click="selectProvider(item.provider)"
            >
              <div class="provider-main">
                <div class="provider-name-row">
                  <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="provider-row-icon">
                    <rect x="2" y="3" width="20" height="14" rx="2" ry="2" />
                    <line x1="8" y1="21" x2="16" y2="21" />
                    <line x1="12" y1="17" x2="12" y2="21" />
                  </svg>
                  <div class="provider-name">{{ item.label }}</div>
                </div>
                <div class="provider-meta">
                  <n-tag v-if="item.isDefault" type="info" size="small" :bordered="false">{{ t('legacy.default') }}</n-tag>
                  <n-tag :type="item.enabled ? 'success' : 'default'" size="small" :bordered="false">
                    {{ item.enabled ? t('legacy.active') : t('legacy.disabled_be70be5') }}
                  </n-tag>
                  <n-tag :type="healthTagType(item.healthStatus)" size="small" :bordered="false">
                    {{ healthText(item.healthStatus) }}
                  </n-tag>
                </div>
              </div>
            </button>
          </section>

          <section v-if="activeProvider" class="provider-editor">
            <div class="editor-toolbar">
              <div>
                <div class="editor-title">
                  <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" class="title-decor-icon">
                    <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>
                  </svg>
                  {{ activeProvider.label }}
                </div>
                <div class="editor-state">{{ activeProvider.apiKeyMasked || t('legacy.api_key_not_saved') }}</div>
              </div>
              <n-space>
                <n-switch v-model:value="form.enabled" />
                <n-button secondary :disabled="!form.enabled || activeProvider.isDefault || saving" @click="makeDefault">
                  {{ activeProvider.isDefault ? t('legacy.current_default') : t('legacy.set_as_default') }}
                </n-button>
              </n-space>
            </div>

            <n-form class="provider-form" label-placement="top">
              <n-grid :cols="2" :x-gap="16">
                <n-grid-item :span="2">
                  <n-form-item label="API Key">
                    <n-input
                      v-model:value="form.apiKey"
                      type="password"
                      show-password-on="click"
                      :placeholder="activeProvider.apiKeyMasked ? t('legacy.leave_blank_to_keep_the_saved_key') : t('legacy.enter_api_key')"
                    >
                      <template #prefix>
                        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="input-prefix-icon">
                          <path d="m21 2-2 2m-7.61 7.61a5.5 5.5 0 1 1-7.778 7.778 5.5 5.5 0 0 1 7.777-7.777zm0 0L15.5 7.5m0 0 1.5 1.5M15.5 7.5 14 6" />
                        </svg>
                      </template>
                    </n-input>
                  </n-form-item>
                </n-grid-item>

                <n-grid-item v-if="selectedProvider === 'baidu_qianfan' || selectedProvider === 'deepseek'" :span="2">
                  <n-form-item label="Endpoint">
                    <n-input v-model:value="form.endpoint">
                      <template #prefix>
                        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="input-prefix-icon">
                          <path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71" />
                          <path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71" />
                        </svg>
                      </template>
                    </n-input>
                  </n-form-item>
                </n-grid-item>

                <n-grid-item v-if="selectedProvider === 'volc_ark'">
                  <n-form-item label="Base URL">
                    <n-input v-model:value="form.baseUrl">
                      <template #prefix>
                        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="input-prefix-icon">
                          <path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71" />
                          <path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71" />
                        </svg>
                      </template>
                    </n-input>
                  </n-form-item>
                </n-grid-item>

                <n-grid-item v-if="selectedProvider === 'volc_ark'">
                  <n-form-item label="Bot Model">
                    <n-input v-model:value="form.model" placeholder="bot-...">
                      <template #prefix>
                        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="input-prefix-icon">
                          <rect x="4" y="4" width="16" height="16" rx="2" ry="2" />
                          <rect x="9" y="9" width="6" height="6" />
                          <path d="M9 1v3M15 1v3M9 20v3M15 20v3M20 9h3M20 15h3M1 9h3M1 15h3" />
                        </svg>
                      </template>
                    </n-input>
                  </n-form-item>
                </n-grid-item>

                <n-grid-item :span="2">
                  <SearchProviderGuide :provider="selectedProvider" />
                </n-grid-item>

                <n-grid-item :span="2">
                  <n-form-item :label="t('legacy.test_query')">
                    <n-input v-model:value="testQuery">
                      <template #prefix>
                        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="input-prefix-icon">
                          <circle cx="11" cy="11" r="8" />
                          <line x1="21" y1="21" x2="16.65" y2="16.65" />
                        </svg>
                      </template>
                    </n-input>
                  </n-form-item>
                </n-grid-item>
              </n-grid>
            </n-form>

            <div class="test-actions">
              <n-button :loading="testing" @click="runTest">{{ t('legacy.test_connection') }}</n-button>
            </div>

            <n-alert
              v-if="testResult"
              :type="testResult.ok ? 'success' : 'error'"
              :bordered="false"
              class="test-result"
            >
              <div class="test-result-title">
                {{ testResult.ok ? t('legacy.connection_test_passed') : t('legacy.connection_test_failed') }}
              </div>
              <div class="test-result-message">{{ testResult.message }}</div>
            </n-alert>

            <div v-if="testResult?.sampleResults.length" class="sample-results">
              <div v-for="item in testResult.sampleResults" :key="item.url || item.title" class="sample-row">
                <div class="sample-title">{{ item.title || item.url }}</div>
                <div class="sample-url">{{ item.url }}</div>
                <div class="sample-snippet">{{ item.snippet }}</div>
              </div>
            </div>

            <n-alert v-if="activeProvider.lastError && !testResult" type="warning" :bordered="false" class="last-error">
              {{ activeProvider.lastError }}
            </n-alert>
          </section>
        </div>
      </n-spin>
    </main>

    <main v-else-if="activeSection === 'page-collection'" class="settings-main">
      <div class="settings-header">
        <div>
          <div class="settings-title">{{ t('legacy.page_collection') }}</div>
          <div class="settings-subtitle">{{ t('legacy.configure_page_content_extraction_from_urls') }}</div>
        </div>
        <n-space>
          <n-button secondary :loading="pageCollectionLoading" @click="loadPageCollection">{{ t('legacy.refresh') }}</n-button>
          <n-button type="primary" :loading="pageCollectionSaving" @click="savePageCollection">{{ t('legacy.save_817af18') }}</n-button>
        </n-space>
      </div>

      <n-spin :show="pageCollectionLoading">
        <section class="provider-editor single-provider-editor">
          <div class="editor-toolbar">
            <div>
              <div class="editor-title">
                <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" class="title-decor-icon">
                  <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>
                </svg>
                {{ pageCollectionSettings?.label || 'Firecrawl' }}
              </div>
              <div class="editor-state">{{ pageCollectionSettings?.apiKeyMasked || t('legacy.api_key_not_saved') }}</div>
            </div>
            <n-switch v-model:value="pageCollectionForm.enabled" />
          </div>

          <n-form class="provider-form" label-placement="top">
            <n-grid :cols="2" :x-gap="16">
              <n-grid-item :span="2">
                <n-form-item label="API Key">
                  <n-input
                    v-model:value="pageCollectionForm.apiKey"
                    type="password"
                    show-password-on="click"
                    :placeholder="pageCollectionSettings?.apiKeyMasked ? t('legacy.leave_blank_to_keep_the_saved_key') : t('legacy.enter_api_key')"
                  >
                    <template #prefix>
                      <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="input-prefix-icon">
                        <path d="m21 2-2 2m-7.61 7.61a5.5 5.5 0 1 1-7.778 7.778 5.5 5.5 0 0 1 7.777-7.777zm0 0L15.5 7.5m0 0 1.5 1.5M15.5 7.5 14 6" />
                      </svg>
                    </template>
                  </n-input>
                </n-form-item>
              </n-grid-item>
            </n-grid>
          </n-form>
        </section>
      </n-spin>
    </main>

    <main v-else class="settings-main">
      <div class="settings-header">
        <div>
          <div class="settings-title">{{ t('knowledgeSource.pageTitle') }}</div>
          <div class="settings-subtitle">{{ t('knowledgeSource.pageSubtitle') }}</div>
        </div>
        <n-space>
          <n-tag v-if="hasKnowledgeEdits" type="warning" round>{{ t('knowledgeSource.unsaved') }}</n-tag>
          <n-button secondary :loading="knowledgeLoading" @click="refreshKnowledgeConfiguration">{{ t('legacy.refresh') }}</n-button>
          <n-button type="primary" :loading="knowledgeSaving || knowledgeSourceRef?.saving" @click="saveKnowledgeConfiguration">{{ t('legacy.save') }}</n-button>
        </n-space>
      </div>

      <KnowledgeSourceSettingsPanel ref="knowledgeSourceRef" @mode-change="knowledgeSourceMode = $event" />
      <n-spin v-if="knowledgeSourceMode === 'movo'" :show="knowledgeLoading">
        <section class="knowledge-settings-panel">
          <n-form class="provider-form knowledge-form" label-placement="top">
            <div class="knowledge-config-card">
              <div class="knowledge-card-title">{{ t('legacy.document_chunking_settings') }}</div>
              <n-grid :cols="2" :x-gap="16" :y-gap="10">
                <n-grid-item>
                  <n-form-item :label="t('legacy.max_chunk_size')">
                    <n-input-number
                      v-model:value="knowledgeForm.parse.maxChunkSize"
                      :min="200"
                      :max="8000"
                      :step="100"
                      style="width: 100%"
                    />
                  </n-form-item>
                </n-grid-item>
                <n-grid-item>
                  <n-form-item :label="t('legacy.chunk_overlap')">
                    <n-input-number
                      v-model:value="knowledgeForm.parse.chunkOverlap"
                      :min="0"
                      :max="2000"
                      :step="20"
                      style="width: 100%"
                    />
                  </n-form-item>
                </n-grid-item>
                <n-grid-item :span="2">
                  <n-alert type="warning" :bordered="false">
                    {{ t('legacy.this_setting_only_affects_newly_uploaded_or_re_processed') }}
                  </n-alert>
                </n-grid-item>
              </n-grid>
            </div>

            <div class="knowledge-config-card">
              <div class="knowledge-card-title">{{ t('legacy.q_a_effect_settings') }}</div>
              <n-grid :cols="2" :x-gap="16" :y-gap="10">
                <n-grid-item>
                  <n-form-item :label="t('legacy.retrieval_mode')">
                    <n-select v-model:value="knowledgeForm.retrieval.mode" :options="retrievalModeOptions" />
                  </n-form-item>
                </n-grid-item>
                <n-grid-item>
                  <n-form-item :label="t('legacy.candidates_to_retrieve_top_n')">
                    <n-input-number v-model:value="knowledgeForm.retrieval.topN" :min="1" :max="50" style="width: 100%" />
                  </n-form-item>
                </n-grid-item>
                <n-grid-item>
                  <n-form-item :label="t('legacy.enable_rerank')">
                    <n-switch v-model:value="knowledgeForm.retrieval.rerank.enabled" />
                    <div class="field-help">{{ t('legacy.rerank_retrieved_candidates_by_relevance_usually_more_accurate_but') }}</div>
                  </n-form-item>
                </n-grid-item>
                <n-grid-item>
                  <n-form-item :label="t('legacy.max_candidate_segments_for_reranking_top_k')">
                    <n-input-number
                      v-model:value="knowledgeForm.retrieval.rerank.topK"
                      :min="knowledgeForm.retrieval.topN"
                      :max="200"
                      style="width: 100%"
                      :disabled="!knowledgeForm.retrieval.rerank.enabled"
                    />
                  </n-form-item>
                </n-grid-item>
                <n-grid-item>
                  <n-form-item :label="t('legacy.max_context_tokens')">
                    <n-input-number v-model:value="knowledgeForm.context.maxContextTokens" :min="500" :max="200000" :step="500" style="width: 100%" />
                  </n-form-item>
                </n-grid-item>
                <n-grid-item>
                  <n-form-item :label="t('legacy.max_citations_to_show')">
                    <n-input-number v-model:value="knowledgeForm.citation.maxCount" :min="1" :max="20" style="width: 100%" />
                  </n-form-item>
                </n-grid-item>
              </n-grid>
            </div>

            <div class="knowledge-advanced">
              <div class="knowledge-advanced-summary">
                <div>
                  <div class="knowledge-advanced-title">{{ t('legacy.advanced_configuration') }}</div>
                  <div class="knowledge-advanced-desc">{{ t('legacy.parameters_such_as_models_vector_stores_and_indices_are') }}</div>
                </div>
                <n-button secondary size="small" @click="showKnowledgeAdvanced = !showKnowledgeAdvanced">
                  {{ showKnowledgeAdvanced ? t('legacy.hide_advanced_config') : t('legacy.show_advanced_config') }}
                </n-button>
              </div>
              <template v-if="showKnowledgeAdvanced">
                <div class="knowledge-config-card knowledge-advanced-panel">
                  <div class="knowledge-card-title">{{ t('legacy.advanced_configuration') }}</div>
                  <n-alert type="default" :bordered="false" class="knowledge-advanced-note">
                    {{ t('legacy.these_configurations_are_mainly_for_admins_and_engineers_to') }}
                  </n-alert>

                  <div class="knowledge-section-title">{{ t('legacy.embedding_model') }}</div>
                  <n-grid :cols="2" :x-gap="16" :y-gap="10">
                  <n-grid-item :span="2">
                    <n-form-item :label="t('legacy.select_embedding_model')" required>
                      <ModelCapabilitySelect
                        v-model="knowledgeForm.embedding.modelInstanceId"
                        capability="embedding"
                        :placeholder="t('legacy.select_an_embedding_model_from_model_center')"
                      />
                      <div class="field-help">{{ t('legacy.only_enabled_model_center_models_with_embedding_capability_are') }}</div>
                    </n-form-item>
                  </n-grid-item>
                  <n-grid-item>
                    <n-form-item :label="t('legacy.embedding_dimension')">
                      <n-input-number v-model:value="knowledgeForm.embedding.dimension" :min="1" :max="20000" style="width: 100%" />
                    </n-form-item>
                  </n-grid-item>
                  <n-grid-item>
                    <n-form-item :label="t('legacy.batch_size')">
                      <n-input-number v-model:value="knowledgeForm.embedding.batchSize" :min="1" :max="256" style="width: 100%" />
                    </n-form-item>
                  </n-grid-item>
                </n-grid>

                <div class="knowledge-section-title">{{ t('legacy.vector_database') }}</div>
                <n-grid :cols="2" :x-gap="16" :y-gap="10">
                  <n-grid-item>
                    <n-form-item :label="t('legacy.database_type')">
                      <n-select v-model:value="knowledgeForm.vectorStore.type" :options="vectorStoreOptions" />
                    </n-form-item>
                  </n-grid-item>
                  <n-grid-item>
                    <n-form-item :label="t('legacy.distance_metric')">
                      <n-select v-model:value="knowledgeForm.vectorStore.distanceMetric" :options="distanceMetricOptions" />
                    </n-form-item>
                  </n-grid-item>
                  <n-grid-item>
                    <n-form-item :label="t('legacy.endpoint')">
                      <n-input v-model:value="knowledgeForm.vectorStore.endpoint" placeholder="http://127.0.0.1:8080" />
                    </n-form-item>
                  </n-grid-item>
                  <n-grid-item>
                    <n-form-item :label="t('legacy.collection_class_name')">
                      <n-input v-model:value="knowledgeForm.vectorStore.collectionName" />
                    </n-form-item>
                  </n-grid-item>
                  <n-grid-item>
                    <n-form-item label="API Key">
                      <n-input
                        v-model:value="knowledgeForm.vectorStore.apiKey"
                        type="password"
                        show-password-on="click"
                        :placeholder="knowledgeForm.vectorStore.apiKeyMasked ? t('legacy.leave_blank_to_keep_the_saved_key') : t('legacy.leave_blank_for_local_weaviate')"
                      />
                    </n-form-item>
                  </n-grid-item>
                </n-grid>

                <div class="knowledge-section-title">{{ t('legacy.underlying_retrieval_strategy') }}</div>
                <n-grid :cols="2" :x-gap="16" :y-gap="10">
                  <n-grid-item>
                    <n-form-item :label="t('legacy.min_chunk_size')">
                      <n-input-number v-model:value="knowledgeForm.parse.minChunkSize" :min="50" :max="4000" :step="50" style="width: 100%" />
                    </n-form-item>
                  </n-grid-item>
                  <n-grid-item>
                    <n-form-item :label="t('legacy.candidate_top_k')">
                      <n-input-number v-model:value="knowledgeForm.retrieval.candidateTopK" :min="knowledgeForm.retrieval.topN" :max="500" style="width: 100%" />
                    </n-form-item>
                  </n-grid-item>
                  <n-grid-item>
                    <n-form-item :label="t('legacy.score_threshold')">
                      <n-input-number v-model:value="knowledgeForm.retrieval.scoreThreshold" :min="0" :max="1" :step="0.01" style="width: 100%" />
                    </n-form-item>
                  </n-grid-item>
                  <n-grid-item>
                    <n-form-item :label="t('legacy.enable_metadata_filtering')">
                      <n-switch v-model:value="knowledgeForm.retrieval.metadataFiltersEnabled" />
                    </n-form-item>
                  </n-grid-item>
                </n-grid>

                <div class="knowledge-section-title">{{ t('legacy.hybrid_retrieval_details') }}</div>
                <n-grid :cols="2" :x-gap="16" :y-gap="10">
                  <n-grid-item>
                    <n-form-item :label="t('legacy.vector_weight')">
                      <n-input-number v-model:value="knowledgeForm.retrieval.hybrid.vectorWeight" :min="0" :max="1" :step="0.05" style="width: 100%" />
                    </n-form-item>
                  </n-grid-item>
                  <n-grid-item>
                    <n-form-item :label="t('legacy.keyword_weight')">
                      <n-input-number v-model:value="knowledgeForm.retrieval.hybrid.keywordWeight" :min="0" :max="1" :step="0.05" style="width: 100%" />
                    </n-form-item>
                  </n-grid-item>
                  <n-grid-item>
                    <n-form-item :label="t('legacy.fusion_method')">
                      <n-select v-model:value="knowledgeForm.retrieval.hybrid.fusionMethod" :options="fusionMethodOptions" />
                    </n-form-item>
                  </n-grid-item>
                  <n-grid-item>
                    <n-form-item label="RRF K">
                      <n-input-number v-model:value="knowledgeForm.retrieval.hybrid.rrfK" :min="1" :max="1000" style="width: 100%" />
                    </n-form-item>
                  </n-grid-item>
                  <n-grid-item>
                    <n-form-item :label="t('legacy.keyword_analyzer')">
                      <n-select v-model:value="knowledgeForm.retrieval.hybrid.keywordAnalyzer" :options="keywordAnalyzerOptions" />
                    </n-form-item>
                  </n-grid-item>
                  <n-grid-item>
                    <n-form-item :label="t('legacy.keyword_top_k')">
                      <n-input-number v-model:value="knowledgeForm.retrieval.hybrid.keywordTopK" :min="1" :max="500" style="width: 100%" />
                    </n-form-item>
                  </n-grid-item>
                </n-grid>

                <div class="knowledge-section-title">{{ t('legacy.rerank_service_details') }}</div>
                <n-grid :cols="2" :x-gap="16" :y-gap="10">
                  <n-grid-item :span="2">
                    <n-form-item :label="t('legacy.select_rerank_model')" :required="knowledgeForm.retrieval.rerank.enabled">
                      <ModelCapabilitySelect
                        v-model="knowledgeForm.retrieval.rerank.modelInstanceId"
                        capability="rerank"
                        :placeholder="t('legacy.select_a_rerank_model_from_model_center')"
                      />
                      <div class="field-help">{{ t('legacy.only_enabled_model_center_models_with_rerank_capability_are') }}</div>
                    </n-form-item>
                  </n-grid-item>
                  <n-grid-item>
                    <n-form-item :label="t('legacy.rerank_timeout_s')">
                      <n-input-number v-model:value="knowledgeForm.retrieval.rerank.timeoutSeconds" :min="1" :max="120" style="width: 100%" />
                    </n-form-item>
                  </n-grid-item>
                  <n-grid-item>
                    <n-form-item :label="t('legacy.rerank_score_threshold')">
                      <n-input-number v-model:value="knowledgeForm.retrieval.rerank.scoreThreshold" :min="0" :max="1" :step="0.01" style="width: 100%" />
                    </n-form-item>
                  </n-grid-item>
                  <n-grid-item>
                    <n-form-item :label="t('legacy.on_rerank_failure')">
                      <n-select v-model:value="knowledgeForm.retrieval.rerank.fallbackPolicy" :options="rerankFallbackOptions" />
                    </n-form-item>
                  </n-grid-item>
                </n-grid>
                </div>
              </template>
            </div>
          </n-form>
        </section>
      </n-spin>
    </main>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue';
import { NAlert, useMessage } from 'naive-ui';
import axios from 'axios';
import { onBeforeRouteLeave, onBeforeRouteUpdate, useRoute, useRouter } from 'vue-router';
import { t, useLocale } from '@/composables/i18n';
import { useTheme } from '@/composables/theme';
import { getAdminTimezone, getBrowserTimezone, setAdminTimezone } from '@/composables/adminTimezone';
import SearchProviderGuide from '@/components/search-provider/SearchProviderGuide.vue';
import ModelCapabilitySelect from '@/components/models/ModelCapabilitySelect.vue';
import PresentationSettingsPanel from '@/components/settings/PresentationSettingsPanel.vue';
import ShortcutSettingsPanel from '@/components/settings/ShortcutSettingsPanel.vue';
import ShortcutSchemeOverview from '@/components/settings/ShortcutSchemeOverview.vue';
import TopicAdmissionPanel from '@/components/settings/TopicAdmissionPanel.vue';
import KnowledgeSourceSettingsPanel from '@/components/settings/KnowledgeSourceSettingsPanel.vue';
import {
  fetchExternalSearchProviders,
  saveExternalSearchProvider,
  setDefaultExternalSearchProvider,
  testExternalSearchProvider,
  type ExternalSearchProvider,
  type ExternalSearchProviderItem,
  type ExternalSearchTestResult,
} from '@/api/external-search';
import {
  fetchPageCollectionSettings,
  savePageCollectionSettings,
  type PageCollectionSettings,
} from '@/api/page-collection';
import {
  fetchKnowledgeSettings,
  saveKnowledgeSettings,
  type KnowledgeSettings,
} from '@/api/knowledge-settings';
import adminProductUiExtension from '@movo-admin-product-extension';

const message = useMessage();
type SettingsSection = 'general' | 'shortcuts' | 'presentation' | 'external-search' | 'page-collection' | 'knowledge' | 'topic-admission';
type ShortcutView = 'schemes' | 'default';

const route = useRoute();
const router = useRouter();
const sectionRouteMap: Record<SettingsSection, string> = {
  general: '/settings',
  shortcuts: '/settings/shortcuts',
  presentation: '/settings/presentation',
  'external-search': '/settings/external-search',
  'page-collection': '/settings/page-collection',
  knowledge: '/settings/knowledge',
  'topic-admission': '/settings/topic-admission',
};
const activeSection = ref<SettingsSection>('general');
const hasShortcutSchemes = Boolean(adminProductUiExtension.shortcutSettingsExtension);
const shortcutView = ref<ShortcutView>(hasShortcutSchemes ? 'schemes' : 'default');
const shortcutSettingsRef = ref<InstanceType<typeof ShortcutSettingsPanel> | null>(null);
const knowledgeSourceRef = ref<InstanceType<typeof KnowledgeSourceSettingsPanel> | null>(null);
const knowledgeParseSnapshot = ref('');
const knowledgeParseDirty = computed(() => Boolean(knowledgeParseSnapshot.value) && JSON.stringify(knowledgeForm) !== knowledgeParseSnapshot.value);
const hasKnowledgeEdits = computed(() => Boolean(knowledgeSourceRef.value?.hasUnsavedChanges) || knowledgeParseDirty.value);

function confirmShortcutNavigation(): boolean {
  if (activeSection.value !== 'shortcuts' || shortcutView.value !== 'default' || !shortcutSettingsRef.value?.hasUnsavedChanges) return true;
  return window.confirm(t('legacy.quick_access_has_unsaved_changes_discard_them_and_leave'));
}

function confirmSettingsNavigation(): boolean {
  if (!confirmShortcutNavigation()) return false;
  if (activeSection.value === 'knowledge' && hasKnowledgeEdits.value) {
    return window.confirm(t('knowledgeSource.unsavedConfirm'));
  }
  return true;
}

function warnBeforeUnload(event: BeforeUnloadEvent) {
  if (activeSection.value !== 'knowledge' || !hasKnowledgeEdits.value) return;
  event.preventDefault();
  event.returnValue = '';
}

function sectionFromPath(path: string): SettingsSection {
  if (path.includes('/settings/topic-admission')) return 'topic-admission';
  if (path.includes('/settings/shortcuts')) return 'shortcuts';
  if (path.includes('/settings/presentation')) return 'presentation';
  if (path.includes('/settings/external-search')) return 'external-search';
  if (path.includes('/settings/page-collection')) return 'page-collection';
  if (path.includes('/settings/knowledge')) return 'knowledge';
  return 'general';
}

function shortcutViewFromPath(path: string): ShortcutView {
  if (!hasShortcutSchemes) return 'default';
  return path.includes('/settings/shortcuts/default') ? 'default' : 'schemes';
}

function switchShortcutView(view: ShortcutView) {
  if (view === 'schemes' && !hasShortcutSchemes) return;
  if (view !== shortcutView.value && !confirmShortcutNavigation()) return;
  shortcutView.value = view;
  const target = view === 'default' ? '/settings/shortcuts/default' : '/settings/shortcuts';
  if (route.path !== target) router.push(target);
}

function switchSection(section: SettingsSection) {
  if (section !== activeSection.value && !confirmSettingsNavigation()) return;
  activeSection.value = section;
  const target = sectionRouteMap[section];
  if (route.path !== target) {
    router.push(target);
  }
}

onBeforeRouteLeave(() => confirmSettingsNavigation());
onBeforeRouteUpdate(() => confirmSettingsNavigation());

watch(
  () => route.path,
  (path) => {
    activeSection.value = sectionFromPath(path);
    shortcutView.value = shortcutViewFromPath(path);
  },
  { immediate: true },
);

const { setLocale, locale: currentLocale } = useLocale();
const { setTheme, theme: currentTheme } = useTheme();

const languageSelectOptions = [
  { label: '简体中文', value: 'zh-CN' },
  { label: 'English', value: 'en-US' },
];

const timezoneSelectOptions = computed(() => [
  {
    label: currentLocale.value === 'en-US'
      ? 'China Standard Time (GMT+8) - Asia/Shanghai'
      : '中国标准时间 (GMT+8) - Asia/Shanghai',
    value: 'Asia/Shanghai',
  },
  {
    label: currentLocale.value === 'en-US'
      ? 'Japan Standard Time (GMT+9) - Asia/Tokyo'
      : '日本标准时间 (GMT+9) - Asia/Tokyo',
    value: 'Asia/Tokyo',
  },
  {
    label: currentLocale.value === 'en-US'
      ? 'Coordinated Universal Time (UTC) - UTC'
      : '协调世界时 (UTC) - UTC',
    value: 'UTC',
  },
  {
    label: currentLocale.value === 'en-US'
      ? 'Central European Time (GMT+1) - Europe/Berlin'
      : '欧洲中部时间 (GMT+1) - Europe/Berlin',
    value: 'Europe/Berlin',
  },
  {
    label: currentLocale.value === 'en-US'
      ? 'Greenwich Mean Time (GMT) - Europe/London'
      : '格林威治标准时间 (GMT) - Europe/London',
    value: 'Europe/London',
  },
  {
    label: currentLocale.value === 'en-US'
      ? 'Eastern Standard Time (GMT-5) - America/New_York'
      : '美国东部标准时间 (GMT-5) - America/New_York',
    value: 'America/New_York',
  },
  {
    label: currentLocale.value === 'en-US'
      ? 'Central Standard Time (GMT-6) - America/Chicago'
      : '美国中部标准时间 (GMT-6) - America/Chicago',
    value: 'America/Chicago',
  },
  {
    label: currentLocale.value === 'en-US'
      ? 'Pacific Standard Time (GMT-8) - America/Los_Angeles'
      : '太平洋标准时间 (GMT-8) - America/Los_Angeles',
    value: 'America/Los_Angeles',
  },
  {
    label: currentLocale.value === 'en-US'
      ? 'Australian Eastern Standard Time (GMT+10) - Australia/Sydney'
      : '澳大利亚东部标准时间 (GMT+10) - Australia/Sydney',
    value: 'Australia/Sydney',
  },
]);

function getLocalTimezone(): string {
  return getBrowserTimezone();
}

const storedTimezone = getAdminTimezone() || getLocalTimezone();

const generalForm = reactive({
  language: currentLocale.value,
  timezone: storedTimezone,
  themeMode: currentTheme.value,
});

function handleThemeChange(val: string) {
  setTheme(val as any);
}

function saveGeneralSettings() {
  setLocale(generalForm.language as any);
  setAdminTimezone(generalForm.timezone);
  message.success(t('legacy.general_settings_saved'));
}

const providers = ref<ExternalSearchProviderItem[]>([]);
const selectedProvider = ref<ExternalSearchProvider>('deepseek');
const loading = ref(false);
const saving = ref(false);
const testing = ref(false);
const testQuery = ref('DeepSeek latest news');
const testResult = ref<ExternalSearchTestResult | null>(null);
const pageCollectionSettings = ref<PageCollectionSettings | null>(null);
const pageCollectionLoading = ref(false);
const pageCollectionSaving = ref(false);
const knowledgeLoading = ref(false);
const knowledgeSourceMode = ref<'movo' | 'external'>('movo');
const knowledgeSaving = ref(false);
const showKnowledgeAdvanced = ref(false);

const form = reactive({
  enabled: true,
  apiKey: '',
  endpoint: '',
  baseUrl: '',
  model: '',
});

const activeProvider = computed(() => providers.value.find((item) => item.provider === selectedProvider.value) || null);
const pageCollectionForm = reactive({
  enabled: false,
  apiKey: '',
});

function defaultKnowledgeSettings(): KnowledgeSettings {
  return {
    parse: { minChunkSize: 800, maxChunkSize: 1500, chunkOverlap: 120 },
    embedding: {
      provider: 'model_center',
      modelInstanceId: '',
      dimension: 1536,
      batchSize: 32,
      timeoutSeconds: 30,
    },
    vectorStore: {
      type: 'weaviate',
      endpoint: 'http://127.0.0.1:8080',
      apiKey: '',
      apiKeyMasked: '',
      collectionName: 'AskAIKnowledgeChunks',
      distanceMetric: 'cosine',
      tenantIsolation: true,
      recreateIndexAllowed: false,
    },
    retrieval: {
      mode: 'vector',
      topN: 10,
      candidateTopK: 50,
      scoreThreshold: 0,
      metadataFiltersEnabled: true,
      hybrid: {
        vectorWeight: 0.7,
        keywordWeight: 0.3,
        fusionMethod: 'rrf',
        rrfK: 60,
        keywordAnalyzer: 'standard',
        keywordTopK: 50,
      },
      rerank: {
        enabled: false,
        provider: 'model_center',
        modelInstanceId: '',
        model: '',
        endpoint: '',
        topK: 20,
        scoreThreshold: 0,
        timeoutSeconds: 10,
        fallbackPolicy: 'return_vector_results',
      },
    },
    context: {
      includeTitlePath: true,
      includePageNo: true,
      includeDocumentMeta: true,
      neighborChunksBefore: 0,
      neighborChunksAfter: 0,
      maxContextTokens: 6000,
    },
    citation: {
      required: true,
      returnSourceChunks: true,
      returnRawChunkRefs: true,
      enablePageJump: true,
      maxCount: 5,
    },
    index: {
      autoIndexAfterParse: true,
      batchSize: 32,
      retryTimes: 3,
      retryIntervalSeconds: 30,
      versioningEnabled: true,
    },
    updatedAt: '',
  };
}

const knowledgeForm = reactive<KnowledgeSettings>(defaultKnowledgeSettings());

const vectorStoreOptions = [
  { label: 'Weaviate', value: 'weaviate' },
  { label: 'Qdrant', value: 'qdrant' },
  { label: 'Milvus', value: 'milvus' },
  { label: 'Elasticsearch', value: 'elasticsearch' },
  { label: 'OpenSearch', value: 'opensearch' },
  { label: 'pgvector', value: 'pgvector' },
];

const distanceMetricOptions = [
  { label: 'Cosine', value: 'cosine' },
  { label: 'Dot Product', value: 'dot' },
  { label: 'L2', value: 'l2' },
];

const retrievalModeOptions = [
  { label: t('legacy.vector_retrieval'), value: 'vector' },
  { label: t('legacy.hybrid_retrieval'), value: 'hybrid' },
];

const fusionMethodOptions = [
  { label: 'RRF', value: 'rrf' },
  { label: t('legacy.weighted_fusion'), value: 'weighted' },
];

const keywordAnalyzerOptions = [
  { label: t('legacy.standard'), value: 'standard' },
  { label: t('legacy.cjk_chinese_japanese_korean'), value: 'cjk' },
  { label: 'IK', value: 'ik' },
];

const rerankFallbackOptions = [
  { label: t('legacy.return_vector_results_on_failure'), value: 'return_vector_results' },
  { label: t('legacy.return_empty_on_failure'), value: 'return_empty' },
  { label: t('legacy.fail_directly_on_failure'), value: 'fail' },
];

function healthTagType(status: string) {
  if (status === 'healthy') return 'success';
  if (status === 'failed') return 'error';
  return 'default';
}

function healthText(status: string) {
  if (status === 'healthy') return t('legacy.passed');
  if (status === 'failed') return t('legacy.test_failed');
  return t('legacy.untested');
}

function fillForm(item: ExternalSearchProviderItem) {
  form.enabled = item.enabled;
  form.apiKey = '';
  form.endpoint = item.endpoint;
  form.baseUrl = item.baseUrl;
  form.model = item.model;
  testResult.value = null;
}

function selectProvider(provider: ExternalSearchProvider) {
  selectedProvider.value = provider;
  const item = providers.value.find((row) => row.provider === provider);
  if (item) fillForm(item);
}

async function loadProviders() {
  loading.value = true;
  try {
    providers.value = await fetchExternalSearchProviders();
    const current = providers.value.find((item) => item.provider === selectedProvider.value)
      || providers.value.find((item) => item.isDefault)
      || providers.value[0];
    if (current) {
      selectedProvider.value = current.provider;
      fillForm(current);
    }
  } finally {
    loading.value = false;
  }
}

async function loadPageCollection() {
  pageCollectionLoading.value = true;
  try {
    const settings = await fetchPageCollectionSettings();
    pageCollectionSettings.value = settings;
    pageCollectionForm.enabled = settings.enabled;
    pageCollectionForm.apiKey = '';
  } finally {
    pageCollectionLoading.value = false;
  }
}

function applyKnowledgeSettings(settings: KnowledgeSettings) {
  Object.assign(knowledgeForm.parse, settings.parse);
  Object.assign(knowledgeForm.embedding, settings.embedding);
  knowledgeForm.embedding.provider = 'model_center';
  Object.assign(knowledgeForm.vectorStore, settings.vectorStore, { apiKey: '' });
  Object.assign(knowledgeForm.retrieval, settings.retrieval);
  Object.assign(knowledgeForm.retrieval.hybrid, settings.retrieval.hybrid);
  Object.assign(knowledgeForm.retrieval.rerank, settings.retrieval.rerank);
  knowledgeForm.retrieval.rerank.provider = 'model_center';
  Object.assign(knowledgeForm.context, settings.context);
  Object.assign(knowledgeForm.citation, settings.citation);
  Object.assign(knowledgeForm.index, settings.index);
  knowledgeForm.updatedAt = settings.updatedAt;
}

async function loadKnowledgeParseSettings() {
  knowledgeLoading.value = true;
  try {
    const settings = await fetchKnowledgeSettings();
    applyKnowledgeSettings(settings);
    knowledgeParseSnapshot.value = JSON.stringify(knowledgeForm);
  } finally {
    knowledgeLoading.value = false;
  }
}

async function saveCurrent() {
  saving.value = true;
  try {
    const provider = selectedProvider.value;
    await saveExternalSearchProvider(provider, { ...form });
    await loadProviders();
    message.success(t('legacy.configuration_saved'));
  } finally {
    saving.value = false;
  }
}

async function makeDefault() {
  if (!form.enabled) return;
  await saveCurrent();
  await setDefaultExternalSearchProvider(selectedProvider.value);
  message.success(t('legacy.default_search_provider_updated'));
  await loadProviders();
}

async function savePageCollection() {
  pageCollectionSaving.value = true;
  try {
    const saved = await savePageCollectionSettings({ ...pageCollectionForm });
    pageCollectionSettings.value = saved;
    pageCollectionForm.enabled = saved.enabled;
    pageCollectionForm.apiKey = '';
    message.success(t('legacy.configuration_saved'));
  } finally {
    pageCollectionSaving.value = false;
  }
}

async function saveKnowledgeParse() {
  knowledgeSaving.value = true;
  try {
    if (!knowledgeForm.embedding.modelInstanceId) {
      message.error(t('legacy.select_an_embedding_model'));
      return;
    }
    if (knowledgeForm.retrieval.rerank.enabled && !knowledgeForm.retrieval.rerank.modelInstanceId) {
      message.error(t('legacy.select_a_rerank_model_after_enabling_reranking'));
      return;
    }
    knowledgeForm.embedding.provider = 'model_center';
    knowledgeForm.retrieval.rerank.provider = 'model_center';
    knowledgeForm.retrieval.rerank.model = '';
    knowledgeForm.retrieval.rerank.endpoint = '';
    knowledgeForm.vectorStore.tenantIsolation = true;
    const saved = await saveKnowledgeSettings(JSON.parse(JSON.stringify(knowledgeForm)));
    applyKnowledgeSettings(saved);
    knowledgeParseSnapshot.value = JSON.stringify(knowledgeForm);
    message.success(t('legacy.configuration_saved'));
  } finally {
    knowledgeSaving.value = false;
  }
}

async function saveKnowledgeConfiguration() {
  if (!await knowledgeSourceRef.value?.save()) return;
  if (knowledgeParseDirty.value) {
    await saveKnowledgeParse();
  }
}

async function refreshKnowledgeConfiguration() {
  if (hasKnowledgeEdits.value && !window.confirm(t('knowledgeSource.unsavedConfirm'))) return;
  await Promise.all([knowledgeSourceRef.value?.load(), loadKnowledgeParseSettings()]);
}

async function runTest() {
  testing.value = true;
  testResult.value = null;
  try {
    const result = await testExternalSearchProvider(selectedProvider.value, {
      query: testQuery.value,
      apiKey: form.apiKey,
      endpoint: form.endpoint,
      baseUrl: form.baseUrl,
      model: form.model,
    });
    const normalizedResult: ExternalSearchTestResult = {
      ok: Boolean(result?.ok),
      provider: result?.provider || selectedProvider.value,
      resultCount: Number(result?.resultCount || 0),
      sampleResults: Array.isArray(result?.sampleResults) ? result.sampleResults : [],
      message: String(result?.message || (result?.ok ? t('legacy.connection_successful') : t('legacy.test_completed_but_returned_no_displayable_result'))),
    };
    testResult.value = normalizedResult;
    if (normalizedResult.ok) {
      message.success(t('legacy.connection_test_passed'));
    } else {
      message.error(normalizedResult.message || t('legacy.connection_test_failed'));
    }
    const index = providers.value.findIndex((item) => item.provider === selectedProvider.value);
    if (index >= 0) {
      providers.value[index] = {
        ...providers.value[index],
        healthStatus: normalizedResult.ok ? 'healthy' : 'failed',
        lastError: normalizedResult.ok ? '' : normalizedResult.message,
      };
    }
  } catch (error) {
    const detail = axios.isAxiosError(error)
      ? error.response?.data?.detail || error.response?.data?.message || error.message
      : error instanceof Error
        ? error.message
        : String(error);
    const errorMessage = String(detail || t('legacy.connection_test_failed'));
    testResult.value = {
      ok: false,
      provider: selectedProvider.value,
      resultCount: 0,
      sampleResults: [],
      message: errorMessage,
    };
    message.error(errorMessage);
  } finally {
    testing.value = false;
  }
}

onMounted(() => {
  window.addEventListener('beforeunload', warnBeforeUnload);
  loadProviders();
  loadPageCollection();
  loadKnowledgeParseSettings();
});
onBeforeUnmount(() => window.removeEventListener('beforeunload', warnBeforeUnload));
</script>

<style scoped>
.settings-page {
  display: grid;
  grid-template-columns: 220px minmax(0, 1fr);
  gap: 20px;
  padding: 12px;
  height: calc(100vh - 64px);
  box-sizing: border-box;
  background: #f5f7fb;
  overflow: hidden;
}

.settings-nav {
  background: #fff;
  border: 1px solid #e6eaf2;
  border-radius: 8px;
  padding: 10px;
  height: 100%;
  box-sizing: border-box;
  overflow: auto;
}

.settings-nav-item {
  width: 100%;
  min-height: 44px;
  border: 0;
  border-radius: 6px;
  background: transparent;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 0 12px;
  color: #394150;
  cursor: pointer;
  text-align: left;
}

.shortcut-page-tabs {
  display: inline-flex;
  gap: 4px;
  margin-bottom: 18px;
  padding: 4px;
  border: 1px solid #e5eaf2;
  border-radius: 10px;
  background: #f7f9fc;
}

.shortcut-page-tabs button {
  border: 0;
  border-radius: 7px;
  padding: 7px 14px;
  color: #667085;
  background: transparent;
  cursor: pointer;
  font-size: 13px;
}

.shortcut-page-tabs button.active {
  color: #1d4ed8;
  background: #fff;
  box-shadow: 0 1px 3px rgba(15, 23, 42, .08);
  font-weight: 600;
}

.settings-nav-item.active {
  background: #eef4ff;
  color: #1f5eff;
  font-weight: 600;
}

.nav-icon {
  width: 16px;
  height: 16px;
  flex-shrink: 0;
  stroke: currentColor;
}

.general-settings-content {
  padding-top: 24px;
  max-width: 580px;
}

.theme-radio-wrapper {
  display: flex;
  align-items: center;
  width: 100%;
}

/* 暗色模式下设置页的外容器及各局部块的精美适配 */
html.dark .settings-page {
  background: #0f1117;
}

html.dark .settings-nav,
html.dark .settings-main {
  background: #111827;
  border-color: #263044;
}

html.dark .settings-title {
  color: #f4f4f5;
}

html.dark .settings-subtitle {
  color: #a1a1aa;
}

html.dark .settings-nav-item {
  color: #cbd5e1;
}

html.dark .settings-nav-item.active {
  background: rgba(54, 106, 255, 0.16);
  color: #93c5fd;
}

html.dark .provider-row {
  border-color: #263044;
  background: #111827;
}

html.dark .provider-row.selected {
  border-color: #3b82f6;
  box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.2);
}

html.dark .provider-name {
  color: #f4f4f5;
}

html.dark .provider-editor {
  border-color: #263044;
  background: #111827;
}

html.dark .editor-title {
  color: #f4f4f5;
}

html.dark .editor-state {
  color: #a1a1aa;
}

html.dark .settings-header {
  border-bottom-color: #263044;
}

html.dark .sample-row,
html.dark .single-provider-editor {
  border-color: #263044;
  background: #0f172a;
}

html.dark .sample-title {
  color: #f8fafc;
}

html.dark .sample-snippet {
  color: #cbd5e1;
}

html.dark .provider-row:hover,
html.dark .settings-nav-item:hover {
  background: rgba(148, 163, 184, 0.08);
}

html.dark .general-settings-content {
  color: #e5e7eb;
}

html.dark .sample-row {
  border-color: #2c2c32;
  background: #202024;
}

html.dark .sample-title {
  color: #f4f4f5;
}

html.dark .sample-snippet {
  color: #a1a1aa;
}

.provider-name-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 10px;
}

.provider-row-icon {
  width: 16px;
  height: 16px;
  color: #8b96a8;
  flex-shrink: 0;
}

.provider-row.selected .provider-row-icon {
  color: #2f6bff;
}

.title-decor-icon {
  width: 20px;
  height: 20px;
  color: #366aff;
  flex-shrink: 0;
}

.input-prefix-icon {
  width: 16px;
  height: 16px;
  color: #8b96a8;
}

.settings-main {
  min-width: 0;
  min-height: 0;
  background: #fff;
  border: 1px solid #e6eaf2;
  border-radius: 8px;
  padding: 22px;
  overflow: auto;
}

.settings-header {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  align-items: flex-start;
  padding-bottom: 18px;
  border-bottom: 1px solid #eef1f6;
}

.settings-title {
  font-size: 22px;
  font-weight: 700;
  color: #172033;
}

.settings-subtitle {
  margin-top: 4px;
  color: #667085;
  font-size: 13px;
}

.provider-layout {
  display: grid;
  grid-template-columns: 300px minmax(0, 1fr);
  gap: 18px;
  padding-top: 18px;
}

.provider-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.provider-row {
  border: 1px solid #e6eaf2;
  background: #fff;
  border-radius: 8px;
  padding: 14px;
  text-align: left;
  cursor: pointer;
}

.provider-row.selected {
  border-color: #2f6bff;
  box-shadow: 0 0 0 3px rgba(47, 107, 255, 0.1);
}

.provider-name {
  font-weight: 700;
  color: #172033;
  margin-bottom: 10px;
}

.provider-meta {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}

.provider-editor {
  min-width: 0;
  border: 1px solid #e6eaf2;
  border-radius: 8px;
  padding: 18px;
}

.single-provider-editor {
  margin-top: 18px;
}

.editor-toolbar {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: center;
  margin-bottom: 18px;
}

.editor-title {
  font-size: 18px;
  font-weight: 700;
  color: #172033;
  display: flex;
  align-items: center;
  gap: 8px;
}

.editor-state {
  margin-top: 3px;
  color: #667085;
  font-size: 13px;
}

.provider-form {
  max-width: 880px;
}

.knowledge-form {
  max-width: 1040px;
}

.knowledge-settings-panel {
  margin-top: 18px;
}

.knowledge-config-card {
  border: 1px solid #e6eaf2;
  border-radius: 8px;
  background: #fff;
  padding: 18px;
}

.knowledge-config-card + .knowledge-config-card {
  margin-top: 16px;
}

.knowledge-card-title {
  margin-bottom: 14px;
  color: #172033;
  font-size: 15px;
  font-weight: 700;
  line-height: 1.4;
}

.knowledge-section-title {
  margin: 20px 0 12px;
  padding-top: 18px;
  border-top: 1px solid #eef1f6;
  font-size: 15px;
  font-weight: 700;
  color: #172033;
}

.knowledge-section-title:first-child {
  margin-top: 0;
  padding-top: 0;
  border-top: 0;
}

.field-help {
  margin-top: 6px;
  color: #667085;
  font-size: 12px;
  line-height: 1.5;
}

.knowledge-advanced {
  margin-top: 16px;
}

.knowledge-advanced-summary {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  border: 1px solid #e6eaf2;
  border-radius: 8px;
  background: #f8fafc;
  padding: 12px 14px;
}

.knowledge-advanced-panel {
  margin-top: 16px;
}

.knowledge-advanced-title {
  color: #172033;
  font-size: 14px;
  font-weight: 700;
}

.knowledge-advanced-desc {
  margin-top: 3px;
  color: #667085;
  font-size: 12px;
  line-height: 1.5;
}

.knowledge-advanced-note {
  margin: 14px 0 8px;
}

.test-actions {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-top: 4px;
}

.test-result {
  margin-top: 14px;
}

.test-result-title {
  font-weight: 700;
}

.test-result-message {
  margin-top: 4px;
  word-break: break-word;
}

.sample-results {
  margin-top: 16px;
  display: grid;
  gap: 10px;
}

.sample-row {
  border: 1px solid #eef1f6;
  border-radius: 8px;
  padding: 12px;
  background: #fafbfe;
}

.sample-title {
  font-weight: 700;
  color: #172033;
}

.sample-url {
  margin-top: 3px;
  color: #1f5eff;
  font-size: 12px;
  word-break: break-all;
}

.sample-snippet {
  margin-top: 6px;
  color: #667085;
  line-height: 1.55;
}

.last-error {
  margin-top: 16px;
}

@media (max-width: 980px) {
  .settings-page,
  .provider-layout {
    grid-template-columns: 1fr;
  }
}
</style>
