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
        <span>{{ t('通用设置') }}</span>
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
        <span>{{ t('PPT 生成') }}</span>
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
        <span>{{ t('外部搜索') }}</span>
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
        <span>{{ t('页面采集') }}</span>
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
        <span>{{ t('文档解析') }}</span>
      </button>
    </aside>

    <main v-if="activeSection === 'general'" class="settings-main">
      <div class="settings-header">
        <div>
          <div class="settings-title">{{ t('通用设置') }}</div>
          <div class="settings-subtitle">{{ t('配置管理后台的语言、时区及界面主题显示。') }}</div>
        </div>
        <n-space>
          <n-button type="primary" @click="saveGeneralSettings">{{ t('保存配置') }}</n-button>
        </n-space>
      </div>

      <div class="general-settings-content">
        <n-form class="provider-form" label-placement="top">
          <n-grid :cols="2" :x-gap="16" :y-gap="16">
            <n-grid-item :span="2">
              <n-form-item :label="t('界面语言')">
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
              <n-form-item :label="t('系统时区')">
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
              <n-form-item :label="t('界面主题')">
                <div class="theme-radio-wrapper">
                  <n-radio-group v-model:value="generalForm.themeMode" @update:value="handleThemeChange">
                    <n-radio-button value="light">{{ t('浅色模式') }}</n-radio-button>
                    <n-radio-button value="dark">{{ t('深色模式') }}</n-radio-button>
                    <n-radio-button value="system">{{ t('跟随系统') }}</n-radio-button>
                  </n-radio-group>
                </div>
              </n-form-item>
            </n-grid-item>
          </n-grid>
        </n-form>
      </div>
    </main>

    <main v-else-if="activeSection === 'presentation'" class="settings-main">
      <PresentationSettingsPanel />
    </main>

    <main v-else-if="activeSection === 'external-search'" class="settings-main">
      <div class="settings-header">
        <div>
          <div class="settings-title">{{ t('外部搜索') }}</div>
          <div class="settings-subtitle">{{ t('配置 web_search 默认调用的外部搜索源。') }}</div>
        </div>
        <n-space>
          <n-button secondary :loading="loading" @click="loadProviders">{{ t('刷新') }}</n-button>
          <n-button type="primary" :loading="saving" @click="saveCurrent">{{ t('保存配置') }}</n-button>
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
                  <n-tag v-if="item.isDefault" type="info" size="small" :bordered="false">{{ t('默认') }}</n-tag>
                  <n-tag :type="item.enabled ? 'success' : 'default'" size="small" :bordered="false">
                    {{ item.enabled ? t('启用') : t('禁用') }}
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
                <div class="editor-state">{{ activeProvider.apiKeyMasked || t('未保存 API Key') }}</div>
              </div>
              <n-space>
                <n-switch v-model:value="form.enabled" />
                <n-button secondary :disabled="activeProvider.isDefault" @click="makeDefault">
                  {{ activeProvider.isDefault ? t('当前默认') : t('设为默认') }}
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
                      :placeholder="activeProvider.apiKeyMasked ? t('留空则保留已保存 Key') : t('填写 API Key')"
                    >
                      <template #prefix>
                        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="input-prefix-icon">
                          <path d="m21 2-2 2m-7.61 7.61a5.5 5.5 0 1 1-7.778 7.778 5.5 5.5 0 0 1 7.777-7.777zm0 0L15.5 7.5m0 0 1.5 1.5M15.5 7.5 14 6" />
                        </svg>
                      </template>
                    </n-input>
                  </n-form-item>
                </n-grid-item>

                <n-grid-item v-if="selectedProvider === 'baidu_qianfan'" :span="2">
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
                  <n-form-item :label="t('测试查询')">
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
              <n-button :loading="testing" @click="runTest">{{ t('测试连接') }}</n-button>
            </div>

            <n-alert
              v-if="testResult"
              :type="testResult.ok ? 'success' : 'error'"
              :bordered="false"
              class="test-result"
            >
              <div class="test-result-title">
                {{ testResult.ok ? t('连接测试通过') : t('连接测试失败') }}
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
          <div class="settings-title">{{ t('页面采集') }}</div>
          <div class="settings-subtitle">{{ t('配置网页正文采集能力，用于从 URL 提取页面内容。') }}</div>
        </div>
        <n-space>
          <n-button secondary :loading="pageCollectionLoading" @click="loadPageCollection">{{ t('刷新') }}</n-button>
          <n-button type="primary" :loading="pageCollectionSaving" @click="savePageCollection">{{ t('保存配置') }}</n-button>
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
              <div class="editor-state">{{ pageCollectionSettings?.apiKeyMasked || t('未保存 API Key') }}</div>
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
                    :placeholder="pageCollectionSettings?.apiKeyMasked ? t('留空则保留已保存 Key') : t('填写 API Key')"
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
          <div class="settings-title">{{ t('知识库问答调试') }}</div>
          <div class="settings-subtitle">{{ t('调整少量关键参数，观察内部知识库问答的命中片段、引用来源和回答质量。') }}</div>
        </div>
        <n-space>
          <n-button secondary :loading="knowledgeLoading" @click="loadKnowledgeParseSettings">{{ t('刷新') }}</n-button>
          <n-button type="primary" :loading="knowledgeSaving" @click="saveKnowledgeParse">{{ t('保存') }}</n-button>
        </n-space>
      </div>

      <n-spin :show="knowledgeLoading">
        <section class="knowledge-settings-panel">
          <n-form class="provider-form knowledge-form" label-placement="top">
            <div class="knowledge-config-card">
              <div class="knowledge-card-title">{{ t('文档分段设置') }}</div>
              <n-grid :cols="2" :x-gap="16" :y-gap="10">
                <n-grid-item>
                  <n-form-item :label="t('每段最大长度')">
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
                  <n-form-item :label="t('相邻段落保留重叠')">
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
                    {{ t('这部分只影响新上传或重新学习后的文档。已经学习过的文档不会自动重新切段。') }}
                  </n-alert>
                </n-grid-item>
              </n-grid>
            </div>

            <div class="knowledge-config-card">
              <div class="knowledge-card-title">{{ t('问答效果设置') }}</div>
              <n-grid :cols="2" :x-gap="16" :y-gap="10">
                <n-grid-item>
                  <n-form-item :label="t('检索方式')">
                    <n-select v-model:value="knowledgeForm.retrieval.mode" :options="retrievalModeOptions" />
                  </n-form-item>
                </n-grid-item>
                <n-grid-item>
                  <n-form-item :label="t('先找多少个候选片段 (Top N)')">
                    <n-input-number v-model:value="knowledgeForm.retrieval.topN" :min="1" :max="50" style="width: 100%" />
                  </n-form-item>
                </n-grid-item>
                <n-grid-item>
                  <n-form-item :label="t('开启重排')">
                    <n-switch v-model:value="knowledgeForm.retrieval.rerank.enabled" />
                    <div class="field-help">{{ t('开启后会对召回的候选片段再按相关性重排，通常更准但会更慢。') }}</div>
                  </n-form-item>
                </n-grid-item>
                <n-grid-item>
                  <n-form-item :label="t('重排最多处理 (Top K)')">
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
                  <n-form-item :label="t('最多喂给模型的资料长度')">
                    <n-input-number v-model:value="knowledgeForm.context.maxContextTokens" :min="500" :max="200000" :step="500" style="width: 100%" />
                  </n-form-item>
                </n-grid-item>
                <n-grid-item>
                  <n-form-item :label="t('回答中最多展示来源')">
                    <n-input-number v-model:value="knowledgeForm.citation.maxCount" :min="1" :max="20" style="width: 100%" />
                  </n-form-item>
                </n-grid-item>
              </n-grid>
            </div>

            <div class="knowledge-advanced">
              <div class="knowledge-advanced-summary">
                <div>
                  <div class="knowledge-advanced-title">{{ t('高级配置') }}</div>
                  <div class="knowledge-advanced-desc">{{ t('模型、向量库、索引等参数已隐藏，普通问答测试通常不用修改。') }}</div>
                </div>
                <n-button secondary size="small" @click="showKnowledgeAdvanced = !showKnowledgeAdvanced">
                  {{ showKnowledgeAdvanced ? t('隐藏高级配置') : t('显示高级配置') }}
                </n-button>
              </div>
              <template v-if="showKnowledgeAdvanced">
                <div class="knowledge-config-card knowledge-advanced-panel">
                  <div class="knowledge-card-title">{{ t('高级配置') }}</div>
                  <n-alert type="default" :bordered="false" class="knowledge-advanced-note">
                    {{ t('这些配置主要给管理员和工程人员排查使用。普通问答测试通常不用修改。') }}
                  </n-alert>

                  <div class="knowledge-section-title">{{ t('向量模型') }}</div>
                  <n-grid :cols="2" :x-gap="16" :y-gap="10">
                  <n-grid-item :span="2">
                    <n-form-item :label="t('选择向量模型')" required>
                      <ModelCapabilitySelect
                        v-model="knowledgeForm.embedding.modelInstanceId"
                        capability="embedding"
                        :placeholder="t('请选择模型中心中的向量模型')"
                      />
                      <div class="field-help">{{ t('仅显示模型中心中已启用且支持向量能力的模型。') }}</div>
                    </n-form-item>
                  </n-grid-item>
                  <n-grid-item>
                    <n-form-item :label="t('向量维度')">
                      <n-input-number v-model:value="knowledgeForm.embedding.dimension" :min="1" :max="20000" style="width: 100%" />
                    </n-form-item>
                  </n-grid-item>
                  <n-grid-item>
                    <n-form-item :label="t('批量大小')">
                      <n-input-number v-model:value="knowledgeForm.embedding.batchSize" :min="1" :max="256" style="width: 100%" />
                    </n-form-item>
                  </n-grid-item>
                </n-grid>

                <div class="knowledge-section-title">{{ t('向量数据库') }}</div>
                <n-grid :cols="2" :x-gap="16" :y-gap="10">
                  <n-grid-item>
                    <n-form-item :label="t('数据库类型')">
                      <n-select v-model:value="knowledgeForm.vectorStore.type" :options="vectorStoreOptions" />
                    </n-form-item>
                  </n-grid-item>
                  <n-grid-item>
                    <n-form-item :label="t('距离算法')">
                      <n-select v-model:value="knowledgeForm.vectorStore.distanceMetric" :options="distanceMetricOptions" />
                    </n-form-item>
                  </n-grid-item>
                  <n-grid-item>
                    <n-form-item :label="t('服务地址')">
                      <n-input v-model:value="knowledgeForm.vectorStore.endpoint" placeholder="http://127.0.0.1:8080" />
                    </n-form-item>
                  </n-grid-item>
                  <n-grid-item>
                    <n-form-item :label="t('Collection / Class 名称')">
                      <n-input v-model:value="knowledgeForm.vectorStore.collectionName" />
                    </n-form-item>
                  </n-grid-item>
                  <n-grid-item>
                    <n-form-item label="API Key">
                      <n-input
                        v-model:value="knowledgeForm.vectorStore.apiKey"
                        type="password"
                        show-password-on="click"
                        :placeholder="knowledgeForm.vectorStore.apiKeyMasked ? t('留空则保留已保存 Key') : t('本地 Weaviate 可留空')"
                      />
                    </n-form-item>
                  </n-grid-item>
                </n-grid>

                <div class="knowledge-section-title">{{ t('底层检索策略') }}</div>
                <n-grid :cols="2" :x-gap="16" :y-gap="10">
                  <n-grid-item>
                    <n-form-item :label="t('最小分段长度')">
                      <n-input-number v-model:value="knowledgeForm.parse.minChunkSize" :min="50" :max="4000" :step="50" style="width: 100%" />
                    </n-form-item>
                  </n-grid-item>
                  <n-grid-item>
                    <n-form-item :label="t('候选召回数')">
                      <n-input-number v-model:value="knowledgeForm.retrieval.candidateTopK" :min="knowledgeForm.retrieval.topN" :max="500" style="width: 100%" />
                    </n-form-item>
                  </n-grid-item>
                  <n-grid-item>
                    <n-form-item :label="t('分数阈值')">
                      <n-input-number v-model:value="knowledgeForm.retrieval.scoreThreshold" :min="0" :max="1" :step="0.01" style="width: 100%" />
                    </n-form-item>
                  </n-grid-item>
                  <n-grid-item>
                    <n-form-item :label="t('每个文档最多取几个片段')">
                      <n-input-number v-model:value="knowledgeForm.retrieval.maxChunksPerDocument" :min="1" :max="50" style="width: 100%" />
                      <div class="field-help">{{ t('问答检索时使用，避免同一篇文档占用太多上下文；不影响文档上传后的实际切段。') }}</div>
                    </n-form-item>
                  </n-grid-item>
                  <n-grid-item>
                    <n-form-item :label="t('启用元数据过滤')">
                      <n-switch v-model:value="knowledgeForm.retrieval.metadataFiltersEnabled" />
                    </n-form-item>
                  </n-grid-item>
                </n-grid>

                <div class="knowledge-section-title">{{ t('混合检索细节') }}</div>
                <n-grid :cols="2" :x-gap="16" :y-gap="10">
                  <n-grid-item>
                    <n-form-item :label="t('向量权重')">
                      <n-input-number v-model:value="knowledgeForm.retrieval.hybrid.vectorWeight" :min="0" :max="1" :step="0.05" style="width: 100%" />
                    </n-form-item>
                  </n-grid-item>
                  <n-grid-item>
                    <n-form-item :label="t('关键词权重')">
                      <n-input-number v-model:value="knowledgeForm.retrieval.hybrid.keywordWeight" :min="0" :max="1" :step="0.05" style="width: 100%" />
                    </n-form-item>
                  </n-grid-item>
                  <n-grid-item>
                    <n-form-item :label="t('融合方式')">
                      <n-select v-model:value="knowledgeForm.retrieval.hybrid.fusionMethod" :options="fusionMethodOptions" />
                    </n-form-item>
                  </n-grid-item>
                  <n-grid-item>
                    <n-form-item label="RRF K">
                      <n-input-number v-model:value="knowledgeForm.retrieval.hybrid.rrfK" :min="1" :max="1000" style="width: 100%" />
                    </n-form-item>
                  </n-grid-item>
                  <n-grid-item>
                    <n-form-item :label="t('关键词分析器')">
                      <n-select v-model:value="knowledgeForm.retrieval.hybrid.keywordAnalyzer" :options="keywordAnalyzerOptions" />
                    </n-form-item>
                  </n-grid-item>
                  <n-grid-item>
                    <n-form-item :label="t('关键词候选数')">
                      <n-input-number v-model:value="knowledgeForm.retrieval.hybrid.keywordTopK" :min="1" :max="500" style="width: 100%" />
                    </n-form-item>
                  </n-grid-item>
                </n-grid>

                <div class="knowledge-section-title">{{ t('重排服务细节') }}</div>
                <n-grid :cols="2" :x-gap="16" :y-gap="10">
                  <n-grid-item :span="2">
                    <n-form-item :label="t('选择重排模型')" :required="knowledgeForm.retrieval.rerank.enabled">
                      <ModelCapabilitySelect
                        v-model="knowledgeForm.retrieval.rerank.modelInstanceId"
                        capability="rerank"
                        :placeholder="t('请选择模型中心中的重排模型')"
                      />
                      <div class="field-help">{{ t('仅显示模型中心中已启用且支持重排能力的模型；关闭重排时可以不选择。') }}</div>
                    </n-form-item>
                  </n-grid-item>
                  <n-grid-item>
                    <n-form-item :label="t('重排超时秒数')">
                      <n-input-number v-model:value="knowledgeForm.retrieval.rerank.timeoutSeconds" :min="1" :max="120" style="width: 100%" />
                    </n-form-item>
                  </n-grid-item>
                  <n-grid-item>
                    <n-form-item :label="t('重排分数阈值')">
                      <n-input-number v-model:value="knowledgeForm.retrieval.rerank.scoreThreshold" :min="0" :max="1" :step="0.01" style="width: 100%" />
                    </n-form-item>
                  </n-grid-item>
                  <n-grid-item>
                    <n-form-item :label="t('重排失败时')">
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
import { computed, onMounted, reactive, ref, watch } from 'vue';
import { useMessage } from 'naive-ui';
import axios from 'axios';
import { useRoute, useRouter } from 'vue-router';
import { t, useLocale } from '@/composables/i18n';
import { useTheme } from '@/composables/theme';
import { getAdminTimezone, getBrowserTimezone, setAdminTimezone } from '@/composables/adminTimezone';
import SearchProviderGuide from '@/components/search-provider/SearchProviderGuide.vue';
import ModelCapabilitySelect from '@/components/models/ModelCapabilitySelect.vue';
import PresentationSettingsPanel from '@/components/settings/PresentationSettingsPanel.vue';
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

const message = useMessage();
type SettingsSection = 'general' | 'presentation' | 'external-search' | 'page-collection' | 'knowledge';

const route = useRoute();
const router = useRouter();
const sectionRouteMap: Record<SettingsSection, string> = {
  general: '/settings',
  presentation: '/settings/presentation',
  'external-search': '/settings/external-search',
  'page-collection': '/settings/page-collection',
  knowledge: '/settings/knowledge',
};
const activeSection = ref<SettingsSection>('general');

function sectionFromPath(path: string): SettingsSection {
  if (path.includes('/settings/presentation')) return 'presentation';
  if (path.includes('/settings/external-search')) return 'external-search';
  if (path.includes('/settings/page-collection')) return 'page-collection';
  if (path.includes('/settings/knowledge')) return 'knowledge';
  return 'general';
}

function switchSection(section: SettingsSection) {
  activeSection.value = section;
  const target = sectionRouteMap[section];
  if (route.path !== target) {
    router.push(target);
  }
}

watch(
  () => route.path,
  (path) => {
    activeSection.value = sectionFromPath(path);
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
  message.success(t('通用配置已保存'));
}

const providers = ref<ExternalSearchProviderItem[]>([]);
const selectedProvider = ref<ExternalSearchProvider>('tavily');
const loading = ref(false);
const saving = ref(false);
const testing = ref(false);
const testQuery = ref('OpenAI latest news');
const testResult = ref<ExternalSearchTestResult | null>(null);
const pageCollectionSettings = ref<PageCollectionSettings | null>(null);
const pageCollectionLoading = ref(false);
const pageCollectionSaving = ref(false);
const knowledgeLoading = ref(false);
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
      maxChunksPerDocument: 5,
      dedupByDocument: true,
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
  { label: t('向量检索'), value: 'vector' },
  { label: t('混合检索'), value: 'hybrid' },
];

const fusionMethodOptions = [
  { label: 'RRF', value: 'rrf' },
  { label: t('加权融合'), value: 'weighted' },
];

const keywordAnalyzerOptions = [
  { label: t('通用'), value: 'standard' },
  { label: t('中文/日文/韩文'), value: 'cjk' },
  { label: 'IK', value: 'ik' },
];

const rerankFallbackOptions = [
  { label: t('失败时仍返回初步检索结果'), value: 'return_vector_results' },
  { label: t('失败时不返回结果'), value: 'return_empty' },
  { label: t('失败时直接报错'), value: 'fail' },
];

function healthTagType(status: string) {
  if (status === 'healthy') return 'success';
  if (status === 'failed') return 'error';
  return 'default';
}

function healthText(status: string) {
  if (status === 'healthy') return t('测试通过');
  if (status === 'failed') return t('测试失败');
  return t('未测试');
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
  } finally {
    knowledgeLoading.value = false;
  }
}

async function saveCurrent() {
  saving.value = true;
  try {
    const saved = await saveExternalSearchProvider(selectedProvider.value, { ...form });
    const index = providers.value.findIndex((item) => item.provider === saved.provider);
    if (index >= 0) providers.value[index] = saved;
    fillForm(saved);
    message.success(t('配置已保存'));
  } finally {
    saving.value = false;
  }
}

async function makeDefault() {
  await saveCurrent();
  await setDefaultExternalSearchProvider(selectedProvider.value);
  message.success(t('默认搜索源已更新'));
  await loadProviders();
}

async function savePageCollection() {
  pageCollectionSaving.value = true;
  try {
    const saved = await savePageCollectionSettings({ ...pageCollectionForm });
    pageCollectionSettings.value = saved;
    pageCollectionForm.enabled = saved.enabled;
    pageCollectionForm.apiKey = '';
    message.success(t('配置已保存'));
  } finally {
    pageCollectionSaving.value = false;
  }
}

async function saveKnowledgeParse() {
  knowledgeSaving.value = true;
  try {
    if (!knowledgeForm.embedding.modelInstanceId) {
      message.error(t('请选择向量模型'));
      return;
    }
    if (knowledgeForm.retrieval.rerank.enabled && !knowledgeForm.retrieval.rerank.modelInstanceId) {
      message.error(t('开启重排后请选择重排模型'));
      return;
    }
    knowledgeForm.embedding.provider = 'model_center';
    knowledgeForm.retrieval.rerank.provider = 'model_center';
    knowledgeForm.retrieval.rerank.model = '';
    knowledgeForm.retrieval.rerank.endpoint = '';
    knowledgeForm.vectorStore.tenantIsolation = true;
    const saved = await saveKnowledgeSettings(JSON.parse(JSON.stringify(knowledgeForm)));
    applyKnowledgeSettings(saved);
    message.success(t('配置已保存'));
  } finally {
    knowledgeSaving.value = false;
  }
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
      message: String(result?.message || (result?.ok ? t('连接成功') : t('测试完成，但未返回可展示结果'))),
    };
    testResult.value = normalizedResult;
    if (normalizedResult.ok) {
      message.success(t('连接测试通过'));
    } else {
      message.error(normalizedResult.message || t('连接测试失败'));
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
    const errorMessage = String(detail || t('连接测试失败'));
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
  loadProviders();
  loadPageCollection();
  loadKnowledgeParseSettings();
});
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
