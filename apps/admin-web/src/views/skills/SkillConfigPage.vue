<template>
  <div class="skill-config-page">
    <Teleport v-if="headerTeleportReady && skill" to="#header-actions-teleport-target">
      <div class="workflow-header-actions" data-header-actions-owner="skill-config">
        <template v-if="skill.type === 'workflow'">
          <n-button
            v-if="workflowSteps.length"
            class="ai-optimize-button"
            size="small"
            :loading="optimizing"
            :disabled="generatingSteps || supplementingStep || !!polishingStepId"
            @click="optimizeSteps"
          >
            <template #icon>
              <span class="button-icon" aria-hidden="true">
                <svg viewBox="0 0 24 24"><path d="M13 2l1.9 5.1L20 9l-5.1 1.9L13 16l-1.9-5.1L6 9l5.1-1.9L13 2z" /><path d="M5 14l.9 2.4L8.5 17l-2.6.6L5 20l-.9-2.4L1.5 17l2.6-.6L5 14z" /></svg>
              </span>
            </template>
            {{ t('AI 优化当前步骤') }}
          </n-button>
          <n-button
            class="regenerate-button"
            size="small"
            :disabled="generatingSteps || optimizing || supplementingStep || !!polishingStepId"
            @click="regenerateSteps"
          >
            <template #icon>
              <span class="button-icon" aria-hidden="true">
                <svg viewBox="0 0 24 24"><path d="M21 12a9 9 0 0 1-15.3 6.4" /><path d="M3 12A9 9 0 0 1 18.3 5.6" /><path d="M18 2v4h-4" /><path d="M6 22v-4h4" /></svg>
              </span>
            </template>
            {{ t('重新生成步骤') }}
          </n-button>
          <n-button
            v-if="workflowAiUndoStack.length"
            class="undo-ai-button"
            size="small"
            secondary
            :disabled="generatingSteps || optimizing || supplementingStep || !!polishingStepId"
            @click="undoLastAiWorkflowChange"
          >
            {{ t('撤回 AI 修改') }}
          </n-button>
          <n-button size="small" type="primary" :loading="saving" @click="saveWorkflow">
            <template #icon>
              <span class="button-icon" aria-hidden="true">
                <svg viewBox="0 0 24 24">
                  <path d="M5 3h11l3 3v15H5z" />
                  <path d="M8 3v6h8V3" />
                  <path d="M8 21v-7h8v7" />
                </svg>
              </span>
            </template>
            {{ t('保存') }}
          </n-button>
        </template>
        <template v-else>
          <n-button
            class="ai-optimize-button"
            size="small"
            :loading="styleEnriching"
            :disabled="saving || !canEnrichWritingStyle"
            @click="enrichWritingStyle"
          >
            <template #icon>
              <span class="button-icon" aria-hidden="true">
                <svg viewBox="0 0 24 24"><path d="M13 2l1.9 5.1L20 9l-5.1 1.9L13 16l-1.9-5.1L6 9l5.1-1.9L13 2z" /><path d="M5 14l.9 2.4L8.5 17l-2.6.6L5 20l-.9-2.4L1.5 17l2.6-.6L5 14z" /></svg>
              </span>
            </template>
            {{ t('智能补全') }}
          </n-button>
          <n-button size="small" type="primary" :loading="saving" @click="saveWritingStyle">
            <template #icon>
              <span class="button-icon" aria-hidden="true">
                <svg viewBox="0 0 24 24">
                  <path d="M5 3h11l3 3v15H5z" />
                  <path d="M8 3v6h8V3" />
                  <path d="M8 21v-7h8v7" />
                </svg>
              </span>
            </template>
            {{ t('保存并发布') }}
          </n-button>
        </template>
      </div>
    </Teleport>

    <n-spin :show="loading">
      <template v-if="skill">
        <template v-if="skill.type === 'workflow'">
          <div class="workflow-grid">
            <main class="logic-panel shell-panel">
              <div class="step-list-shell">
                <n-spin :show="(generatingSteps || optimizing || supplementingStep) && !loading" :description="stepListLoadingText">
                  <div class="step-list">
                    <article
                      v-for="(step, index) in workflowSteps"
                      :key="step.id"
                      class="step-card"
                      :class="{
                        active: activeStepId === step.id,
                        dragging: draggingStepId === step.id,
                        'drag-over': dragOverStepId === step.id && draggingStepId !== step.id,
                        'script-step-card': step.type === 'script_plugin',
                      }"
                      @click="activeStepId = step.id"
                      @dragenter.prevent="onDragOver(step.id)"
                      @dragover.prevent="onDragOver(step.id)"
                      @drop.prevent="onDrop(step.id)"
                    >
                      <div class="node-rail">
                        <div class="step-index">{{ index + 1 }}</div>
                        <div class="drag-handle" aria-hidden="true" draggable="true" @dragstart="onDragStart(step.id, $event)" @dragend="onDragEnd">
                          <span></span><span></span><span></span><span></span><span></span><span></span>
                        </div>
                      </div>
                      <div class="workflow-node-body">
                        <div class="node-head-row">
                          <div class="node-title-fields">
                            <div class="node-type-row">
                              <div class="node-type-pill" :style="{ color: workflowTypeMeta(step.type).color }">
                                <span class="node-type-icon" :style="{ '--icon-url': `url(${workflowTypeMeta(step.type).icon})` }"></span>
                                <n-select
                                  :value="step.type"
                                  @update:value="(val: any) => handleNodeTypeChange(step, val)"
                                  size="small"
                                  :options="workflowNodeTypes.map((item) => ({ label: item.label, value: item.type }))"
                                  class="node-type-select"
                                />
                              </div>
                              <n-select
                                v-if="step.type === 'generate_content'"
                                v-model:value="step.boundWritingSkillId"
                                size="small"
                                clearable
                                filterable
                                :options="writingSkillOptions"
                                class="node-writing-skill-select"
                                :placeholder="t('选择写作 Skill')"
                              />
                              <n-select
                                v-if="step.type === 'extract_resources'"
                                v-model:value="step.businessConfig.resourceTypes"
                                multiple
                                size="small"
                                :options="[
                                  { label: t('图片'), value: 'images' },
                                  { label: t('URL'), value: 'urls' },
                                  { label: t('附件'), value: 'attachments' }
                                ]"
                                class="node-resource-types-select"
                                :placeholder="t('选择资源类型')"
                              />
                              <n-select
                                v-if="step.type === 'call_tool'"
                                :value="selectedToolId(step)"
                                size="small"
                                clearable
                                filterable
                                :loading="toolOptionsLoading"
                                :options="toolOptions"
                                class="node-tool-select"
                                :placeholder="t('优先使用的 Tool / MCP（可选）')"
                                @update:value="(val: any) => handleToolSelect(step, val)"
                              />
                              <n-select
                                v-if="step.type === 'call_tool' && selectedTool(step)?.type === 'mcp'"
                                :value="selectedMcpToolName(step)"
                                size="small"
                                clearable
                                filterable
                                :options="mcpToolOptions(step)"
                                class="node-tool-select"
                                :placeholder="t('优先使用的 MCP 子工具（可选）')"
                                @update:value="(val: any) => handleMcpToolSelect(step, val)"
                              />
                            </div>
                            <div v-if="step.type === 'script_plugin'" class="script-plugin-panel">
                              <div class="script-processing-instruction">
                                <div class="script-processing-head">
                                  <strong>{{ t('处理要求') }}</strong>
                                  <div class="script-generation-tools">
                                    <span class="script-generation-status" :class="{ ready: isScriptPluginGenerated(step) }">
                                      {{ isScriptPluginGenerated(step) ? t('已生成') : t('未生成') }}
                                    </span>
                                    <n-button
                                      size="small"
                                      type="primary"
                                      secondary
                                      :loading="generatingScriptStepId === step.id"
                                      :disabled="!String(step.businessConfig?.processingInstruction || '').trim()"
                                      @click.stop="generateScriptPluginStep(step, { confirmOverwrite: true })"
                                    >
                                      <template #icon>
                                        <span class="button-icon" aria-hidden="true">
                                          <svg viewBox="0 0 24 24"><path d="M12 3l1.7 4.4L18 9l-4.3 1.6L12 15l-1.7-4.4L6 9l4.3-1.6L12 3z" /><path d="M5 14l.9 2.1L8 17l-2.1.9L5 20l-.9-2.1L2 17l2.1-.9L5 14z" /><path d="M19 14l.9 2.1L22 17l-2.1.9L19 20l-.9-2.1L16 17l2.1-.9L19 14z" /></svg>
                                        </span>
                                      </template>
                                      {{ isScriptPluginGenerated(step) ? t('重新生成') : t('生成代码') }}
                                    </n-button>
                                  </div>
                                </div>
                                <n-input
                                  v-model:value="step.businessConfig.processingInstruction"
                                  type="textarea"
                                  :autosize="{ minRows: 3, maxRows: 8 }"
                                  :placeholder="t('用自然语言描述要处理什么、输入是什么、输出什么。')"
                                  @update:value="() => invalidateScriptPluginCheck(step.id)"
                                />
                                <div class="script-instruction-example">
                                  <b>{{ t('示例') }}</b>
                                  <span>{{ t('上传文档：读取用户上传的 Word 或 PDF，删除说明文字和空段落，提取标题、表格和图片，按指定顺序重排，输出新的 Word 文件。') }}</span>
                                  <span>{{ t('工具结果：读取上游工具返回的客户或订单数据，统一字段名和日期格式，去除重复记录，计算每类数量和金额汇总，输出 JSON 或 Excel。') }}</span>
                                  <span>{{ t('网页采集：读取爬取回来的多篇网页正文，去掉导航和广告文本，提取标题、发布时间、正文和链接，按来源分组输出结构化数据。') }}</span>
                                </div>
                              </div>
                              <div class="script-plugin-actions">
                                <n-button
                                  size="small"
                                  secondary
                                  @click.stop="openScriptAdvancedDrawer(step)"
                                >
                                  <template #icon>
                                    <span class="button-icon" aria-hidden="true">
                                      <svg viewBox="0 0 24 24"><path d="M12 15.5A3.5 3.5 0 1 0 12 8a3.5 3.5 0 0 0 0 7.5z" /><path d="M19.4 15a1.8 1.8 0 0 0 .4 2l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.8 1.8 0 0 0-2-.4 1.8 1.8 0 0 0-1 1.6V21a2 2 0 1 1-4 0v-.1a1.8 1.8 0 0 0-1-1.6 1.8 1.8 0 0 0-2 .4l-.1.1A2 2 0 1 1 4.1 17l.1-.1a1.8 1.8 0 0 0 .4-2 1.8 1.8 0 0 0-1.6-1H3a2 2 0 1 1 0-4h.1a1.8 1.8 0 0 0 1.6-1 1.8 1.8 0 0 0-.4-2l-.1-.1A2 2 0 1 1 7 4.1l.1.1a1.8 1.8 0 0 0 2 .4 1.8 1.8 0 0 0 1-1.6V3a2 2 0 1 1 4 0v.1a1.8 1.8 0 0 0 1 1.6 1.8 1.8 0 0 0 2-.4l.1-.1A2 2 0 1 1 19.9 7l-.1.1a1.8 1.8 0 0 0-.4 2 1.8 1.8 0 0 0 1.6 1h.1a2 2 0 1 1 0 4H21a1.8 1.8 0 0 0-1.6 1z" /></svg>
                                    </span>
                                  </template>
                                  {{ t('高级') }}
                                </n-button>
                              </div>
                            </div>
                            <div v-if="step.type !== 'script_plugin'" class="node-description-field">
                              <div class="node-description-head">
                                <div class="node-description-label">{{ t('节点要求') }}</div>
                                <n-button
                                  size="tiny"
                                  secondary
                                  :loading="polishingStepId === step.id"
                                  :disabled="generatingSteps || optimizing || supplementingStep || (!!polishingStepId && polishingStepId !== step.id)"
                                  @click.stop="polishStepRequirement(step)"
                                >
                                  {{ t('AI 润色') }}
                                </n-button>
                              </div>
                              <n-input
                                v-model:value="step.text"
                                type="textarea"
                                :autosize="{ minRows: 2, maxRows: 10 }"
                                class="step-input"
                                :placeholder="workflowTypeMeta(step.type).placeholder"
                                @focus="activeStepId = step.id"
                              />
                            </div>
                          </div>
                        </div>
                        <details
                          v-if="workflowTypeMeta(step.type).usageDescription"
                          class="node-usage-guide"
                          :style="{ '--guide-color': workflowTypeMeta(step.type).color }"
                          @click.stop
                        >
                          <summary>
                            <svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="9" /><path d="M12 11v5" /><path d="M12 8h.01" /></svg>
                            <span>{{ t('查看使用说明与示例') }}</span>
                            <svg class="node-usage-chevron" viewBox="0 0 24 24" aria-hidden="true"><path d="M7 10l5 5 5-5" /></svg>
                          </summary>
                          <div class="node-usage-content">
                            <strong>{{ t('使用场景') }}</strong>
                            <p>{{ workflowTypeMeta(step.type).usageDescription }}</p>
                            <div class="node-usage-example">
                              <span>{{ t('示例') }}</span>
                              <p>{{ workflowTypeMeta(step.type).usageExample }}</p>
                            </div>
                          </div>
                        </details>
                      </div>
                      <div class="step-tools">
                        <button class="icon-button" type="button" :title="t('上移')" :disabled="index === 0" @click.stop="moveStep(index, -1)">
                          <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 19V5" /><path d="M5 12l7-7 7 7" /></svg>
                        </button>
                        <button class="icon-button" type="button" :title="t('下移')" :disabled="index === workflowSteps.length - 1" @click.stop="moveStep(index, 1)">
                          <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 5v14" /><path d="M19 12l-7 7-7-7" /></svg>
                        </button>
                        <button class="icon-button danger" type="button" :title="t('删除步骤')" @click.stop="removeStep(step.id)">
                          <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3 6h18" /><path d="M8 6V4h8v2" /><path d="M6 6l1 16h10l1-16" /><path d="M10 11v6" /><path d="M14 11v6" /></svg>
                        </button>
                      </div>
                    </article>

                    <n-empty
                      v-if="!workflowSteps.length && !generatingSteps"
                      class="step-empty"
                      :description="stepGenerationError || t('还没有业务逻辑步骤')"
                    >
                      <template #extra>
                        <n-button type="primary" secondary @click="regenerateSteps">{{ t('重新生成步骤') }}</n-button>
                      </template>
                    </n-empty>
                  </div>
                </n-spin>
              </div>

              <section class="add-step-box">
                <div class="add-title-row">
                  <div class="add-title">{{ t('添加业务流程步骤') }}</div>
                  <n-button
                    class="ai-supplement-button"
                    size="small"
                    :loading="supplementingStep"
                    :disabled="!newStepText.trim() || generatingSteps || optimizing || !!polishingStepId"
                    @click="supplementStepWithAi"
                  >
                    <template #icon>
                      <span class="button-icon" aria-hidden="true">
                        <svg viewBox="0 0 24 24"><path d="M13 2l1.9 5.1L20 9l-5.1 1.9L13 16l-1.9-5.1L6 9l5.1-1.9L13 2z" /><path d="M5 14l.9 2.4L8.5 17l-2.6.6L5 20l-.9-2.4L1.5 17l2.6-.6L5 14z" /></svg>
                      </span>
                    </template>
                    {{ t('AI 优化添加') }}
                  </n-button>
                </div>
                <n-input
                  v-model:value="newStepText"
                  type="textarea"
                  :autosize="{ minRows: 1, maxRows: 10 }"
                  maxlength="200"
                  show-count
                  :placeholder="t('例如：如果查不到部分数据，需要提示用户并继续分析已有数据')"
                />
                <div class="quick-node-row">
                  <n-popover
                    v-for="item in workflowNodeTypes"
                    :key="item.type"
                    trigger="hover"
                    placement="top-start"
                    :width="340"
                    :disabled="!item.usageDescription"
                  >
                    <template #trigger>
                      <button
                        class="quick-node-button"
                        type="button"
                        :style="{ color: item.color, background: item.bg, borderColor: item.bg }"
                        @click="appendNodeByType(item.type)"
                      >
                        <span class="quick-node-icon" :style="{ '--icon-url': `url(${item.icon})`, color: item.color }"></span>
                        <span>{{ item.label }}</span>
                      </button>
                    </template>
                    <div class="quick-node-help">
                      <strong>{{ item.label }} · {{ t('使用场景') }}</strong>
                      <p>{{ item.usageDescription }}</p>
                      <div><span>{{ t('示例') }}</span>{{ item.usageExample }}</div>
                    </div>
                  </n-popover>
                </div>
              </section>
            </main>

            <aside class="test-panel shell-panel">
              <div class="test-head">
                <div class="test-icon" aria-hidden="true">
                  <svg viewBox="0 0 24 24"><path d="M10 2h4" /><path d="M11 2v6L5 19a2 2 0 0 0 1.8 3h10.4A2 2 0 0 0 19 19L13 8V2" /><path d="M7.5 15h9" /></svg>
                </div>
                <div>
                  <div class="panel-title">{{ t('执行顺序预览') }}</div>
                  <div class="panel-desc">{{ t('查看当前 Skill 的节点执行顺序') }}</div>
                </div>
              </div>

              <div class="divider"></div>

              <section class="execution-preview-block">
                <div class="result-title">{{ t('执行预览') }}</div>
                <div v-if="workflowPreviewNodes.length" class="flow-preview">
                  <template v-for="(node, index) in workflowPreviewNodes" :key="node.id">
                    <div class="flow-node" :style="{ color: node.color }">
                      <span class="flow-node-icon" :style="{ '--icon-url': `url(${node.icon})` }"></span>
                      <span>{{ node.label }}</span>
                    </div>
                    <div v-if="index < workflowPreviewNodes.length - 1" class="flow-arrow">↓</div>
                  </template>
                </div>
                <div v-else class="flow-empty">{{ t('添加节点后展示执行顺序') }}</div>
              </section>

            </aside>
          </div>
        </template>

        <template v-else>
          <div class="style-grid">
            <main class="shell-panel style-panel">
              <section class="style-section">
                <div class="config-title">{{ t('定位') }}</div>
                <div class="config-note">{{ t('定义这类内容更适合投放到哪里，以及它面向什么读者。') }}</div>
                <div class="style-grid-fields style-grid-fields-2">
                  <div class="style-field">
                    <label class="field-label">{{ t('发布渠道') }}</label>
                    <n-select
                      v-model:value="publishChannelInput"
                      multiple
                      filterable
                      tag
                      :options="publishChannelOptions"
                      :placeholder="t('添加渠道，例如 website / docs / wechat_official')"
                    />
                  </div>
                  <div class="style-field">
                    <label class="field-label">{{ t('内容形式') }}</label>
                    <n-select
                      v-model:value="contentFormInput"
                      multiple
                      filterable
                      tag
                      :options="contentFormOptions"
                      :placeholder="t('添加内容形式，例如 report / article / memo')"
                    />
                  </div>
                  <div class="style-field">
                    <label class="field-label">{{ t('目标受众') }}</label>
                    <n-select
                      v-model:value="targetAudienceInput"
                      multiple
                      filterable
                      tag
                      :options="targetAudienceOptions"
                      :placeholder="t('添加目标受众')"
                    />
                  </div>
                  <div class="style-field">
                    <label class="field-label">{{ t('偏好风格') }}</label>
                    <n-select
                      v-model:value="preferredStyleInput"
                      multiple
                      filterable
                      tag
                      :options="preferredStyleOptions"
                      :placeholder="t('添加偏好风格')"
                    />
                  </div>
                  <div class="style-field">
                    <label class="field-label">{{ t('目标字数下限') }}</label>
                    <n-input-number
                      v-model:value="targetLengthMin"
                      :min="0"
                      :step="100"
                      clearable
                      :placeholder="t('例如 3500')"
                    />
                  </div>
                  <div class="style-field">
                    <label class="field-label">{{ t('目标字数上限') }}</label>
                    <n-input-number
                      v-model:value="targetLengthMax"
                      :min="0"
                      :step="100"
                      clearable
                      :placeholder="t('例如 4500')"
                    />
                  </div>
                </div>
              </section>

              <section class="style-section">
                <div class="config-title">{{ t('结构与边界') }}</div>
                <div class="config-note">{{ t('章节结构控制最终标题层级；每个章节内的包含/避免项会作为该章节的写作约束。') }}</div>
                <div class="section-builder">
                  <div class="section-builder-head">
                    <label class="field-label">{{ t('章节结构') }}</label>
                    <n-button size="small" secondary @click="addSection()">{{ t('添加一级章节') }}</n-button>
                  </div>
                  <div v-if="sectionStructure.length" class="section-node-list">
                    <article v-for="(node, index) in sectionStructure" :key="node.id" class="section-node-card">
                      <div class="section-node-main">
                        <div class="section-node-index">{{ index + 1 }}</div>
                        <div class="section-node-content">
                          <n-input v-model:value="node.title" :placeholder="t('章节标题，例如：一、主题报道总体情况')" />
                          <div class="section-node-fields">
                            <n-input
                              v-model:value="node.mustIncludeText"
                              type="textarea"
                              :autosize="{ minRows: 1, maxRows: 10 }"
                              :placeholder="t('本章必须包含，每行一条')"
                            />
                            <n-input
                              v-model:value="node.avoidText"
                              type="textarea"
                              :autosize="{ minRows: 1, maxRows: 10 }"
                              :placeholder="t('本章必须避免，每行一条')"
                            />
                          </div>
                          <n-input
                            v-model:value="node.notes"
                            type="textarea"
                            :autosize="{ minRows: 1, maxRows: 10 }"
                            :placeholder="t('本章补充说明，可选')"
                          />
                        </div>
                        <div class="section-node-actions">
                          <n-button size="tiny" quaternary :disabled="index === 0" @click="moveSection(sectionStructure, index, -1)">{{ t('上移') }}</n-button>
                          <n-button size="tiny" quaternary :disabled="index === sectionStructure.length - 1" @click="moveSection(sectionStructure, index, 1)">{{ t('下移') }}</n-button>
                          <n-button size="tiny" secondary @click="addSection(node)">{{ t('加子节') }}</n-button>
                          <n-button size="tiny" quaternary type="error" @click="removeSection(sectionStructure, index)">{{ t('删除') }}</n-button>
                        </div>
                      </div>
                      <div class="section-child-list">
                        <article v-for="(child, childIndex) in node.children" :key="child.id" class="section-node-card section-node-card-child">
                          <div class="section-node-main">
                            <div class="section-node-index">{{ index + 1 }}.{{ childIndex + 1 }}</div>
                            <div class="section-node-content">
                              <n-input v-model:value="child.title" :placeholder="t('二级标题，例如：（一）多语种记者现场采访')" />
                              <div class="section-node-fields">
                                <n-input
                                  v-model:value="child.mustIncludeText"
                                  type="textarea"
                                  :autosize="{ minRows: 1, maxRows: 10 }"
                                  :placeholder="t('本节必须包含，每行一条')"
                                />
                                <n-input
                                  v-model:value="child.avoidText"
                                  type="textarea"
                                  :autosize="{ minRows: 2, maxRows: 4 }"
                                  :placeholder="t('本节必须避免，每行一条')"
                                />
                              </div>
                              <n-input
                                v-model:value="child.notes"
                                type="textarea"
                                :autosize="{ minRows: 1, maxRows: 3 }"
                                :placeholder="t('本节补充说明，可选')"
                              />
                            </div>
                            <div class="section-node-actions">
                              <n-button size="tiny" quaternary :disabled="childIndex === 0" @click="moveSection(node.children, childIndex, -1)">{{ t('上移') }}</n-button>
                              <n-button size="tiny" quaternary :disabled="childIndex === node.children.length - 1" @click="moveSection(node.children, childIndex, 1)">{{ t('下移') }}</n-button>
                              <n-button size="tiny" quaternary type="error" @click="removeSection(node.children, childIndex)">{{ t('删除') }}</n-button>
                            </div>
                          </div>
                        </article>
                      </div>
                    </article>
                  </div>
                  <n-empty v-else class="section-empty" :description="t('还没有章节结构')">
                    <template #extra>
                      <n-button type="primary" secondary @click="addSection()">{{ t('添加章节') }}</n-button>
                    </template>
                  </n-empty>
                </div>
                <div class="style-grid-fields style-grid-fields-2">
                  <div class="style-field">
                    <label class="field-label">{{ t('必须包含') }}</label>
                    <n-input
                      v-model:value="requiredElementsText"
                      type="textarea"
                      :autosize="{ minRows: 1, maxRows: 10 }"
                      :placeholder="t('每行一条，例如：标题')"
                    />
                  </div>
                  <div class="style-field">
                    <label class="field-label">{{ t('必须避免') }}</label>
                    <n-input
                      v-model:value="forbiddenElementsText"
                      type="textarea"
                      :autosize="{ minRows: 1, maxRows: 10 }"
                      :placeholder="t('每行一条，例如：编造数据')"
                    />
                  </div>
                </div>
              </section>

            </main>

            <aside class="shell-panel style-preview-panel">
              <div class="panel-head">
                <div>
                  <div class="panel-title">{{ t('当前生效摘要') }}</div>
                  <div class="panel-desc">{{ t('这里展示将注入 runtime 的核心写作约束。') }}</div>
                </div>
              </div>

              <div class="style-preview-group">
                <div class="preview-label">{{ t('内容形式') }}</div>
                <div class="preview-value">{{ formatLocalizedValues(contentFormInput, ' / ') }}</div>
              </div>
              <div class="style-preview-group">
                <div class="preview-label">{{ t('目标受众') }}</div>
                <div class="preview-value">{{ formatLocalizedValues(targetAudienceInput) }}</div>
              </div>
              <div class="style-preview-group">
                <div class="preview-label">{{ t('偏好风格') }}</div>
                <div class="preview-value">{{ formatLocalizedValues(preferredStyleInput) }}</div>
              </div>
              <div class="style-preview-group">
                <div class="preview-label">{{ t('目标字数') }}</div>
                <div class="preview-value">{{ targetLengthLabel }}</div>
              </div>
              <div class="style-preview-group">
                <div class="preview-label">{{ t('章节结构') }}</div>
                <div v-if="sectionStructurePreview.length" class="preview-section-tree">
                  <div v-for="item in sectionStructurePreview" :key="item.key" class="preview-section-row" :class="{ child: item.level > 1 }">
                    <span class="preview-section-title">{{ item.title }}</span>
                    <span v-if="item.mustInclude.length" class="preview-section-meta">{{ t('含 {count} 项', { count: item.mustInclude.length }) }}</span>
                  </div>
                </div>
                <span v-else class="preview-empty">{{ t('未配置') }}</span>
              </div>
              <div class="style-preview-group">
                <div class="preview-label">{{ t('必须包含') }}</div>
                <div class="preview-list">
                  <span v-for="item in requiredElementsItems" :key="item" class="preview-chip">{{ item }}</span>
                  <span v-if="!requiredElementsItems.length" class="preview-empty">{{ t('未配置') }}</span>
                </div>
              </div>
              <div class="style-preview-group">
                <div class="preview-label">{{ t('禁止项') }}</div>
                <div class="preview-list preview-list-danger">
                  <span v-for="item in forbiddenElementsItems" :key="item" class="preview-chip preview-chip-danger">{{ item }}</span>
                  <span v-if="!forbiddenElementsItems.length" class="preview-empty">{{ t('未配置') }}</span>
                </div>
              </div>
            </aside>
          </div>
        </template>
      </template>

      <n-empty v-else :description="t('Skill 不存在或已删除')" />
    </n-spin>
    <n-drawer v-model:show="scriptAdvancedDrawerVisible" :width="820" placement="right">
      <n-drawer-content
        v-if="activeScriptStep"
        :title="t('数据处理高级设置')"
        closable
        :body-content-style="{ height: '100%', overflow: 'hidden' }"
      >
        <div class="script-drawer-body">
          <div class="script-drawer-settings">
            <div class="script-drawer-instruction">
              <div class="script-drawer-instruction-head">
                <strong>{{ t('处理要求') }}</strong>
                <n-button
                  size="small"
                  type="primary"
                  :loading="generatingScriptStepId === activeScriptStep.id"
                  :disabled="!String(activeScriptStep.businessConfig?.processingInstruction || '').trim()"
                  @click.stop="generateScriptPluginStep(activeScriptStep, { confirmOverwrite: true })"
                >
                  <template #icon>
                    <span class="button-icon" aria-hidden="true">
                      <svg viewBox="0 0 24 24"><path d="M12 3l1.7 4.4L18 9l-4.3 1.6L12 15l-1.7-4.4L6 9l4.3-1.6L12 3z" /><path d="M5 14l.9 2.1L8 17l-2.1.9L5 20l-.9-2.1L2 17l2.1-.9L5 14z" /><path d="M19 14l.9 2.1L22 17l-2.1.9L19 20l-.9-2.1L16 17l2.1-.9L19 14z" /></svg>
                    </span>
                  </template>
                  {{ String(activeScriptStep.businessConfig?.pluginCode || '').trim() ? t('重新生成代码') : t('生成处理代码') }}
                </n-button>
              </div>
              <n-input
                v-model:value="activeScriptStep.businessConfig.processingInstruction"
                type="textarea"
                :autosize="{ minRows: 3, maxRows: 5 }"
                :placeholder="t('用自然语言描述要处理什么、输入是什么、输出什么。')"
                @update:value="() => invalidateScriptPluginCheck(activeScriptStepId)"
              />
            </div>
            <details class="script-drawer-details">
              <summary>{{ t('节点规范') }}</summary>
              <div class="script-plugin-rules">
                <strong>{{ t('数据处理节点规范') }}</strong>
                <div class="script-contract-grid">
                  <div>
                    <b>{{ t('入口') }}</b>
                    <code>def run(inputs, context):</code>
                  </div>
                  <div>
                    <b>{{ t('标准输入') }}</b>
                    <code>selected = inputs["selected"]<br>files = selected["files"]<br>images = selected["images"]<br>texts = selected["texts"]</code>
                  </div>
                  <div>
                    <b>{{ t('输出文件') }}</b>
                    <code>out_dir = context["output_dir"]<br>out_path = os.path.join(out_dir, "result.docx")</code>
                  </div>
                  <div>
                    <b>{{ t('返回结果') }}</b>
                    <code>return {"files": [{"path": "result.docx", "type": "docx"}], "data": {}, "logs": []}</code>
                  </div>
                </div>
                <span>{{ t('限制：禁止联网、子进程、eval/exec、固定本机路径；输出只支持 docx/pdf/xlsx/pptx/txt/md/json/csv。') }}</span>
              </div>
            </details>
          </div>
          <div v-if="!String(activeScriptStep.businessConfig?.pluginCode || '').trim()" class="script-code-empty">
            {{ t('代码尚未填写。可以手写代码，或点击生成处理代码。保存前需要通过检测。') }}
          </div>
          <div class="code-editor-shell script-drawer-code">
            <div class="code-editor-head">
              <span>Python</span>
              <span>{{ t('按 Tab 插入缩进，必须定义 run(inputs, context)') }}</span>
            </div>
            <PythonCodeEditor
              v-model="activeScriptStep.businessConfig.pluginCode"
              :placeholder="t('Python 脚本需定义 run(inputs, context)，返回 { files, data, logs }')"
              @update:model-value="() => invalidateScriptPluginCheck(activeScriptStepId)"
            />
          </div>
          <div class="script-plugin-actions">
            <n-button
              size="small"
              type="primary"
              secondary
              :loading="checkingScriptStepId === activeScriptStep.id"
              :disabled="!String(activeScriptStep.businessConfig?.pluginCode || '').trim()"
              @click.stop="checkScriptPluginStep(activeScriptStep)"
            >
              {{ t('检测代码') }}
            </n-button>
            <n-button
              v-if="scriptCheckResults[activeScriptStep.id] && !scriptCheckResults[activeScriptStep.id]?.pass"
              size="small"
              secondary
              :loading="fixingScriptStepId === activeScriptStep.id"
              :disabled="!String(activeScriptStep.businessConfig?.pluginCode || '').trim()"
              @click.stop="fixScriptPluginStep(activeScriptStep)"
            >
              {{ t('AI 修复代码') }}
            </n-button>
          </div>
          <div v-if="scriptCheckResults[activeScriptStep.id]" class="script-check-result">
            <div class="script-check-summary" :class="{ pass: scriptCheckResults[activeScriptStep.id]?.pass, fail: !scriptCheckResults[activeScriptStep.id]?.pass }">
              <strong>{{ scriptCheckResults[activeScriptStep.id]?.pass ? t('检测通过') : t('检测未通过') }}</strong>
              <span>
                {{
                  scriptCheckResults[activeScriptStep.id]?.pass
                    ? (scriptCheckResults[activeScriptStep.id]?.llm?.summary || scriptCheckResults[activeScriptStep.id]?.message || t('代码已通过规则检测。'))
                    : (scriptCheckResults[activeScriptStep.id]?.llm?.summary || scriptCheckResults[activeScriptStep.id]?.message || t('代码未通过检测，请查看下方问题或点击 AI 修复代码。'))
                }}
              </span>
            </div>
            <div
              v-for="item in scriptCheckIssueItems(activeScriptStep).slice(0, 8)"
              :key="`${item.code}-${item.line || 0}-${item.message}`"
              class="script-check-issue"
              :class="item.level"
            >
              <span>{{ item.level === 'error' ? t('错误') : t('警告') }}</span>
              <p>{{ item.line ? `L${item.line}: ` : '' }}{{ item.message }}</p>
            </div>
          </div>
        </div>
        <template #footer>
          <div class="script-drawer-footer">
            <n-button @click="scriptAdvancedDrawerVisible = false">{{ t('取消') }}</n-button>
            <n-button type="primary" :loading="scriptDrawerSaving" @click="saveScriptAdvancedDrawer">{{ t('保存') }}</n-button>
          </div>
        </template>
      </n-drawer-content>
    </n-drawer>
  </div>
</template>

<script setup lang="ts">
import { computed, defineAsyncComponent, nextTick, onMounted, onUnmounted, ref, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { useMessage } from 'naive-ui';
import { t, useLocale } from '@/composables/i18n';
import { formatAdminDateTime } from '@/composables/adminTimezone';
import {
  checkScriptPlugin,
  checkWorkflowNodes,
  enrichWritingStyleDraft,
  fetchSkill,
  fetchSkills,
  fixScriptPlugin,
  generateScriptPlugin,
  generateWorkflowNodes,
  polishWorkflowNode,
  updateSkill,
  type SkillItem,
  type SkillType,
  type ScriptPluginCheckIssue,
  type ScriptPluginCheckResult,
  type WorkflowNodeDraft,
  type WorkflowNodeType,
  type WritingStyleDraft,
} from '@/api/skills';
import { fetchTools, type ExternalToolItem } from '@/api/tools';
import readMaterialIcon from '@/assets/workflow-node-icons/read-material.svg';
import extractInfoIcon from '@/assets/workflow-node-icons/extract-info.svg';
import extractResourcesIcon from '@/assets/workflow-node-icons/extract-resources.svg';
import understandImageIcon from '@/assets/workflow-node-icons/understand-image.svg';
import computeMetricIcon from '@/assets/workflow-node-icons/compute-metric.svg';
import dataCollectIcon from '@/assets/workflow-node-icons/data-collect.svg';
import internalSearchIcon from '@/assets/workflow-node-icons/internal-search.svg';
import externalSearchIcon from '@/assets/workflow-node-icons/external-search.svg';
import callToolIcon from '@/assets/workflow-node-icons/call-tool.svg';
import dataProcessingIcon from '@/assets/workflow-node-icons/data-processing.svg';
import generateContentIcon from '@/assets/workflow-node-icons/generate-content.svg';
import translateRewriteIcon from '@/assets/workflow-node-icons/translate-rewrite.svg';
import fillTableIcon from '@/assets/workflow-node-icons/fill-table.svg';
import exportDeliveryIcon from '@/assets/workflow-node-icons/export-delivery.svg';

const PythonCodeEditor = defineAsyncComponent(() => import('@/components/PythonCodeEditor.vue'));

interface WorkflowStep {
  id: string;
  type: WorkflowNodeType;
  title: string;
  text: string;
  businessConfig: Record<string, any>;
  boundWritingSkillId?: string;
  outputAlias?: string;
}

interface SectionNode {
  id: string;
  title: string;
  mustIncludeText: string;
  avoidText: string;
  notes: string;
  children: SectionNode[];
}

interface SectionPreviewItem {
  key: string;
  title: string;
  level: number;
  mustInclude: string[];
}

interface CoverageItem {
  key: string;
  label: string;
  covered: boolean;
}

interface ReadinessItem {
  key: string;
  label: string;
  ready: boolean;
}

interface WorkflowTestResult {
  testedAt: string;
  pass: boolean;
  logic: {
    label: string;
    level: 'success' | 'warning';
    summary: string;
  };
  coverage: CoverageItem[];
  readiness: ReadinessItem[];
  suggestions: string[];
  conclusion: string;
}

const route = useRoute();
const router = useRouter();
const message = useMessage();
const { locale } = useLocale();

const loading = ref(false);
const headerTeleportReady = ref(false);
const detailRequestSequence = ref(0);
const saving = ref(false);
const testing = ref(false);
const optimizing = ref(false);
const generatingSteps = ref(false);
const supplementingStep = ref(false);
const polishingStepId = ref('');
const styleEnriching = ref(false);
const skill = ref<SkillItem | null>(null);
const workflowSteps = ref<WorkflowStep[]>([]);
const workflowAiUndoStack = ref<Array<{ label: string; steps: WorkflowStep[]; activeStepId: string }>>([]);
const activeStepId = ref('');
const draggingStepId = ref('');
const dragOverStepId = ref('');
const newStepText = ref('');
const testResult = ref<WorkflowTestResult | null>(null);
const stepGenerationError = ref('');
const restoringWorkflow = ref(false);
const checkingScriptStepId = ref('');
const fixingScriptStepId = ref('');
const generatingScriptStepId = ref('');
const scriptAdvancedDrawerVisible = ref(false);
const activeScriptStepId = ref('');
const scriptDrawerSaving = ref(false);
const scriptCheckResults = ref<Record<string, ScriptPluginCheckResult & { signature?: string }>>({});
const publishChannelInput = ref<string[]>([]);
const contentFormInput = ref<string[]>([]);
const targetAudienceInput = ref<string[]>([]);
const preferredStyleInput = ref<string[]>([]);
const targetLengthMin = ref<number | null>(null);
const targetLengthMax = ref<number | null>(null);
const targetLengthUnit = ref('chinese_chars');
const sectionStructure = ref<SectionNode[]>([]);
const requiredElementsText = ref('');
const forbiddenElementsText = ref('');
const styleInputProfile = ref<Record<string, any>>({});
const styleContractJson = ref<Record<string, any>>({});
const styleSkillMarkdown = ref('');
const writingSkillOptions = ref<Array<{ label: string; value: string }>>([]);
const toolRows = ref<ExternalToolItem[]>([]);
const toolOptionsLoading = ref(false);
const activeScriptStep = computed(() => workflowSteps.value.find((item) => item.id === activeScriptStepId.value && item.type === 'script_plugin') || null);
const toolOptions = computed(() => toolRows.value.map((item) => ({
  label: `${item.name} (${item.type.toUpperCase()})${item.status === 'disabled' ? ` - ${t('已停用')}` : ''}`,
  value: item.id,
  disabled: item.status === 'disabled',
})));

const workflowNodeTypes = computed<Array<{
  type: WorkflowNodeType;
  label: string;
  shortLabel: string;
  color: string;
  bg: string;
  icon: string;
  defaultTitle: string;
  placeholder: string;
  defaultConfig: Record<string, any>;
  usageDescription?: string;
  usageExample?: string;
}>>(() => [
  {
    type: 'read_material',
    label: t('读取材料'),
    shortLabel: t('材料'),
    color: '#2f6bff',
    bg: '#eef4ff',
    icon: readMaterialIcon,
    defaultTitle: '读取上传材料',
    placeholder: t('例如：读取用户上传的传播数据文档和原始材料。'),
    defaultConfig: { source: '上传材料', outputAlias: '原始材料' },
    usageDescription: t('用于读取当前任务中用户上传的文档、表格等材料，将可解析的正文、表格和文件信息交给后续节点。它只负责读取材料，不负责抽取字段、统计计算或生成内容。'),
    usageExample: t('读取用户上传的《华东区域项目进展报告.docx》和《项目执行数据.xlsx》，获取报告正文，以及 Excel 中“项目清单”和“月度进度”两个工作表的全部内容。'),
  },
  {
    type: 'extract_resources',
    label: t('提取资源'),
    shortLabel: t('资源'),
    color: '#0891b2',
    bg: '#ecfeff',
    icon: extractResourcesIcon,
    defaultTitle: '提取可处理资源',
    placeholder: t('例如：从上传文档中提取图片、URL 和附件，供后续理解或采集使用。'),
    defaultConfig: { resourceTypes: ['images', 'urls', 'attachments'], outputAlias: '资源列表' },
    usageDescription: t('用于从上游材料中分离图片、网页链接和附件，形成可供后续节点逐项处理的资源列表。它只定位并提取资源，不识别图片内容，也不采集网页正文。'),
    usageExample: t('从《品牌传播复盘.docx》中提取所有内嵌截图、以 http 或 https 开头的网页链接及附件对象，分别输出为图片、链接和附件列表。'),
  },
  {
    type: 'understand_image',
    label: t('图片理解'),
    shortLabel: t('识图'),
    color: '#4f46e5',
    bg: '#eef2ff',
    icon: understandImageIcon,
    defaultTitle: '理解图片内容',
    placeholder: t('例如：对上一步提取出的图片进行多模态识别，提取图中对象、文字、图表和关键信息。'),
    defaultConfig: { input: '上游图片资源', outputAlias: '图片理解结果' },
    usageDescription: t('用于识别上游图片中的文字、对象、界面、图表和关键视觉信息，并输出可继续处理的文字描述或结构化结果。它不负责从文档中提取图片。'),
    usageExample: t('识别上游的 8 张社交平台截图，逐张提取账号名称、发布时间、阅读量和互动量；无法看清的字段标记为“无法识别”。'),
  },
  {
    type: 'extract_info',
    label: t('抽取信息'),
    shortLabel: t('抽取'),
    color: '#2563eb',
    bg: '#edf5ff',
    icon: extractInfoIcon,
    defaultTitle: '抽取关键信息',
    placeholder: t('例如：从上传文档中抽取总阅读量、播放量、互动量。'),
    defaultConfig: { target: '关键字段 / 事实 / 指标', method: '自动识别', outputAlias: '抽取结果' },
    usageDescription: t('用于从上游文本、表格或识图结果中提取指定字段、事实和指标，并整理为结构化结果。它适合明确“要哪些信息”的场景，不负责汇总计算。'),
    usageExample: t('从项目报告中提取项目名称、负责人、起止日期、合同金额、当前进度和主要风险；缺失字段保留为空，不自行推测。'),
  },
  {
    type: 'compute_metric',
    label: t('统计计算'),
    shortLabel: t('统计'),
    color: '#16a36f',
    bg: '#effaf4',
    icon: computeMetricIcon,
    defaultTitle: '计算核心指标',
    placeholder: t('例如：汇总各渠道数据，计算占比、排序并识别异常波动。'),
    defaultConfig: { method: '求和 / 占比 / 排序 / 异常识别', outputAlias: '指标分析' },
    usageDescription: t('用于对上游结构化数据执行求和、平均、占比、同比环比、排序和异常识别等确定口径的统计计算。计算规则和分组维度应在节点要求中写清楚。'),
    usageExample: t('按区域汇总 2026 年第一季度合同金额和回款金额，计算回款率，按回款率从高到低排序，并标记回款率低于 60% 的区域。'),
  },
  {
    type: 'data_collect',
    label: t('数据采集'),
    shortLabel: t('采集'),
    color: '#0d9488',
    bg: '#ecfdf5',
    icon: dataCollectIcon,
    defaultTitle: '采集网页数据',
    placeholder: t('例如：从上一步抽取出的网页链接采集正文内容，作为后续分析和生成依据。'),
    defaultConfig: { source: '网页链接 / 上游 URL', outputAlias: '采集内容' },
    usageDescription: t('用于访问上游提供的网页链接并采集页面标题、正文、发布时间、来源等内容。它面向已知链接的页面采集，不负责通过关键词搜索互联网。'),
    usageExample: t('采集上游链接列表中的新闻页面，保存标题、发布时间、来源、正文和原始 URL；过滤导航、页脚和广告文字，失败链接记录失败原因。'),
  },
  {
    type: 'internal_search',
    label: t('内部搜索'),
    shortLabel: t('内搜'),
    color: '#a16207',
    bg: '#fff8e8',
    icon: internalSearchIcon,
    defaultTitle: '查询内部口径',
    placeholder: t('例如：查找公司过往复盘口径和内部评价标准。'),
    defaultConfig: { source: '知识库 / 制度库 / 历史材料', outputAlias: '内部依据' },
    usageDescription: t('用于在已配置的企业知识库、制度库或历史材料中检索内部依据，并返回相关内容和来源。适合查制度、口径、案例和内部知识，不访问公开互联网。'),
    usageExample: t('在“项目管理制度库”中检索项目延期认定标准、风险分级规则和周报提交要求，返回对应条款、制度名称及原文位置。'),
  },
  {
    type: 'external_search',
    label: t('外部搜索'),
    shortLabel: t('外搜'),
    color: '#d97706',
    bg: '#fff7ed',
    icon: externalSearchIcon,
    defaultTitle: '搜索外部资料',
    placeholder: t('例如：检索公开行业数据和新闻背景，补充外部依据。'),
    defaultConfig: { source: '公开网页 / 新闻 / 行业资料', outputAlias: '外部资料' },
    usageDescription: t('用于按关键词搜索公开网页、新闻和行业资料，获得外部信息线索及来源链接。适合开放式资料发现；如需读取某个已知网页的完整正文，应使用数据采集。'),
    usageExample: t('搜索 2026 年上半年中国新能源汽车出口量相关的官方统计和行业报告，优先采用政府部门及行业协会来源，返回数据摘要、发布日期和链接。'),
  },
  {
    type: 'call_tool',
    label: t('调用工具'),
    shortLabel: t('工具'),
    color: '#0f83a5',
    bg: '#eefbff',
    icon: callToolIcon,
    defaultTitle: '调用业务工具',
    placeholder: t('例如：调用 MCP 或企业工具查询本月渠道投放数据。'),
    defaultConfig: { preferredToolId: '', preferredToolName: '', preferredMcpToolName: '', outputAlias: '工具数据' },
    usageDescription: t('用于调用已接入平台的 Tool 或 MCP，向业务系统查询数据或执行其开放的操作。节点要求应明确工具、输入参数和期望返回内容。'),
    usageExample: t('调用“订单查询”工具，查询 2026-06-01 至 2026-06-30 华东区域状态为“已完成”的订单，返回订单号、客户名称、成交金额和完成时间。'),
  },
  {
    type: 'script_plugin',
    label: t('数据处理'),
    shortLabel: t('处理'),
    color: '#475569',
    bg: '#f1f5f9',
    icon: dataProcessingIcon,
    defaultTitle: '处理数据',
    placeholder: t('例如：规整上传 DOCX、整理图片链接，并输出新的交付文件。'),
    defaultConfig: {
      runtime: 'python',
      outputAlias: '处理结果',
      processingInstruction: '',
      selectedInputSource: 'all',
      selectedInputTypes: ['files', 'documents', 'images', 'urls', 'texts', 'data'],
      pluginCode: '',
    },
    usageDescription: t('用于按照自然语言要求生成并执行确定性的处理代码，对上游文件、文本、链接或结构化数据进行清洗、转换、合并、重排和文件生成。适合规则明确且需要可重复执行的处理。'),
    usageExample: t('读取上游《项目执行数据.xlsx》，统一日期为 YYYY-MM-DD，删除订单号重复的记录，按区域汇总合同金额和回款金额，输出《区域项目汇总.xlsx》。'),
  },
  {
    type: 'generate_content',
    label: t('生成内容'),
    shortLabel: t('生成'),
    color: '#7c3aed',
    bg: '#f4f0ff',
    icon: generateContentIcon,
    defaultTitle: '生成业务内容',
    placeholder: t('例如：基于指标分析和原始材料生成正式复盘稿。'),
    defaultConfig: { input: '上游结果', outputAlias: '生成稿' },
    usageDescription: t('用于根据上游材料和分析结果撰写报告、文章、摘要、方案等内容，可结合选定的写作规范 Skill 控制结构和表达。它负责内容生成，不负责最终文件格式导出。'),
    usageExample: t('根据项目报告和季度指标，生成一份 1500 字以内的《华东区域一季度项目复盘》，包含总体情况、关键成果、主要问题和下一步计划四个部分。'),
  },
  {
    type: 'translate_rewrite',
    label: t('文档翻译'),
    shortLabel: t('翻译'),
    color: '#9333ea',
    bg: '#faf0ff',
    icon: translateRewriteIcon,
    defaultTitle: '翻译文档',
    placeholder: t('例如：将报告翻译成目标语言，并保持术语和表达一致。'),
    defaultConfig: { mode: '翻译 / 润色 / 扩写 / 压缩', outputAlias: '改写稿' },
    usageDescription: t('用于翻译或改写上游文档内容，在保留原意的前提下统一术语、语气和表达。应明确目标语言、保留项及专有名词处理规则。'),
    usageExample: t('将《产品发布说明.docx》翻译为英文，保留标题层级、表格和数字格式；“智汇云”统一译为“Insight Cloud”，产品型号不翻译。'),
  },
  {
    type: 'fill_table',
    label: t('填表制表'),
    shortLabel: t('填表'),
    color: '#0f766e',
    bg: '#effdfa',
    icon: fillTableIcon,
    defaultTitle: '填表或制表',
    placeholder: t('例如：把统计结果填入指定 Excel 或生成结构化明细表。'),
    defaultConfig: { target: 'Word / Excel / PDF / 表格', outputAlias: '表格结果' },
    usageDescription: t('用于把上游结构化结果写入指定表格模板，或按明确列结构生成新表。应说明目标模板、工作表、字段对应关系和空值处理方式。'),
    usageExample: t('将上游项目数据填入《月度项目台账.xlsx》的“6月台账”工作表，按项目编号匹配行，填写负责人、完成率、回款金额和风险等级。'),
  },
  {
    type: 'export_delivery',
    label: t('导出交付'),
    shortLabel: t('导出'),
    color: '#ea580c',
    bg: '#fff4ed',
    icon: exportDeliveryIcon,
    defaultTitle: '导出交付文件',
    placeholder: t('例如：将复盘稿导出为 Word 和 PDF，便于提交归档。'),
    defaultConfig: { format: 'Word / PDF / Excel / PPT', outputAlias: '交付文件' },
    usageDescription: t('用于把上游最终内容导出为 Word、PDF、Excel 或 PPT 等交付文件。它处理交付格式和文件命名，不应承担内容分析、改写或统计计算。'),
    usageExample: t('将上游《华东区域一季度项目复盘》导出为 Word 和 PDF，文件名分别为《华东区域一季度项目复盘.docx》和《华东区域一季度项目复盘.pdf》。'),
  },
]);

type LocalizedSelectOption = {
  value: string;
  zh: string;
  en: string;
  aliases?: string[];
};

const publishChannelSuggestions: LocalizedSelectOption[] = [
  { value: 'generic', zh: '通用', en: 'Generic' },
  { value: 'website', zh: '官网', en: 'Website' },
  { value: 'docs', zh: '产品文档', en: 'Docs' },
  { value: 'knowledge_base', zh: '知识库', en: 'Knowledge Base' },
  { value: 'email', zh: '邮件', en: 'Email' },
  { value: 'wechat_official', zh: '微信公众号', en: 'WeChat Official Account' },
  { value: 'zhihu', zh: '知乎', en: 'Zhihu' },
  { value: 'xiaohongshu', zh: '小红书', en: 'Xiaohongshu' },
];

const contentFormSuggestions: LocalizedSelectOption[] = [
  { value: 'article', zh: '文章', en: 'Article' },
  { value: 'report', zh: '报告', en: 'Report' },
  { value: 'brief', zh: '简报', en: 'Brief' },
  { value: 'memo', zh: '备忘录', en: 'Memo' },
  { value: 'guide', zh: '指南', en: 'Guide' },
  { value: 'faq', zh: '问答', en: 'FAQ' },
  { value: 'presentation_outline', zh: '演示大纲', en: 'Presentation Outline' },
];

const targetAudienceSuggestions: LocalizedSelectOption[] = [
  { value: 'general_public', zh: '大众读者', en: 'General Public' },
  { value: 'professionals', zh: '专业人士', en: 'Professionals' },
  { value: 'decision_makers', zh: '决策者', en: 'Decision Makers' },
  { value: 'developers', zh: '开发者', en: 'Developers' },
  { value: 'students', zh: '学生', en: 'Students' },
  { value: 'internal_team', zh: '内部团队', en: 'Internal Team' },
];

const preferredStyleSuggestions: LocalizedSelectOption[] = [
  { value: 'professional', zh: '专业', en: 'Professional' },
  { value: 'formal', zh: '正式', en: 'Formal' },
  { value: 'concise', zh: '简洁', en: 'Concise' },
  { value: 'analytical', zh: '分析型', en: 'Analytical' },
  { value: 'objective', zh: '客观', en: 'Objective' },
  { value: 'authoritative', zh: '权威', en: 'Authoritative' },
  { value: 'practical', zh: '实用', en: 'Practical' },
  { value: 'storytelling', zh: '故事化', en: 'Storytelling' },
];

const localizedOptionLabel = (item: LocalizedSelectOption) => (locale.value === 'zh-CN' ? item.zh : item.en);
const localizedValueMap = computed(() => {
  const entries = [
    ...publishChannelSuggestions,
    ...contentFormSuggestions,
    ...targetAudienceSuggestions,
    ...preferredStyleSuggestions,
  ];
  return new Map(entries.flatMap((item) => [
    [item.value, localizedOptionLabel(item)],
    [item.zh, localizedOptionLabel(item)],
    [item.en, localizedOptionLabel(item)],
    ...(item.aliases || []).map((alias) => [alias, localizedOptionLabel(item)] as [string, string]),
  ] as [string, string][]));
});
const formatLocalizedValues = (items: string[], separator = '、') => (
  items.length
    ? items.map((item) => localizedValueMap.value.get(item) || item).join(separator)
    : t('未配置')
);
const toSelectOptions = (items: LocalizedSelectOption[]) => computed(() => (
  items.map((item) => ({ label: localizedOptionLabel(item), value: item.value }))
));
const publishChannelOptions = toSelectOptions(publishChannelSuggestions);
const contentFormOptions = toSelectOptions(contentFormSuggestions);
const targetAudienceOptions = toSelectOptions(targetAudienceSuggestions);
const preferredStyleOptions = toSelectOptions(preferredStyleSuggestions);

const workflowTypeMap = computed(() => Object.fromEntries(workflowNodeTypes.value.map((item) => [item.type, item])));
const normalizedStepText = computed(() => workflowSteps.value.map((item) => buildNodeText(item).trim()).filter(Boolean).join('\n'));
const workflowPreviewNodes = computed(() => workflowSteps.value.map((item) => ({
  id: item.id,
  label: item.outputAlias || item.businessConfig?.outputAlias || item.title || workflowTypeLabel(item.type),
  type: item.type,
  color: workflowTypeMeta(item.type).color,
  icon: workflowTypeMeta(item.type).icon,
})));
const stepListLoadingText = computed(() => {
  if (optimizing.value) return t('正在优化当前业务步骤');
  if (supplementingStep.value) return t('正在补充业务步骤');
  return t('正在生成业务逻辑步骤');
});
const canEnrichWritingStyle = computed(() => {
  if (!skill.value?.name?.trim()) return false;
  return Boolean(skill.value.description?.trim() || skill.value.scenario?.trim());
});
const requiredElementsItems = computed(() => parseMultilineItems(requiredElementsText.value));
const requiredSectionsItems = computed(() => flattenSectionTitles(sectionStructure.value));
const forbiddenElementsItems = computed(() => parseMultilineItems(forbiddenElementsText.value));
const sectionStructurePreview = computed(() => flattenSectionPreview(sectionStructure.value));
const targetLengthLabel = computed(() => {
  const min = Number(targetLengthMin.value || 0);
  const max = Number(targetLengthMax.value || 0);
  if (min > 0 && max > 0) return t('{min}-{max} 字', { min, max });
  if (min > 0) return t('不少于 {min} 字', { min });
  if (max > 0) return t('不超过 {max} 字', { max });
  return t('未配置');
});

watch(normalizedStepText, () => {
  if (restoringWorkflow.value) {
    restoringWorkflow.value = false;
    return;
  }
  if (testResult.value) {
    testResult.value = null;
  }
});

function typeLabel(type: SkillType): string {
  return type === 'workflow' ? t('工作流') : t('写作规范');
}

function createId(): string {
  return `step_${Date.now()}_${Math.random().toString(16).slice(2, 8)}`;
}

function workflowTypeMeta(type: WorkflowNodeType | string) {
  return workflowTypeMap.value[String(type)] || workflowTypeMap.value.generate_content || workflowNodeTypes.value[0];
}

function workflowTypeLabel(type: WorkflowNodeType | string): string {
  return workflowTypeMeta(type).label;
}

function serializeWorkflowNodeCatalog() {
  return workflowNodeTypes.value.map((item) => ({
    type: item.type,
    name: item.label,
    usageDescription: String(item.usageDescription || ''),
    usageExample: String(item.usageExample || ''),
  }));
}

function createWorkflowNode(type: WorkflowNodeType = 'extract_info', seed: Partial<WorkflowStep> = {}): WorkflowStep {
  const meta = workflowTypeMeta(type);
  const businessConfig = {
    ...(meta.defaultConfig || {}),
    ...(seed.businessConfig || {}),
  };
  const outputAlias = seed.outputAlias || String(businessConfig.outputAlias || '').trim();
  return {
    id: seed.id || createId(),
    type,
    title: seed.title || meta.defaultTitle,
    text: seed.text || '',
    businessConfig,
    boundWritingSkillId: seed.boundWritingSkillId || '',
    outputAlias,
  };
}

function buildNodeText(node: Partial<WorkflowStep>): string {
  const title = String(node.title || '').trim();
  const desc = String(node.text || '').trim();
  if (title && desc) return `${title}：${desc}`;
  return desc || title;
}

function serializeWorkflowNodes(): WorkflowNodeDraft[] {
  return workflowSteps.value
    .map((item) => ({
      id: item.id,
      type: item.type,
      title: item.title.trim(),
      description: item.type === 'script_plugin'
        ? String(item.businessConfig?.processingInstruction || '').trim()
        : item.text.trim(),
      businessConfig: {
        ...(item.businessConfig || {}),
        outputAlias: item.outputAlias || item.businessConfig?.outputAlias || '',
      },
      boundWritingSkillId: item.type === 'generate_content' ? item.boundWritingSkillId || '' : '',
      outputAlias: item.outputAlias || item.businessConfig?.outputAlias || '',
    }))
    .filter((item) => item.title || item.description);
}

function serializeWorkflowSteps() {
  return serializeWorkflowNodes().map((item) => ({
    id: item.id || createId(),
    text: [item.title, item.description].filter(Boolean).join('：'),
  }));
}

function normalizeWorkflowNode(value: any, index = 0): WorkflowStep | null {
  if (typeof value === 'string') {
    const text = value.trim();
    const type = inferWorkflowNodeTypeFromText(text);
    return text ? createWorkflowNode(type, { id: createId(), text, title: workflowTypeMeta(type).defaultTitle }) : null;
  }
  if (!value || typeof value !== 'object') return null;
  const rawText = String(value.description || value.text || value.instruction || '').trim();
  const type = workflowNodeTypes.value.some((item) => item.type === value.type)
    ? value.type as WorkflowNodeType
    : inferWorkflowNodeTypeFromText(`${value.title || value.name || ''} ${rawText}`);
  const config = value.businessConfig && typeof value.businessConfig === 'object'
    ? value.businessConfig
    : value.business_config && typeof value.business_config === 'object'
      ? value.business_config
      : {};
  return createWorkflowNode(type, {
    id: String(value.id || createId()),
    title: String(value.title || value.name || '').trim(),
    text: rawText,
    businessConfig: type === 'script_plugin' && !config.processingInstruction
      ? { ...config, processingInstruction: rawText }
      : config,
    boundWritingSkillId: String(value.boundWritingSkillId || value.bound_writing_skill_id || '').trim(),
    outputAlias: String(value.outputAlias || value.output_alias || config.outputAlias || config.output_alias || '').trim(),
  });
}

function inferWorkflowNodeTypeFromText(text: string): WorkflowNodeType {
  const normalized = text.toLowerCase();
  const rules: Array<{ type: WorkflowNodeType; keywords: string[] }> = [
    { type: 'extract_resources', keywords: ['提取资源', '资源提取', '提取图片', '提取链接', '提取url', '提取附件', '图片资源', '内嵌图片'] },
    { type: 'understand_image', keywords: ['图片理解', '图像理解', '多模态', '识图', '图片识别', '图表识别', '截图理解', '视觉理解'] },
    { type: 'read_material', keywords: ['读取', '阅读', '上传', '材料', '文档', '原始', 'word', 'pdf', '附件'] },
    { type: 'extract_info', keywords: ['抽取', '提取', '识别', '字段', '指标', '关键信息', '口径'] },
    { type: 'compute_metric', keywords: ['统计', '计算', '汇总', '求和', '占比', '排序', '排名', '异常', '波动', '总量'] },
    { type: 'data_collect', keywords: ['采集', '抓取', '爬取', '网页链接', '链接', 'url', '正文', '页面内容', 'firecrawl'] },
    { type: 'internal_search', keywords: ['内部', '知识库', '制度', '历史', '过往', '内部口径'] },
    { type: 'external_search', keywords: ['外部', '搜索', '检索', '公开', '新闻', '网页', '行业', '联网'] },
    { type: 'call_tool', keywords: ['mcp', '工具', '接口', '调用', '查询系统', '业务系统', 'api'] },
    { type: 'translate_rewrite', keywords: ['文档翻译', '翻译', '改写', '润色', '压缩', '扩写', '转写', '多语言'] },
    { type: 'fill_table', keywords: ['填表', '制表', '表格', 'excel', 'sheet', '明细表', '模板'] },
    { type: 'export_delivery', keywords: ['导出', '交付', '下载', '归档', 'word', 'pdf', 'ppt', '文件'] },
    { type: 'generate_content', keywords: ['生成', '撰写', '写作', '成稿', '草稿', '报告', '专报', '复盘稿', '内容'] },
  ];
  return rules.find((rule) => rule.keywords.some((keyword) => normalized.includes(keyword)))?.type || 'generate_content';
}

function createSectionNode(seed: Partial<SectionNode> = {}): SectionNode {
  return {
    id: seed.id || `section_${Date.now()}_${Math.random().toString(16).slice(2, 8)}`,
    title: seed.title || '',
    mustIncludeText: seed.mustIncludeText || '',
    avoidText: seed.avoidText || '',
    notes: seed.notes || '',
    children: Array.isArray(seed.children) ? seed.children : [],
  };
}

function addSection(parent?: SectionNode) {
  const next = createSectionNode();
  if (parent) {
    parent.children.push(next);
    return;
  }
  sectionStructure.value.push(next);
}

function moveSection(list: SectionNode[], index: number, direction: -1 | 1) {
  const nextIndex = index + direction;
  if (nextIndex < 0 || nextIndex >= list.length) return;
  const [item] = list.splice(index, 1);
  list.splice(nextIndex, 0, item);
}

function removeSection(list: SectionNode[], index: number) {
  list.splice(index, 1);
}

function beginRestoreWorkflow() {
  restoringWorkflow.value = true;
  window.setTimeout(() => {
    restoringWorkflow.value = false;
  }, 0);
}

function cloneWorkflowStep(step: WorkflowStep): WorkflowStep {
  return {
    ...step,
    businessConfig: JSON.parse(JSON.stringify(step.businessConfig || {})),
  };
}

function snapshotWorkflowSteps(): WorkflowStep[] {
  return workflowSteps.value.map((step) => cloneWorkflowStep(step));
}

function pushWorkflowAiUndo(label: string) {
  workflowAiUndoStack.value = [
    {
      label,
      steps: snapshotWorkflowSteps(),
      activeStepId: activeStepId.value,
    },
    ...workflowAiUndoStack.value,
  ].slice(0, 10);
}

function undoLastAiWorkflowChange() {
  const [latest, ...rest] = workflowAiUndoStack.value;
  if (!latest) return;
  beginRestoreWorkflow();
  workflowSteps.value = latest.steps.map((step) => cloneWorkflowStep(step));
  activeStepId.value = latest.activeStepId || workflowSteps.value[0]?.id || '';
  workflowAiUndoStack.value = rest;
  testResult.value = null;
  message.success(t('已撤回上一次 AI 修改'));
}

function currentStepSnapshot(): string[] {
  return workflowSteps.value.map((item) => item.text.trim()).filter(Boolean);
}

function normalizeStoredCheck(value: any): WorkflowTestResult | null {
  const result = value?.result || value;
  if (!result || typeof result !== 'object') return null;
  const logic = result.logic && typeof result.logic === 'object' ? result.logic : {};
  return {
    testedAt: String(result.testedAt || value?.checkedAt || ''),
    pass: Boolean(result.pass),
    logic: {
      label: String(logic.label || t('需要澄清')),
      level: logic.level === 'success' ? 'success' : 'warning',
      summary: String(logic.summary || t('未保存明确的逻辑说明。')),
    },
    coverage: Array.isArray(result.coverage) ? result.coverage : [],
    readiness: Array.isArray(result.readiness) ? result.readiness : [],
    suggestions: Array.isArray(result.suggestions) ? result.suggestions : [],
    conclusion: String(result.conclusion || t('未保存明确结论。')),
  };
}

function normalizeStringArray(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  const out: string[] = [];
  const seen = new Set<string>();
  value.forEach((item) => {
    const text = String(item || '').trim();
    if (!text) return;
    const key = text.toLowerCase();
    if (seen.has(key)) return;
    seen.add(key);
    out.push(text);
  });
  return out;
}

function splitLegacyBulletLine(value: string): string[] {
  const normalized = String(value || '')
    .replace(/\u00a0/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
  if (!normalized) return [];
  const matches = normalized.match(/(?:^|(?:\s+-\s+))[^-][^-]*(?=(?:\s+-\s+)|$)/g);
  if (!matches || matches.length <= 1) {
    return [normalized];
  }
  return matches.map((item) => item.replace(/^\s*-\s*/, '').trim()).filter(Boolean);
}

function parseMultilineItems(value: unknown): string[] {
  const parts = Array.isArray(value) ? value : [value];
  const out: string[] = [];
  const seen = new Set<string>();
  parts.forEach((part) => {
    const text = String(part || '');
    text
      .split(/\r?\n/)
      .flatMap((line) => splitLegacyBulletLine(line))
      .map((item) => item.replace(/^[\-\u2022\u00b7\s]+/, '').trim())
      .filter(Boolean)
      .forEach((item) => {
        const key = item.toLowerCase();
        if (seen.has(key)) return;
        seen.add(key);
        out.push(item);
      });
  });
  return out;
}

function normalizeSectionNode(value: any): SectionNode | null {
  if (typeof value === 'string') {
    const title = value.trim();
    return title ? createSectionNode({ title }) : null;
  }
  if (!value || typeof value !== 'object') return null;
  const title = String(value.title || value.name || value.heading || '').trim();
  if (!title) return null;
  const mustInclude = parseMultilineItems(value.must_include || value.mustInclude || value.required_elements || value.requiredElements);
  const avoid = parseMultilineItems(value.avoid || value.must_avoid || value.mustAvoid || value.forbidden_elements || value.forbiddenElements);
  const children = Array.isArray(value.children)
    ? value.children.map((item: any) => normalizeSectionNode(item)).filter(Boolean) as SectionNode[]
    : [];
  return createSectionNode({
    title,
    mustIncludeText: mustInclude.join('\n'),
    avoidText: avoid.join('\n'),
    notes: String(value.notes || value.description || '').trim(),
    children,
  });
}

function hydrateSectionStructure(value: unknown, fallbackSections: unknown = []): SectionNode[] {
  const source = Array.isArray(value) && value.length ? value : fallbackSections;
  if (!Array.isArray(source)) return [];
  return source.map((item) => normalizeSectionNode(item)).filter(Boolean) as SectionNode[];
}

function serializeSectionStructure(nodes: SectionNode[], level = 1): Array<Record<string, any>> {
  return nodes
    .map((node) => {
      const title = node.title.trim();
      if (!title) return null;
      const item: Record<string, any> = {
        title,
        level,
        must_include: parseMultilineItems(node.mustIncludeText),
        avoid: parseMultilineItems(node.avoidText),
        notes: node.notes.trim(),
        children: serializeSectionStructure(node.children || [], level + 1),
      };
      return item;
    })
    .filter(Boolean) as Array<Record<string, any>>;
}

function flattenSectionTitles(nodes: SectionNode[]): string[] {
  const out: string[] = [];
  const walk = (items: SectionNode[]) => {
    items.forEach((item) => {
      const title = item.title.trim();
      if (title) out.push(title);
      if (item.children?.length) walk(item.children);
    });
  };
  walk(nodes);
  return out;
}

function flattenSectionPreview(nodes: SectionNode[]): SectionPreviewItem[] {
  const out: SectionPreviewItem[] = [];
  const walk = (items: SectionNode[], level: number) => {
    items.forEach((item) => {
      const title = item.title.trim();
      if (title) {
        out.push({
          key: `${item.id}_${level}`,
          title,
          level,
          mustInclude: parseMultilineItems(item.mustIncludeText),
        });
      }
      if (item.children?.length) walk(item.children, level + 1);
    });
  };
  walk(nodes, 1);
  return out;
}

function buildWritingStyleContractJson(): Record<string, any> {
  const min = Number(targetLengthMin.value || 0);
  const max = Number(targetLengthMax.value || 0);
  const serializedSections = serializeSectionStructure(sectionStructure.value);
  const sectionTitles = flattenSectionTitles(sectionStructure.value);
  const targetLength = {
    min: min > 0 ? min : undefined,
    max: max > 0 ? max : undefined,
    unit: targetLengthUnit.value || 'chinese_chars',
  };
  return {
    skill_type: 'style',
    name: skill.value?.name || '',
    summary: skill.value?.description || '',
    applicable_scenarios: skill.value?.scenario || '',
    publish_channel: [...publishChannelInput.value],
    content_form: [...contentFormInput.value],
    target_audience: [...targetAudienceInput.value],
    preferred_style: [...preferredStyleInput.value],
    target_length: targetLength,
    targetLength,
    section_structure: serializedSections,
    sectionStructure: serializedSections,
    required_sections: sectionTitles,
    required_elements: [...requiredElementsItems.value],
    forbidden_elements: [...forbiddenElementsItems.value],
  };
}

function buildWritingStyleDraft(): WritingStyleDraft {
  const serializedSections = serializeSectionStructure(sectionStructure.value);
  return {
    publishChannel: [...publishChannelInput.value],
    contentForm: [...contentFormInput.value],
    targetAudience: [...targetAudienceInput.value],
    preferredStyle: [...preferredStyleInput.value],
    targetLength: {
      min: Number(targetLengthMin.value || 0) || undefined,
      max: Number(targetLengthMax.value || 0) || undefined,
      unit: targetLengthUnit.value || 'chinese_chars',
    },
    sectionStructure: serializedSections,
    requiredSections: flattenSectionTitles(sectionStructure.value),
    requiredElements: [...requiredElementsItems.value],
    forbiddenElements: [...forbiddenElementsItems.value],
    inputProfile: styleInputProfile.value,
    contractJson: styleContractJson.value,
    skillMarkdown: styleSkillMarkdown.value,
  };
}

function applyWritingStyleContract(contract: Record<string, any>) {
  publishChannelInput.value = normalizeStringArray(contract.publish_channel);
  contentFormInput.value = normalizeStringArray(contract.content_form);
  targetAudienceInput.value = normalizeStringArray(contract.target_audience);
  preferredStyleInput.value = normalizeStringArray(contract.preferred_style);
  const targetLength = contract.target_length && typeof contract.target_length === 'object'
    ? contract.target_length
    : contract.targetLength && typeof contract.targetLength === 'object'
      ? contract.targetLength
      : {};
  targetLengthMin.value = Number(targetLength.min || targetLength.min_words || 0) || null;
  targetLengthMax.value = Number(targetLength.max || targetLength.max_words || 0) || null;
  targetLengthUnit.value = String(targetLength.unit || 'chinese_chars');
  sectionStructure.value = hydrateSectionStructure(
    contract.section_structure || contract.sectionStructure,
    contract.required_sections || contract.requiredSections,
  );
  requiredElementsText.value = parseMultilineItems(contract.required_elements).join('\n');
  forbiddenElementsText.value = parseMultilineItems(contract.forbidden_elements).join('\n');
  styleContractJson.value = { ...contract };
}

function hydrateWritingStyle(source: SkillItem) {
  const config = source.config && typeof source.config === 'object' ? source.config : {};
  const contract = config.contractJson && typeof config.contractJson === 'object'
    ? config.contractJson
    : config.contract_json && typeof config.contract_json === 'object'
      ? config.contract_json
      : buildWritingStyleContractJson();
  applyWritingStyleContract(contract);
  styleInputProfile.value = config.inputProfile && typeof config.inputProfile === 'object'
    ? { ...config.inputProfile }
    : config.input_profile && typeof config.input_profile === 'object'
      ? { ...config.input_profile }
      : { ...contract };
  styleSkillMarkdown.value = String(config.skillMarkdown || config.skill_markdown || '').trim();
}

function isSameStepSnapshot(left: unknown, right: string[]): boolean {
  if (!Array.isArray(left)) return false;
  const normalized = left.map((item) => String(item || '').trim()).filter(Boolean);
  return normalized.length === right.length && normalized.every((item, index) => item === right[index]);
}

function hydrateWorkflow(source: SkillItem): boolean {
  const rawNodes = source.config?.workflowNodes;
  if (Array.isArray(rawNodes) && rawNodes.length) {
    const hydrated = rawNodes
      .map((item: any, index: number) => normalizeWorkflowNode(item, index))
      .filter(Boolean) as WorkflowStep[];
    if (hydrated.length) {
      beginRestoreWorkflow();
      workflowAiUndoStack.value = [];
      workflowSteps.value = hydrated;
      activeStepId.value = workflowSteps.value[0]?.id || '';
      const lastCheck = source.config?.lastWorkflowCheck || source.config?.lastFrontendTest;
      testResult.value = isSameStepSnapshot(lastCheck?.stepsSnapshot, currentStepSnapshot())
        ? normalizeStoredCheck(lastCheck)
        : null;
      stepGenerationError.value = '';
      return true;
    }
  }
  const rawSteps = source.config?.workflowSteps;
  if (Array.isArray(rawSteps) && rawSteps.length) {
    const hydrated = rawSteps
      .map((item: any, index: number) => normalizeWorkflowNode(
        typeof item === 'object'
          ? { ...item, description: item?.text || item?.description || '' }
          : String(item || ''),
        index,
      ))
      .filter(Boolean) as WorkflowStep[];
    if (hydrated.length) {
      beginRestoreWorkflow();
      workflowAiUndoStack.value = [];
      workflowSteps.value = hydrated;
      activeStepId.value = workflowSteps.value[0]?.id || '';
      const lastCheck = source.config?.lastWorkflowCheck || source.config?.lastFrontendTest;
      testResult.value = isSameStepSnapshot(lastCheck?.stepsSnapshot, currentStepSnapshot())
        ? normalizeStoredCheck(lastCheck)
        : null;
      stepGenerationError.value = '';
      return true;
    }
  }
  beginRestoreWorkflow();
  workflowAiUndoStack.value = [];
  workflowSteps.value = [];
  activeStepId.value = workflowSteps.value[0]?.id || '';
  testResult.value = null;
  stepGenerationError.value = '';
  return false;
}

function moveStep(index: number, direction: -1 | 1) {
  const nextIndex = index + direction;
  if (nextIndex < 0 || nextIndex >= workflowSteps.value.length) return;
  const next = [...workflowSteps.value];
  const [item] = next.splice(index, 1);
  next.splice(nextIndex, 0, item);
  workflowSteps.value = next;
}

function onDragStart(stepId: string, event: DragEvent) {
  draggingStepId.value = stepId;
  dragOverStepId.value = '';
  if (event.dataTransfer) {
    event.dataTransfer.effectAllowed = 'move';
    event.dataTransfer.dropEffect = 'move';
    event.dataTransfer.setData('text/plain', stepId);
  }
}

function onDragOver(stepId: string) {
  if (!draggingStepId.value || draggingStepId.value === stepId) return;
  dragOverStepId.value = stepId;
}

function onDrop(targetStepId: string) {
  const sourceStepId = draggingStepId.value;
  draggingStepId.value = '';
  dragOverStepId.value = '';
  if (!sourceStepId || sourceStepId === targetStepId) return;
  const current = [...workflowSteps.value];
  const fromIndex = current.findIndex((item) => item.id === sourceStepId);
  const toIndex = current.findIndex((item) => item.id === targetStepId);
  if (fromIndex < 0 || toIndex < 0 || fromIndex === toIndex) return;
  const [dragged] = current.splice(fromIndex, 1);
  current.splice(toIndex, 0, dragged);
  workflowSteps.value = current;
}

function onDragEnd() {
  draggingStepId.value = '';
  dragOverStepId.value = '';
}

function removeStep(stepId: string) {
  if (workflowSteps.value.length <= 1) {
    message.warning(t('至少保留一个业务步骤'));
    return;
  }
  workflowSteps.value = workflowSteps.value.filter((item) => item.id !== stepId);
  if (activeStepId.value === stepId) {
    activeStepId.value = workflowSteps.value[0]?.id || '';
  }
}

function handleNodeTypeChange(step: WorkflowStep, newType: WorkflowNodeType) {
  step.type = newType;
  const meta = workflowTypeMeta(newType);
  if (meta.defaultConfig) {
    if (!step.businessConfig) {
      step.businessConfig = {};
    }
    for (const key of Object.keys(meta.defaultConfig)) {
      if (step.businessConfig[key] === undefined) {
        step.businessConfig[key] = JSON.parse(JSON.stringify(meta.defaultConfig[key]));
      }
    }
  }
}

function appendNodeByType(type: WorkflowNodeType) {
  const text = newStepText.value.trim();
  const next = createWorkflowNode(type, text ? { text } : {});
  workflowSteps.value = [...workflowSteps.value, next];
  activeStepId.value = next.id;
  if (text) newStepText.value = '';
  testResult.value = null;
}

function mapGeneratedNodes(items: WorkflowNodeDraft[]): WorkflowStep[] {
  return (items || [])
    .map((item, index) => {
      const normalized = normalizeWorkflowNode(item, index);
      if (!normalized) return null;
      return normalized;
    })
    .filter(Boolean) as WorkflowStep[];
}

function buildCheckRecord(result: WorkflowTestResult) {
  return {
    id: `check_${Date.now()}_${Math.random().toString(16).slice(2, 8)}`,
    checkedAt: result.testedAt,
    stepsSnapshot: currentStepSnapshot(),
    result,
  };
}

async function persistWorkflowCheck(result: WorkflowTestResult) {
  if (!skill.value) return;
  const record = buildCheckRecord(result);
  const existingHistory = Array.isArray(skill.value.config?.workflowCheckHistory)
    ? skill.value.config.workflowCheckHistory
    : [];
  try {
    const updated = await updateSkill(skill.value.id, {
      name: skill.value.name,
      description: skill.value.description,
      scenario: skill.value.scenario,
      type: skill.value.type,
      enabled: skill.value.enabled !== false,
      config: {
        ...(skill.value.config || {}),
        workflowNodes: serializeWorkflowNodes(),
        workflowSteps: serializeWorkflowSteps(),
        lastWorkflowCheck: record,
        workflowCheckHistory: [record, ...existingHistory].slice(0, 10),
      },
    });
    skill.value = updated;
  } catch (error: any) {
    message.warning(error?.response?.data?.detail || t('检查结果未能保存到 Skill'));
  }
}

async function regenerateSteps() {
  if (!skill.value) return;
  generatingSteps.value = true;
  stepGenerationError.value = '';
  try {
    const result = await generateWorkflowNodes({
      name: skill.value.name,
      description: skill.value.description,
      scenario: skill.value.scenario,
      existingNodes: [],
      nodeCatalog: serializeWorkflowNodeCatalog(),
      maxNodes: 12,
      mode: 'generate',
    });
    const generated = mapGeneratedNodes(result.nodes || []);
    if (generated.length) {
      pushWorkflowAiUndo(t('重新生成步骤'));
      workflowSteps.value = generated;
      activeStepId.value = workflowSteps.value[0]?.id || '';
      testResult.value = null;
      stepGenerationError.value = '';
      message.success(t('已生成业务逻辑步骤'));
    } else {
      stepGenerationError.value = result.message || t('未生成可用业务逻辑步骤');
      message.warning(result.message || t('未生成可用业务逻辑步骤，请调整 Skill 描述后重试'));
    }
  } catch (error: any) {
    stepGenerationError.value = error?.response?.data?.detail || error?.message || t('生成步骤失败，请稍后重试');
    message.error(stepGenerationError.value);
  } finally {
    generatingSteps.value = false;
  }
}

async function optimizeSteps() {
  if (!skill.value) return;
  const existingNodes = serializeWorkflowNodes();
  if (!existingNodes.length) {
    message.warning(t('请先生成或填写业务步骤，再使用 AI 优化当前步骤'));
    return;
  }
  optimizing.value = true;
  stepGenerationError.value = '';
  try {
    const result = await generateWorkflowNodes({
      name: skill.value.name,
      description: skill.value.description,
      scenario: skill.value.scenario,
      existingNodes,
      nodeCatalog: serializeWorkflowNodeCatalog(),
      maxNodes: Math.max(8, Math.min(12, existingNodes.length + 3)),
      mode: 'optimize',
    });
    const optimized = mapGeneratedNodes(result.nodes || []);
    if (!optimized.length) {
      stepGenerationError.value = result.message || t('未返回可用的优化结果');
      message.warning(stepGenerationError.value);
      return;
    }
    pushWorkflowAiUndo(t('AI 优化当前步骤'));
    workflowSteps.value = optimized;
    activeStepId.value = workflowSteps.value[0]?.id || '';
    testResult.value = null;
    message.success(t('已基于当前步骤完成优化'));
  } catch (error: any) {
    stepGenerationError.value = error?.response?.data?.detail || error?.message || t('优化当前步骤失败，请稍后重试');
    message.error(stepGenerationError.value);
  } finally {
    optimizing.value = false;
  }
}

async function supplementStepWithAi() {
  if (!skill.value) return;
  const supplement = newStepText.value.trim();
  if (!supplement) return;
  supplementingStep.value = true;
  stepGenerationError.value = '';
  try {
    const result = await generateWorkflowNodes({
      name: skill.value.name,
      description: skill.value.description,
      scenario: skill.value.scenario,
      supplement,
      nodeCatalog: serializeWorkflowNodeCatalog(),
      mode: 'supplement_step',
    });
    const supplemented = mapGeneratedNodes(result.nodes || []);
    if (!supplemented.length) {
      stepGenerationError.value = result.message || t('未返回可用的补充结果');
      message.warning(stepGenerationError.value);
      return;
    }
    const nextStep: WorkflowStep = {
      id: createId(),
      type: supplemented[0]?.type || 'generate_content',
      title: supplemented[0]?.title || '补充业务节点',
      text: supplemented[0]?.text || supplement,
      businessConfig: supplemented[0]?.businessConfig || {},
      boundWritingSkillId: supplemented[0]?.boundWritingSkillId || '',
      outputAlias: supplemented[0]?.outputAlias || '',
    };
    pushWorkflowAiUndo(t('AI 优化添加'));
    workflowSteps.value = [...workflowSteps.value, nextStep];
    activeStepId.value = nextStep.id;
    newStepText.value = '';
    testResult.value = null;
    message.success(t('已补充并加入新的业务步骤'));
  } catch (error: any) {
    stepGenerationError.value = error?.response?.data?.detail || error?.message || t('补充业务步骤失败，请稍后重试');
    message.error(stepGenerationError.value);
  } finally {
    supplementingStep.value = false;
  }
}

async function polishStepRequirement(step: WorkflowStep) {
  if (!skill.value) return;
  const currentText = String(step.text || '').trim();
  if (!currentText) {
    message.warning(t('请先填写节点要求'));
    return;
  }
  polishingStepId.value = step.id;
  stepGenerationError.value = '';
  try {
    const result = await polishWorkflowNode({
      name: skill.value.name,
      description: skill.value.description,
      scenario: skill.value.scenario,
      node: {
        id: step.id,
        type: step.type,
        title: step.title,
        description: step.text,
        businessConfig: step.businessConfig || {},
        boundWritingSkillId: step.boundWritingSkillId || '',
        outputAlias: step.outputAlias || '',
      },
      existingNodes: serializeWorkflowNodes(),
      nodeCatalog: serializeWorkflowNodeCatalog(),
    });
    const polished = String(result.text || '').trim();
    if (!polished) {
      stepGenerationError.value = result.message || t('未返回可用的润色结果');
      message.warning(stepGenerationError.value);
      return;
    }
    if (polished === currentText) {
      message.info(t('AI 润色后内容未发生变化'));
      return;
    }
    pushWorkflowAiUndo(t('AI 润色'));
    step.text = polished;
    activeStepId.value = step.id;
    testResult.value = null;
    message.success(t('已润色节点要求'));
  } catch (error: any) {
    stepGenerationError.value = error?.response?.data?.detail || error?.message || t('润色节点要求失败，请稍后重试');
    message.error(stepGenerationError.value);
  } finally {
    polishingStepId.value = '';
  }
}

async function runWorkflowTest() {
  if (!skill.value) return;
  const steps = workflowSteps.value.map((item) => buildNodeText(item).trim()).filter(Boolean);
  if (!steps.length) {
    message.warning(t('请先生成或填写业务步骤'));
    return;
  }
  testing.value = true;
  try {
    const result = await checkWorkflowNodes({
      name: skill.value.name,
      description: skill.value.description,
      scenario: skill.value.scenario,
      steps,
      nodes: serializeWorkflowNodes(),
    });
    const checkedAt = formatAdminDateTime(new Date().toISOString(), '');
    const nextResult: WorkflowTestResult = {
      testedAt: checkedAt,
      pass: Boolean(result.pass),
      logic: {
        label: result.logic?.label || t('需要澄清'),
        level: result.logic?.level === 'success' ? 'success' : 'warning',
        summary: result.logic?.summary || t('后端未返回明确的逻辑说明。'),
      },
      coverage: Array.isArray(result.coverage) ? result.coverage : [],
      readiness: Array.isArray(result.readiness) ? result.readiness : [],
      suggestions: Array.isArray(result.suggestions) && result.suggestions.length
        ? result.suggestions
        : [t('后端未返回具体建议，请检查步骤是否覆盖目标、输入、判断、异常和输出。')],
      conclusion: result.conclusion || t('本次检查未返回明确结论。'),
    };
    testResult.value = nextResult;
    await persistWorkflowCheck(nextResult);
  } catch (error: any) {
    message.error(error?.response?.data?.detail || error?.message || t('检查业务逻辑失败，请稍后重试'));
  } finally {
    testing.value = false;
  }
}

function scriptPluginInstructionSignature(step: WorkflowStep): string {
  return String(step.businessConfig?.processingInstruction || '').trim();
}

function scriptPluginSignature(step: WorkflowStep): string {
  const payload = [
    step.id,
    scriptPluginInstructionSignature(step),
    String(step.businessConfig?.pluginCode || ''),
  ].join('\u0000');
  let hashA = 2166136261;
  let hashB = 5381;
  for (let index = 0; index < payload.length; index += 1) {
    const code = payload.charCodeAt(index);
    hashA = Math.imul(hashA ^ code, 16777619);
    hashB = Math.imul(hashB, 33) ^ code;
  }
  return `v1:${payload.length}:${(hashA >>> 0).toString(16)}:${(hashB >>> 0).toString(16)}`;
}

function isScriptPluginGenerated(step: WorkflowStep): boolean {
  const instruction = scriptPluginInstructionSignature(step);
  return Boolean(
    instruction
    && String(step.businessConfig?.pluginCode || '').trim()
    && String(step.businessConfig?.generatedInstructionSignature || '') === instruction,
  );
}

function isScriptPluginCheckPassed(step: WorkflowStep): boolean {
  const result = scriptCheckResults.value[step.id] as (ScriptPluginCheckResult & { signature?: string }) | undefined;
  const signature = scriptPluginSignature(step);
  return Boolean(
    (result?.pass && result.signature === signature)
    || String(step.businessConfig?.pluginCheckSignature || '') === signature,
  );
}

function persistScriptPluginCheck(step: WorkflowStep, result?: ScriptPluginCheckResult): void {
  if (result?.pass) {
    step.businessConfig.pluginCheckSignature = scriptPluginSignature(step);
    return;
  }
  delete step.businessConfig.pluginCheckSignature;
}

function scriptCheckIssueItems(step: WorkflowStep): ScriptPluginCheckIssue[] {
  const result = scriptCheckResults.value[step.id];
  if (!result) return [];
  const issues = [
    ...((result.errors || []) as ScriptPluginCheckIssue[]),
    ...((result.warnings || []) as ScriptPluginCheckIssue[]),
  ];
  if (issues.length || result.pass) return issues;
  return [{
    level: 'error',
    code: 'CHECK_FAILED',
    message: result.message || t('检测未通过，但检测服务没有返回具体错误明细。建议点击 AI 修复代码，或检查是否使用了不支持的输入/输出写法。'),
    line: null,
  }];
}

function invalidateScriptPluginCheck(stepId: string) {
  if (scriptCheckResults.value[stepId]) {
    const next = { ...scriptCheckResults.value };
    delete next[stepId];
    scriptCheckResults.value = next;
  }
}

function openScriptAdvancedDrawer(step: WorkflowStep) {
  activeScriptStepId.value = step.id;
  activeStepId.value = step.id;
  scriptAdvancedDrawerVisible.value = true;
}

function scriptPluginContextNodes(): WorkflowNodeDraft[] {
  return serializeWorkflowNodes().map((node) => {
    return {
      id: node.id,
      type: node.type,
      title: node.title,
      description: '',
      businessConfig: {},
      outputAlias: node.outputAlias || node.businessConfig?.outputAlias || '',
      boundWritingSkillId: '',
    };
  });
}

async function generateScriptPluginStep(step: WorkflowStep, options: { confirmOverwrite?: boolean; silent?: boolean } = {}): Promise<boolean> {
  if (!skill.value) return false;
  const instruction = String(step.businessConfig?.processingInstruction || '').trim();
  if (!instruction) {
    if (!options.silent) message.warning(t('请先填写处理要求'));
    return false;
  }
  const existingCode = String(step.businessConfig?.pluginCode || '').trim();
  if (existingCode && options.confirmOverwrite && !window.confirm(t('重新生成会覆盖当前高级代码，是否继续？'))) {
    return false;
  }
  generatingScriptStepId.value = step.id;
  try {
    const result = await generateScriptPlugin({
      processingInstruction: instruction,
      nodeTitle: step.title,
      nodeDescription: '',
      skillName: '',
      skillDescription: '',
      scenario: '',
      selectedInputSource: String(step.businessConfig?.selectedInputSource || 'all'),
      selectedInputTypes: Array.isArray(step.businessConfig?.selectedInputTypes) ? step.businessConfig.selectedInputTypes : [],
      workflowNodes: scriptPluginContextNodes(),
    });
    if (!result.code?.trim()) {
      message.error(t('AI 未返回可用代码'));
      return false;
    }
    step.businessConfig.pluginCode = result.code;
    step.businessConfig.generatedInstructionSignature = scriptPluginInstructionSignature(step);
    const check = result.check as (ScriptPluginCheckResult | undefined);
    if (check) {
      scriptCheckResults.value = {
        ...scriptCheckResults.value,
        [step.id]: { ...check, signature: scriptPluginSignature(step) },
      };
      persistScriptPluginCheck(step, check);
    } else {
      invalidateScriptPluginCheck(step.id);
      persistScriptPluginCheck(step);
    }
    const firstNote = (result.notes || [])[0];
    if (check?.pass) {
      if (!options.silent) message.success(firstNote || t('已生成代码并通过规则检测'));
      return true;
    }
    if (!options.silent) message.warning(check?.errors?.[0]?.message || firstNote || t('已生成代码，请根据检测结果修复后保存'));
    return true;
  } catch (error: any) {
    if (!options.silent) message.error(error?.response?.data?.detail || error?.message || t('AI 生成代码失败'));
    return false;
  } finally {
    generatingScriptStepId.value = '';
  }
}

async function checkScriptPluginStep(step: WorkflowStep): Promise<boolean> {
  const code = String(step.businessConfig?.pluginCode || '').trim();
  if (!code) {
    message.warning(t('请先填写脚本代码'));
    return false;
  }
  checkingScriptStepId.value = step.id;
  try {
    const result = await checkScriptPlugin({
      code,
      nodeTitle: step.title,
      nodeDescription: String(step.businessConfig?.processingInstruction || ''),
    });
    scriptCheckResults.value = {
      ...scriptCheckResults.value,
      [step.id]: { ...result, signature: scriptPluginSignature(step) },
    };
    persistScriptPluginCheck(step, result);
    if (result.pass) {
      step.businessConfig.generatedInstructionSignature = scriptPluginInstructionSignature(step);
      message.success(result.llm?.summary || t('脚本代码检测通过'));
      return true;
    }
    return false;
  } catch (error: any) {
    message.error(error?.response?.data?.detail || error?.message || t('检测脚本代码失败'));
    return false;
  } finally {
    checkingScriptStepId.value = '';
  }
}

async function fixScriptPluginStep(step: WorkflowStep): Promise<boolean> {
  const code = String(step.businessConfig?.pluginCode || '').trim();
  if (!code) {
    message.warning(t('请先填写脚本代码'));
    return false;
  }
  fixingScriptStepId.value = step.id;
  try {
    const current = scriptCheckResults.value[step.id];
    const issues = [
      ...((current?.errors || []) as any[]),
      ...((current?.warnings || []) as any[]),
    ];
    const result = await fixScriptPlugin({
      code,
      nodeTitle: step.title,
      nodeDescription: String(step.businessConfig?.processingInstruction || ''),
      issues,
    });
    if (!result.code?.trim()) {
      message.error(t('AI 未返回可用代码'));
      return false;
    }
    step.businessConfig.pluginCode = result.code;
    const check = result.check as (ScriptPluginCheckResult | undefined);
    if (check) {
      scriptCheckResults.value = {
        ...scriptCheckResults.value,
        [step.id]: { ...check, signature: scriptPluginSignature(step) },
      };
      persistScriptPluginCheck(step, check);
    } else {
      invalidateScriptPluginCheck(step.id);
      persistScriptPluginCheck(step);
    }
    if (check?.pass) {
      step.businessConfig.generatedInstructionSignature = scriptPluginInstructionSignature(step);
    }
    message.success((result.notes || [])[0] || t('已完成 AI 修复，请再次确认代码'));
    return Boolean(check?.pass);
  } catch (error: any) {
    message.error(error?.response?.data?.detail || error?.message || t('AI 修复代码失败'));
    return false;
  } finally {
    fixingScriptStepId.value = '';
  }
}

async function ensureScriptPluginsChecked(): Promise<boolean> {
  const scriptSteps = workflowSteps.value.filter((item) => item.type === 'script_plugin');
  for (const step of scriptSteps) {
    if (!String(step.businessConfig?.processingInstruction || '').trim()) {
      activeStepId.value = step.id;
      message.warning(t('数据处理节点必须先填写处理要求'));
      return false;
    }
    if (!String(step.businessConfig?.pluginCode || '').trim()) {
      activeStepId.value = step.id;
      message.warning(t('请先填写或生成脚本代码'));
      return false;
    }
    if (!isScriptPluginCheckPassed(step)) {
      activeStepId.value = step.id;
      message.warning(t('脚本代码已变更或尚未检测通过，请先点击检测代码'));
      return false;
    }
  }
  return true;
}

async function ensureScriptPluginStepReady(step: WorkflowStep): Promise<boolean> {
  if (!String(step.businessConfig?.processingInstruction || '').trim()) {
    message.warning(t('请先填写处理要求'));
    return false;
  }
  if (!String(step.businessConfig?.pluginCode || '').trim()) {
    message.warning(t('请先填写或生成脚本代码'));
    return false;
  }
  if (!isScriptPluginCheckPassed(step)) {
    message.warning(t('脚本代码已变更或尚未检测通过，请先点击检测代码'));
    return false;
  }
  return true;
}

async function saveScriptAdvancedDrawer() {
  const step = activeScriptStep.value;
  if (!step) return;
  scriptDrawerSaving.value = true;
  try {
    const ready = await ensureScriptPluginStepReady(step);
    if (ready) {
      scriptAdvancedDrawerVisible.value = false;
    }
  } finally {
    scriptDrawerSaving.value = false;
  }
}

async function saveWorkflow() {
  if (!skill.value) return;
  if (!serializeWorkflowNodes().length) {
    message.warning(t('请至少填写一个业务步骤'));
    return;
  }
  saving.value = true;
  try {
    if (!(await ensureScriptPluginsChecked())) {
      return;
    }
    const nodes = serializeWorkflowNodes();
    const updated = await updateSkill(skill.value.id, {
      name: skill.value.name,
      description: skill.value.description,
      scenario: skill.value.scenario,
      type: skill.value.type,
      enabled: skill.value.enabled !== false,
      config: {
        ...(skill.value.config || {}),
        workflowNodes: nodes,
        workflowSteps: serializeWorkflowSteps(),
      },
    });
    skill.value = updated;
    hydrateWorkflow(updated);
    message.success(t('工作流配置已保存'));
  } catch (error: any) {
    message.error(error?.response?.data?.detail || t('保存 Skill 失败'));
  } finally {
    saving.value = false;
  }
}

async function enrichWritingStyle() {
  if (!skill.value) return;
  styleEnriching.value = true;
  try {
    const result = await enrichWritingStyleDraft({
      name: skill.value.name,
      description: skill.value.description,
      scenario: skill.value.scenario,
      draft: buildWritingStyleDraft(),
    });
    styleInputProfile.value = result.inputProfile || {};
    styleSkillMarkdown.value = String(result.skillMarkdown || '').trim();
    applyWritingStyleContract(result.contractJson || buildWritingStyleContractJson());
    message.success(t('已补全写作规范配置'));
  } catch (error: any) {
    message.error(error?.response?.data?.detail || error?.message || t('写作规范补全失败'));
  } finally {
    styleEnriching.value = false;
  }
}

async function saveWritingStyle() {
  if (!skill.value) return;
  saving.value = true;
  try {
    const contractJson = buildWritingStyleContractJson();
    const inputProfile = {
      ...(styleInputProfile.value || {}),
      ...contractJson,
    };
    const updated = await updateSkill(skill.value.id, {
      name: skill.value.name,
      description: skill.value.description,
      scenario: skill.value.scenario,
      type: skill.value.type,
      enabled: skill.value.enabled !== false,
      config: {
        ...(skill.value.config || {}),
        inputProfile,
        contractJson,
        skillMarkdown: styleSkillMarkdown.value,
      },
    });
    skill.value = updated;
    hydrateWritingStyle(updated);
    message.success(t('写作规范配置已保存'));
  } catch (error: any) {
    message.error(error?.response?.data?.detail || error?.message || t('保存 Skill 失败'));
  } finally {
    saving.value = false;
  }
}

function goBack() {
  router.push('/skills');
}

function updateHeaderTitle(detail: SkillItem | null) {
  window.dispatchEvent(new CustomEvent('askai-admin-title-change', {
    detail: {
      routeName: 'SkillConfig',
      title: detail?.name || '',
      tag: detail ? typeLabel(detail.type) : '',
    },
  }));
}

async function loadDetail() {
  const requestSequence = ++detailRequestSequence.value;
  const id = String(route.params.id || '');
  if (!id) {
    skill.value = null;
    return;
  }
  loading.value = true;
  try {
    const detail = await fetchSkill(id);
    if (requestSequence !== detailRequestSequence.value || id !== String(route.params.id || '')) return;
    skill.value = detail;
    updateHeaderTitle(detail);
    if (detail.type === 'workflow') {
      hydrateWorkflow(detail);
    } else {
      hydrateWritingStyle(detail);
    }
  } catch (error: any) {
    if (requestSequence !== detailRequestSequence.value) return;
    skill.value = null;
    updateHeaderTitle(null);
    message.error(error?.response?.data?.detail || t('加载 Skill 详情失败'));
  } finally {
    if (requestSequence === detailRequestSequence.value) {
      loading.value = false;
    }
  }
}

async function loadWritingSkillOptions() {
  try {
    const rows = await fetchSkills();
    writingSkillOptions.value = rows
      .filter((item) => item.type === 'writing_style' && item.enabled !== false)
      .map((item) => ({ label: item.name, value: item.id }));
  } catch {
    writingSkillOptions.value = [];
  }
}

async function loadToolOptions() {
  toolOptionsLoading.value = true;
  try {
    toolRows.value = await fetchTools();
  } catch {
    toolRows.value = [];
  } finally {
    toolOptionsLoading.value = false;
  }
}

function selectedToolId(step: WorkflowStep): string | null {
  return String(step.businessConfig?.preferredToolId || step.businessConfig?.toolId || '').trim() || null;
}

function selectedTool(step: WorkflowStep): ExternalToolItem | undefined {
  const toolId = selectedToolId(step);
  return toolRows.value.find((item) => item.id === toolId);
}

function selectedMcpToolName(step: WorkflowStep): string | null {
  return String(step.businessConfig?.preferredMcpToolName || step.businessConfig?.mcpToolName || '').trim() || null;
}

function mcpToolOptions(step: WorkflowStep) {
  const tool = selectedTool(step);
  if (!tool || tool.type !== 'mcp') return [];
  const enabled = new Set(
    Array.isArray(tool.config?.enabledToolNames)
      ? tool.config.enabledToolNames.map((item: unknown) => String(item || '').trim()).filter(Boolean)
      : [],
  );
  return (tool.discoveredTools || [])
    .filter((item) => !enabled.size || enabled.has(String(item.name || '').trim()))
    .map((item) => ({
      label: item.description ? `${item.name} - ${item.description}` : item.name,
      value: item.name,
    }));
}

function handleToolSelect(step: WorkflowStep, toolId: string | null) {
  if (!step.businessConfig) step.businessConfig = {};
  const tool = toolRows.value.find((item) => item.id === toolId);
  step.businessConfig.preferredToolId = tool?.id || '';
  step.businessConfig.preferredToolName = tool?.name || '';
  step.businessConfig.preferredToolType = tool?.type || '';
  step.businessConfig.preferredToolScope = tool ? 'organization' : '';
  step.businessConfig.preferredMcpToolName = '';
}

function handleMcpToolSelect(step: WorkflowStep, mcpToolName: string | null) {
  if (!step.businessConfig) step.businessConfig = {};
  step.businessConfig.preferredMcpToolName = String(mcpToolName || '').trim();
}

function clearSkillHeaderActions() {
  const target = window.document.querySelector('#header-actions-teleport-target');
  target
    ?.querySelectorAll('[data-header-actions-owner="skill-config"], .workflow-header-actions')
    .forEach((item) => item.remove());
}

function refreshHeaderTeleportReady(attempt = 0) {
  const target = window.document.querySelector('#header-actions-teleport-target');
  headerTeleportReady.value = Boolean(target);
  if (!headerTeleportReady.value && attempt < 5) {
    window.requestAnimationFrame(() => refreshHeaderTeleportReady(attempt + 1));
  }
}

async function reloadSkillDetail() {
  headerTeleportReady.value = false;
  skill.value = null;
  updateHeaderTitle(null);
  await nextTick();
  clearSkillHeaderActions();
  await loadDetail();
  await nextTick();
  refreshHeaderTeleportReady();
}

onMounted(async () => {
  await reloadSkillDetail();
  loadWritingSkillOptions();
  loadToolOptions();
});

watch(() => route.params.id, async (nextId, previousId) => {
  if (String(nextId || '') === String(previousId || '')) return;
  await reloadSkillDetail();
});

onUnmounted(() => {
  detailRequestSequence.value += 1;
  headerTeleportReady.value = false;
  clearSkillHeaderActions();
  updateHeaderTitle(null);
});
</script>

<style scoped>
.skill-config-page {
  height: calc(100vh - 70px);
  padding: 0;
  color: #172033;
  overflow: hidden;
}

.skill-config-page :deep(.n-spin),
.skill-config-page :deep(.n-spin-container),
.skill-config-page :deep(.n-spin-content) {
  height: 100%;
  min-height: 0;
}

.skill-config-page :deep(.n-spin-container),
.skill-config-page :deep(.n-spin-content) {
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.style-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  min-height: 58px;
  margin: 16px 24px 0;
  padding: 12px 14px;
  border: 1px solid #e4eaf5;
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.94);
  box-shadow: 0 8px 24px rgba(16, 38, 84, 0.05);
}

.toolbar-copy {
  min-width: 0;
}

.toolbar-title-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.button-icon svg,
.icon-button svg,
.test-icon svg,
.empty-result-icon svg,
.conclusion-icon svg {
  width: 18px;
  height: 18px;
  fill: none;
  stroke: currentColor;
  stroke-width: 2;
  stroke-linecap: round;
  stroke-linejoin: round;
}

.button-icon {
  display: inline-flex;
  color: currentColor;
}

.toolbar-title {
  overflow: hidden;
  color: #14213d;
  font-size: 15px;
  font-weight: 700;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.page-title {
  color: #0f1f45;
  font-size: 20px;
  font-weight: 700;
  line-height: 1.25;
}

.page-subtitle {
  margin-top: 4px;
  color: #65738a;
  font-size: 13px;
}

.toolbar-actions {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 8px;
  flex-wrap: wrap;
}

.workflow-header-actions {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.workflow-header-actions :deep(.ai-optimize-button) {
  box-shadow: none;
}

:deep(.ai-optimize-button) {
  --n-color: #5c61ff !important;
  --n-color-hover: #4e52f0 !important;
  --n-color-pressed: #4347d6 !important;
  --n-color-focus: #5c61ff !important;
  --n-border: 1px solid #5c61ff !important;
  --n-border-hover: 1px solid #4e52f0 !important;
  --n-border-pressed: 1px solid #4347d6 !important;
  --n-border-focus: 1px solid #5c61ff !important;
  --n-text-color: #ffffff !important;
  --n-text-color-hover: #ffffff !important;
  --n-text-color-pressed: #ffffff !important;
  --n-text-color-focus: #ffffff !important;
  box-shadow: 0 8px 18px rgba(92, 97, 255, 0.26);
}

:deep(.regenerate-button) {
  --n-color: #eef4ff !important;
  --n-color-hover: #e3ecff !important;
  --n-color-pressed: #d7e4ff !important;
  --n-color-focus: #eef4ff !important;
  --n-border: 1px solid #b8cdfd !important;
  --n-border-hover: 1px solid #7fa4ff !important;
  --n-border-pressed: 1px solid #5b82f6 !important;
  --n-border-focus: 1px solid #7fa4ff !important;
  --n-text-color: #2f60d9 !important;
  --n-text-color-hover: #2454c9 !important;
  --n-text-color-pressed: #1d43a4 !important;
  --n-text-color-focus: #2454c9 !important;
}

:deep(.ai-supplement-button) {
  --n-color: #5c61ff !important;
  --n-color-hover: #4e52f0 !important;
  --n-color-pressed: #4347d6 !important;
  --n-color-focus: #5c61ff !important;
  --n-border: 1px solid #5c61ff !important;
  --n-border-hover: 1px solid #4e52f0 !important;
  --n-border-pressed: 1px solid #4347d6 !important;
  --n-border-focus: 1px solid #5c61ff !important;
  --n-text-color: #ffffff !important;
  --n-text-color-hover: #ffffff !important;
  --n-text-color-pressed: #ffffff !important;
  --n-text-color-focus: #ffffff !important;
  box-shadow: 0 8px 18px rgba(92, 97, 255, 0.26);
}

.workflow-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.48fr) minmax(340px, 0.72fr);
  gap: 16px;
  padding: 14px 24px 24px;
  flex: 1;
  min-height: 0;
  overflow: hidden;
  box-sizing: border-box;
}

.style-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.3fr) minmax(320px, 0.78fr);
  gap: 16px;
  padding: 16px 24px 24px;
  flex: 1;
  min-height: 0;
  overflow: hidden;
  height: 100%;
  box-sizing: border-box;
}

.shell-panel,
.shell-card {
  border: 1px solid #e4eaf5;
  border-radius: 12px;
  background: #fff;
  box-shadow: 0 10px 30px rgba(16, 38, 84, 0.06);
}

.logic-panel,
.test-panel {
  min-height: 0;
  padding: 18px;
}

.style-panel,
.style-preview-panel {
  min-height: 0;
  padding: 20px;
  overflow: auto;
  scrollbar-width: thin;
  scrollbar-color: #c0d1fb transparent;
}

.style-panel::-webkit-scrollbar,
.style-preview-panel::-webkit-scrollbar {
  width: 6px;
}

.style-panel::-webkit-scrollbar-thumb,
.style-preview-panel::-webkit-scrollbar-thumb {
  background: #c0d1fb;
  border-radius: 999px;
}

.style-panel::-webkit-scrollbar-track,
.style-preview-panel::-webkit-scrollbar-track {
  background: transparent;
}

.logic-panel {
  display: grid;
  grid-template-rows: minmax(0, 1fr) auto;
  gap: 12px;
  max-height: calc(100vh - 98px);
  overflow: hidden;
}

.panel-head,
.result-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
}

.panel-title {
  color: #15223b;
  font-size: 16px;
  font-weight: 700;
}

.panel-desc {
  margin-top: 5px;
  color: #7a879a;
  font-size: 13px;
  line-height: 1.5;
}

.step-list-shell {
  min-height: 0;
  overflow: hidden;
}

.step-list-shell :deep(.n-spin-container),
.step-list-shell :deep(.n-spin-content) {
  height: 100%;
  min-height: 0;
}

.step-list-shell :deep(.n-spin-body) {
  top: 45%;
}

.step-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin-top: 6px;
  height: 100%;
  min-height: 0;
  overflow-y: auto;
  padding-right: 6px;
  padding-bottom: 10px;
  scrollbar-width: thin;
  scrollbar-color: #c0d1fb transparent;
}

.step-list::-webkit-scrollbar {
  width: 6px;
}

.step-list::-webkit-scrollbar-thumb {
  background: #c0d1fb;
  border-radius: 999px;
}

.step-list::-webkit-scrollbar-track {
  background: transparent;
}

.step-empty {
  min-height: 260px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.step-empty :deep(.n-empty__description) {
  max-width: 420px;
  line-height: 1.6;
  white-space: normal;
}

.step-card {
  position: relative;
  display: grid;
  grid-template-columns: 42px minmax(0, 1fr);
  align-items: flex-start;
  gap: 14px;
  padding: 18px 16px 16px 14px;
  border: 1px solid #e6ecf5;
  border-radius: 8px;
  background: linear-gradient(180deg, #ffffff 0%, #fbfcff 100%);
  cursor: pointer;
  transition: border-color 0.2s ease, background 0.2s ease, box-shadow 0.2s ease;
}

.step-card.script-step-card {
  grid-template-columns: 42px minmax(0, 1fr);
}

.step-card .step-tools {
  position: absolute;
  top: 16px;
  right: 12px;
  width: auto;
}

.step-card::before {
  display: none;
}

.drag-handle,
.step-index,
.step-tools {
  align-self: flex-start;
}

.node-rail {
  position: relative;
  z-index: 1;
  display: grid;
  justify-items: center;
  gap: 8px;
  padding-top: 2px;
}

.step-input {
  align-self: stretch;
  min-height: 0;
}

.code-editor-shell {
  overflow: hidden;
  margin-bottom: 8px;
  border: 1px solid #1f2937;
  border-radius: 8px;
  background: #0f172a;
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.04);
}

.code-editor-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  border-bottom: 1px solid rgba(148, 163, 184, 0.2);
  background: #111827;
  color: #cbd5e1;
  padding: 7px 10px;
  font-size: 12px;
}

.code-editor-head span:first-child {
  color: #93c5fd;
  font-weight: 700;
}

.script-plugin-panel {
  display: grid;
  gap: 8px;
  margin-bottom: 8px;
  width: 100%;
  box-sizing: border-box;
  border: 1px solid #dbe5f5;
  border-radius: 8px;
  background: #f8fbff;
  padding: 10px;
}

.script-processing-instruction {
  display: grid;
  gap: 6px;
}

.script-processing-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.script-processing-instruction strong {
  color: #18315a;
  font-size: 13px;
}

.script-generation-tools {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 8px;
}

.script-generation-status {
  display: inline-flex;
  align-items: center;
  height: 24px;
  padding: 0 8px;
  border-radius: 999px;
  background: #fff7ed;
  color: #9a5b13;
  font-size: 12px;
  font-weight: 700;
  white-space: nowrap;
}

.script-generation-status.ready {
  background: #edfdf3;
  color: #13713c;
}

.script-processing-instruction :deep(textarea) {
  font-size: 13px;
  line-height: 1.55;
}

.script-instruction-example {
  display: grid;
  gap: 4px;
  border-radius: 6px;
  background: #eef5ff;
  color: #36577f;
  padding: 8px 10px;
  font-size: 12px;
  line-height: 1.45;
}

.script-instruction-example b {
  color: #1f3b63;
}

.script-plugin-rules {
  display: grid;
  gap: 4px;
  color: #52627a;
  font-size: 12px;
  line-height: 1.5;
}

.script-plugin-rules strong {
  color: #18315a;
  font-size: 13px;
}

.script-plugin-rules code {
  display: block;
  border-radius: 6px;
  background: #eef3fb;
  color: #263b5e;
  padding: 6px 8px;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, 'Liberation Mono', 'Courier New', monospace;
  font-size: 11px;
  line-height: 1.45;
  overflow-wrap: anywhere;
}

.script-contract-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
}

.script-contract-grid > div {
  display: grid;
  gap: 5px;
  min-width: 0;
}

.script-contract-grid b {
  color: #29476f;
  font-size: 12px;
}

.script-plugin-actions {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
}

.script-drawer-body {
  display: flex;
  flex-direction: column;
  gap: 12px;
  height: 100%;
  min-height: 0;
  overflow: hidden;
}

.script-drawer-settings {
  display: grid;
  gap: 8px;
  flex: 0 0 15%;
  min-height: 118px;
  max-height: 180px;
  overflow: auto;
}

.script-drawer-instruction {
  display: grid;
  grid-template-rows: auto minmax(0, 1fr);
  gap: 6px;
  min-height: 0;
}

.script-drawer-instruction-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.script-drawer-instruction strong {
  color: #18315a;
  font-size: 13px;
}

.script-drawer-instruction :deep(textarea) {
  font-size: 13px;
  line-height: 1.5;
  max-height: 100%;
  overflow: auto;
}

.script-drawer-instruction :deep(.n-input),
.script-drawer-instruction :deep(.n-input-wrapper),
.script-drawer-instruction :deep(.n-input__textarea),
.script-drawer-instruction :deep(.n-input__textarea-el) {
  height: 100% !important;
  min-height: 0 !important;
}

.script-drawer-details {
  border: 1px solid #e4edf8;
  border-radius: 8px;
  background: #fbfdff;
  padding: 8px 10px;
}

.script-drawer-details summary {
  cursor: pointer;
  color: #31527c;
  font-size: 12px;
  font-weight: 700;
  user-select: none;
}

.script-drawer-details[open] summary {
  margin-bottom: 8px;
}

.script-drawer-code {
  display: grid;
  grid-template-rows: auto minmax(0, 1fr);
  flex: 1 1 auto;
  min-height: 0;
  margin-bottom: 0;
  overflow: hidden;
}

.script-drawer-body > .script-plugin-actions {
  flex: 0 0 44px;
  min-height: 44px;
  align-content: center;
  align-items: center;
  padding: 6px 0;
  border-top: 1px solid #e6edf7;
  background: #ffffff;
  z-index: 1;
}

.script-drawer-footer {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}

.script-code-empty {
  border: 1px dashed #c9d8ef;
  border-radius: 8px;
  background: #f6f9ff;
  color: #4d6385;
  padding: 10px 12px;
  font-size: 13px;
  line-height: 1.5;
}

.script-advanced {
  border-top: 1px solid #e4edf8;
  padding-top: 8px;
}

.script-advanced summary {
  cursor: pointer;
  color: #31527c;
  font-size: 12px;
  font-weight: 700;
  user-select: none;
}

.script-advanced[open] summary {
  margin-bottom: 8px;
}

.script-check-status {
  border-radius: 999px;
  padding: 2px 8px;
  font-size: 12px;
  font-weight: 600;
}

.script-check-status.ok {
  background: #e8f8ef;
  color: #157347;
}

.script-check-status.error {
  background: #fff0f0;
  color: #c62828;
}

.script-check-result {
  display: grid;
  align-content: start;
  gap: 6px;
  flex: 0 0 20%;
  max-height: none;
  min-height: 150px;
  overflow: auto;
  border: 1px solid #e8edf5;
  border-radius: 8px;
  background: #ffffff;
  padding: 8px;
}

.script-check-summary {
  display: grid;
  gap: 3px;
  border-radius: 6px;
  padding: 7px 8px;
  font-size: 12px;
  line-height: 1.45;
}

.script-check-summary strong {
  font-size: 13px;
}

.script-check-summary span {
  overflow-wrap: anywhere;
}

.script-check-summary.pass {
  background: #edfdf3;
  color: #176b3a;
}

.script-check-summary.fail {
  background: #fff2f2;
  color: #a32020;
}

.script-check-issue {
  display: grid;
  grid-template-columns: 44px minmax(0, 1fr);
  gap: 8px;
  border-radius: 6px;
  padding: 6px 8px;
  font-size: 12px;
  line-height: 1.45;
}

.script-check-issue span {
  font-weight: 700;
}

.script-check-issue p {
  margin: 0;
  overflow-wrap: anywhere;
}

.script-check-issue.error {
  background: #fff2f2;
  color: #a32020;
}

.script-check-issue.warning {
  background: #fff8e6;
  color: #7a5200;
}

.script-check-llm {
  border-radius: 6px;
  background: #eef5ff;
  color: #284369;
  padding: 7px 8px;
  font-size: 12px;
  line-height: 1.45;
}

.workflow-node-body {
  min-width: 0;
}

.node-head-row {
  display: block;
}

.node-description-field {
  width: 100%;
  margin-top: 10px;
}

.node-description-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  margin-bottom: 7px;
}

.node-description-label {
  color: #263750;
  font-size: 13px;
  font-weight: 700;
}

.node-usage-guide {
  margin-top: 8px;
  border-top: 1px solid #dfe8f5;
  color: #42526b;
}

.node-usage-guide summary {
  display: flex;
  align-items: center;
  gap: 6px;
  min-height: 32px;
  color: #64748b;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  list-style: none;
}

.node-usage-guide summary::-webkit-details-marker {
  display: none;
}

.node-usage-guide summary svg {
  width: 15px;
  height: 15px;
  fill: none;
  stroke: currentColor;
  stroke-width: 1.8;
  stroke-linecap: round;
  stroke-linejoin: round;
}

.node-usage-guide[open] summary {
  color: var(--guide-color, #2f6bff);
}

.node-usage-chevron {
  margin-left: auto;
  transition: transform 0.18s ease;
}

.node-usage-guide[open] .node-usage-chevron {
  transform: rotate(180deg);
}

.node-usage-content {
  margin-bottom: 4px;
  padding: 8px 10px;
  border-left: 2px solid var(--guide-color, #2f6bff);
  border-radius: 3px;
  background: #f8faff;
}

.node-usage-content > strong {
  color: #334155;
  font-size: 12px;
}

.node-usage-content > p,
.node-usage-example p {
  margin: 5px 0 0;
  font-size: 12px;
  line-height: 1.65;
}

.node-usage-example {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr);
  gap: 7px;
  margin-top: 7px;
}

.node-usage-example > span {
  margin-top: 5px;
  color: var(--guide-color, #2f6bff);
  font-size: 12px;
  font-weight: 700;
}

.node-type-icon,
.quick-node-icon,
.flow-node-icon {
  width: 16px;
  height: 16px;
  flex: none;
  background: currentColor;
  mask: var(--icon-url) center / contain no-repeat;
  -webkit-mask: var(--icon-url) center / contain no-repeat;
  opacity: 0.9;
}

.node-title-fields {
  min-width: 0;
}

.node-type-row {
  display: grid;
  grid-template-columns: minmax(170px, 220px) minmax(220px, 320px);
  gap: 8px;
  margin-bottom: 8px;
  padding-right: 132px;
}

.node-type-pill {
  display: grid;
  grid-template-columns: 18px minmax(0, 1fr);
  align-items: center;
  gap: 7px;
  min-width: 0;
  border: 1px solid #e4eaf2;
  border-radius: 8px;
  background: #f8fafc;
  padding: 0 8px;
}

.node-type-select {
  min-width: 0;
}

.node-writing-skill-select,
.node-resource-types-select,
.node-tool-select {
  min-width: 0;
}

.node-resource-types-select :deep(.n-base-selection) {
  --n-height: 32px !important;
  --n-border: 1px solid #e4eaf2 !important;
  --n-border-hover: 1px solid #cbd8ef !important;
  --n-border-active: 1px solid #9fb8ee !important;
  --n-border-focus: 1px solid #9fb8ee !important;
  --n-box-shadow-active: 0 0 0 2px rgba(74, 112, 211, 0.08) !important;
  --n-box-shadow-focus: 0 0 0 2px rgba(74, 112, 211, 0.08) !important;
  border-radius: 8px;
  background: #ffffff;
}

.node-resource-types-select :deep(.n-base-selection-tag-wrapper .n-tag) {
  border-radius: 4px !important;
  border: 1px solid #e0e0e6 !important;
  background-color: #fafafc !important;
  color: #333333 !important;
  font-weight: 400 !important;
  font-size: 12px !important;
  padding: 0 8px !important;
  height: 22px !important;
  line-height: 20px !important;
}

.node-resource-types-select :deep(.n-base-selection-tag-wrapper .n-tag .n-tag__close) {
  color: #999999 !important;
  margin-left: 4px !important;
  transition: all 0.2s ease;
}

.node-resource-types-select :deep(.n-base-selection-tag-wrapper .n-tag .n-tag__close:hover) {
  background-color: rgba(0, 0, 0, 0.08) !important;
  color: #333333 !important;
}

.node-type-select :deep(.n-base-selection) {
  --n-height: 30px !important;
  --n-border: 0 !important;
  --n-border-active: 0 !important;
  --n-border-focus: 0 !important;
  --n-box-shadow-active: 0 0 0 2px rgba(74, 112, 211, 0.08) !important;
  --n-box-shadow-focus: 0 0 0 2px rgba(74, 112, 211, 0.08) !important;
  border-radius: 8px;
  background: transparent;
}

.node-writing-skill-select :deep(.n-base-selection),
.node-tool-select :deep(.n-base-selection) {
  --n-height: 32px !important;
  --n-border: 1px solid #e4eaf2 !important;
  --n-border-hover: 1px solid #cbd8ef !important;
  --n-border-active: 1px solid #9fb8ee !important;
  --n-border-focus: 1px solid #9fb8ee !important;
  --n-box-shadow-active: 0 0 0 2px rgba(74, 112, 211, 0.08) !important;
  --n-box-shadow-focus: 0 0 0 2px rgba(74, 112, 211, 0.08) !important;
  border-radius: 8px;
  background: #ffffff;
}

.node-type-row :deep(.n-input-wrapper) {
  min-height: 30px;
  border-radius: 8px;
  background: #ffffff;
}

.step-card:hover {
  border-color: #cbd8ef;
  box-shadow: 0 8px 18px rgba(30, 48, 89, 0.06);
}

.step-card.active {
  border-color: #9fb8ee;
  background: #ffffff;
  box-shadow: 0 8px 22px rgba(45, 77, 140, 0.1);
}

.step-card.dragging {
  opacity: 0.62;
}

.step-card.drag-over {
  border-color: #6f95ff;
  box-shadow: 0 0 0 2px rgba(111, 149, 255, 0.2) inset;
}

.drag-handle {
  display: grid;
  grid-template-columns: repeat(2, 4px);
  gap: 3px;
  justify-content: center;
  cursor: grab;
  opacity: 0.6;
}

.drag-handle:active {
  cursor: grabbing;
}

.drag-handle span {
  width: 3px;
  height: 3px;
  border-radius: 50%;
  background: #aab6c8;
}

.step-index {
  position: relative;
  z-index: 1;
  display: grid;
  place-items: center;
  width: 26px;
  height: 26px;
  border-radius: 999px;
  background: #f3f6fb;
  color: #58708f;
  font-size: 12px;
  font-weight: 700;
  box-shadow: 0 0 0 4px #fff;
}

.step-card.active .step-index {
  box-shadow: 0 0 0 4px #fff;
}

.step-input :deep(.n-input-wrapper) {
  align-items: flex-start;
  min-height: 68px;
  padding: 10px 12px;
  border-radius: 7px;
  background: #ffffff;
}

.step-input :deep(textarea) {
  min-height: 44px !important;
  color: #1f2a44;
  font-size: 14px;
  line-height: 1.6;
}

.step-input :deep(textarea::placeholder) {
  color: #94a3b8;
}

.step-input :deep(.n-input__border) {
  border-color: #d9e2ef;
}

.step-input:hover :deep(.n-input__border) {
  border-color: #9db7ef;
}

.step-tools {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 5px;
  padding-top: 1px;
}

.icon-button {
  display: grid;
  place-items: center;
  width: 30px;
  height: 30px;
  border: 1px solid transparent;
  border-radius: 8px;
  background: transparent;
  color: #50617c;
  cursor: pointer;
  transition: background 0.2s ease, color 0.2s ease, border-color 0.2s ease;
}

.icon-button:hover:not(:disabled) {
  border-color: #d8e3f8;
  background: #f6f9ff;
  color: #2468ff;
}

.icon-button.primary {
  color: #3d67de;
}

.step-card.active .icon-button.primary {
  background: #eef4ff;
  color: #2f60d9;
}

.icon-button.danger:hover:not(:disabled) {
  color: #d03050;
}

.icon-button:disabled {
  cursor: not-allowed;
  opacity: 0.35;
}

.add-step-box {
  z-index: 3;
  margin-top: 0;
  padding: 14px 16px;
  border: 1px solid #dfe8f7;
  border-radius: 8px;
  background: #ffffff;
  box-shadow: 0 -8px 18px rgba(31, 45, 78, 0.06);
}

.add-title-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 10px;
}

.add-title {
  color: #1a2741;
  font-size: 14px;
  font-weight: 700;
}

.add-actions {
  display: flex;
  justify-content: flex-end;
  margin-top: 12px;
}

.quick-node-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 12px;
}

.quick-node-button {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  min-height: 38px;
  border: 1px solid #e1e7ef;
  border-radius: 7px;
  padding: 0 14px;
  font-size: 13px;
  font-weight: 700;
  cursor: pointer;
  transition: border-color 0.15s ease, background 0.15s ease, color 0.15s ease;
}

.quick-node-button:hover {
  border-color: currentColor !important;
  filter: saturate(1.08);
}

.quick-node-help {
  color: #334155;
  font-size: 13px;
  line-height: 1.6;
}

.quick-node-help strong {
  display: block;
  margin-bottom: 5px;
  color: #172033;
  font-size: 14px;
}

.quick-node-help p {
  margin: 0;
}

.quick-node-help > div {
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px solid #e5eaf2;
}

.quick-node-help > div span {
  margin-right: 6px;
  color: #2f6bff;
  font-weight: 700;
}

.quick-node-icon {
  width: 17px;
  height: 17px;
}

.execution-preview-block {
  margin-bottom: 8px;
}

.flow-preview {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  margin-top: 12px;
}

.flow-node {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  width: min(100%, 286px);
  min-height: 38px;
  border: 1px solid #e2e8f2;
  border-radius: 7px;
  background: #fbfcff;
  font-weight: 700;
  font-size: 13px;
  padding: 8px 12px;
  text-align: center;
}

.flow-node span {
  min-width: 0;
  overflow-wrap: anywhere;
}

.flow-arrow {
  color: #9aa6b8;
  font-weight: 700;
  line-height: 1;
}

.flow-empty {
  margin-top: 12px;
  border: 1px dashed #cbd7ea;
  border-radius: 8px;
  color: #8a96aa;
  font-size: 13px;
  padding: 18px;
  text-align: center;
}

.test-panel {
  height: 100%;
  max-height: 100%;
  overflow: auto;
  scrollbar-width: thin;
  scrollbar-color: #c0d1fb transparent;
}

.test-panel::-webkit-scrollbar {
  width: 6px;
}

.test-panel::-webkit-scrollbar-thumb {
  background: #c0d1fb;
  border-radius: 999px;
}

.test-panel::-webkit-scrollbar-track {
  background: transparent;
}

.test-head {
  display: flex;
  align-items: center;
  gap: 12px;
}

.test-icon {
  display: grid;
  place-items: center;
  width: 46px;
  height: 46px;
  border-radius: 999px;
  background: #e8f0ff;
  color: #366aff;
}

.test-icon svg {
  width: 24px;
  height: 24px;
}

.divider {
  height: 1px;
  margin: 18px 0;
  background: #e7edf6;
}

.field-label {
  display: block;
  margin-bottom: 8px;
  color: #21304d;
  font-size: 13px;
  font-weight: 700;
}

.test-action-row {
  display: flex;
  justify-content: flex-end;
  margin-top: 12px;
}

.test-action-row :deep(.n-button) {
  background: #366aff;
}

.result-block {
  margin-top: 18px;
}

.result-title {
  color: #172033;
  font-size: 14px;
  font-weight: 700;
}

.result-meta {
  display: flex;
  align-items: center;
  gap: 10px;
  color: #7a879a;
  font-size: 12px;
}

.result-meta button {
  border: 0;
  background: transparent;
  color: #2468ff;
  cursor: pointer;
}

.result-card {
  margin-top: 10px;
  padding: 12px;
  border: 1px solid #e4eaf5;
  border-radius: 8px;
  background: #fff;
}

.result-card-head {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  align-items: center;
  gap: 8px;
  color: #1c2a45;
  font-size: 13px;
}

.result-card p {
  margin: 8px 0 0;
  color: #67758c;
  font-size: 12px;
  line-height: 1.6;
}

.metric-badge {
  display: grid;
  place-items: center;
  width: 20px;
  height: 20px;
  border-radius: 999px;
  background: #3f6cff;
  color: #fff;
  font-size: 12px;
  font-weight: 700;
}

.coverage-list {
  display: grid;
  gap: 8px;
  margin-top: 10px;
}

.coverage-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  color: #36435a;
  font-size: 12px;
}

.status-ok {
  color: #10a371;
  font-weight: 700;
}

.status-warn {
  color: #c9830b;
  font-weight: 700;
}

.suggestion-list {
  margin: 10px 0 0;
  padding-left: 18px;
  color: #5f6f89;
  font-size: 12px;
  line-height: 1.7;
}

.final-conclusion {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr);
  gap: 10px;
  margin-top: 12px;
  padding: 12px;
  border-radius: 10px;
}

.final-conclusion.pass {
  border: 1px solid #bcebd5;
  background: #effcf6;
  color: #0b8f63;
}

.final-conclusion.warn {
  border: 1px solid #f2d49b;
  background: #fff8e8;
  color: #a66b05;
}

.final-conclusion strong {
  display: block;
  font-size: 13px;
}

.final-conclusion p {
  margin: 4px 0 0;
  font-size: 12px;
  line-height: 1.6;
}

.conclusion-icon {
  display: grid;
  place-items: center;
  width: 26px;
  height: 26px;
  border-radius: 999px;
}

.empty-result {
  display: grid;
  place-items: center;
  gap: 10px;
  min-height: 220px;
  color: #7a879a;
  text-align: center;
}

.empty-result p {
  max-width: 300px;
  margin: 0;
  font-size: 13px;
  line-height: 1.6;
}

.empty-result-icon {
  display: grid;
  place-items: center;
  width: 46px;
  height: 46px;
  border-radius: 999px;
  background: #eef4ff;
  color: #2b64ff;
}

.header-row {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.meta-grid {
  margin-top: 14px;
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.meta-item {
  border: 1px solid #e9eef8;
  border-radius: 10px;
  padding: 12px;
  background: #fcfdff;
}

.meta-label {
  color: #7c889b;
  font-size: 12px;
}

.meta-value {
  margin-top: 6px;
  color: #26344b;
  font-size: 14px;
  line-height: 1.55;
}

.config-shell {
  min-height: 460px;
  margin-top: 12px;
}

.style-section + .style-section {
  margin-top: 20px;
}

.style-grid-fields {
  display: grid;
  gap: 14px;
}

.style-grid-fields-2 {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.style-field {
  min-width: 0;
}

.style-field-wide {
  margin-bottom: 14px;
}

.section-builder {
  margin-bottom: 14px;
}

.section-builder-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 10px;
}

.section-node-list,
.section-child-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.section-child-list {
  margin: 10px 0 0 36px;
}

.section-node-card {
  border: 1px solid #dbe5f4;
  border-radius: 10px;
  padding: 12px;
  background: #fbfdff;
}

.section-node-card-child {
  background: #ffffff;
}

.section-node-main {
  display: grid;
  grid-template-columns: 28px minmax(0, 1fr) auto;
  gap: 10px;
  align-items: flex-start;
}

.section-node-index {
  display: flex;
  align-items: center;
  justify-content: center;
  min-width: 28px;
  height: 28px;
  border-radius: 999px;
  background: #edf3ff;
  color: #2855a6;
  font-size: 12px;
  font-weight: 700;
}

.section-node-content {
  display: flex;
  flex-direction: column;
  gap: 8px;
  min-width: 0;
}

.section-node-fields {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
}

.section-node-actions {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.section-empty {
  padding: 20px 0;
  border: 1px dashed #cbd7ea;
  border-radius: 10px;
  background: #fbfdff;
}

.style-preview-group + .style-preview-group {
  margin-top: 16px;
}

.preview-label {
  color: #7c889b;
  font-size: 12px;
  font-weight: 700;
}

.preview-value {
  margin-top: 6px;
  color: #24334c;
  font-size: 14px;
  line-height: 1.6;
}

.preview-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 8px;
}

.preview-chip {
  display: inline-flex;
  align-items: center;
  border-radius: 999px;
  background: #edf3ff;
  color: #2754a7;
  font-size: 12px;
  font-weight: 600;
  padding: 7px 10px;
}

.preview-chip-danger {
  background: #fff1f4;
  color: #b53b59;
}

.preview-empty {
  color: #8996aa;
  font-size: 12px;
}

.preview-section-tree {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-top: 8px;
}

.preview-section-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  border-left: 3px solid #8fb2ff;
  padding: 6px 8px;
  background: #f5f8ff;
  color: #24334c;
  font-size: 12px;
  line-height: 1.45;
}

.preview-section-row.child {
  margin-left: 16px;
  border-left-color: #b6c6e6;
  background: #fbfdff;
}

.preview-section-title {
  min-width: 0;
  overflow-wrap: anywhere;
}

.preview-section-meta {
  flex: none;
  color: #5b70a3;
  font-size: 11px;
}

.config-title {
  color: #0f1f45;
  font-size: 16px;
  font-weight: 700;
}

.config-note {
  margin: 6px 0 12px;
  color: #6d7a8f;
  font-size: 13px;
}

.json-preview :deep(textarea) {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, 'Liberation Mono', 'Courier New', monospace;
}

@media (max-width: 1180px) {
  .style-toolbar {
    align-items: flex-start;
    flex-direction: column;
  }

  .toolbar-actions {
    justify-content: flex-start;
  }

  .workflow-grid {
    grid-template-columns: minmax(0, 1fr);
  }

  .style-grid {
    grid-template-columns: minmax(0, 1fr);
    height: auto;
  }

  .test-panel {
    position: static;
    max-height: none;
  }

  .logic-panel {
    max-height: none;
  }
}

@media (max-width: 760px) {
  .workflow-grid {
    padding-left: 14px;
    padding-right: 14px;
  }

  .style-toolbar {
    margin-left: 14px;
    margin-right: 14px;
  }

  .step-card {
    grid-template-columns: 32px minmax(0, 1fr);
    padding-right: 14px;
  }

  .step-tools {
    position: static;
    grid-column: 2;
    justify-content: flex-end;
  }

  .node-type-row {
    grid-template-columns: minmax(0, 1fr);
    padding-right: 0;
  }

  .add-actions {
    grid-template-columns: minmax(0, 1fr);
  }

  .meta-grid {
    grid-template-columns: minmax(0, 1fr);
  }

  .style-grid-fields-2 {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
