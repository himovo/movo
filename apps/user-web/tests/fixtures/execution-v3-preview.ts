import { createApp, h } from 'vue'
import ExecutionViewV3 from '../../src/features/execution-v3/components/ExecutionViewV3.vue'
import { createExecutionStoreV3 } from '../../src/features/execution-v3/stores/executionStore'
import type { ExecutionEventV3 } from '../../src/features/execution-v3/domain/protocol'

function event(sequence: number, overrides: Partial<ExecutionEventV3>): ExecutionEventV3 {
  return {
    v: 3, event_id: `preview_${sequence}`, id: `preview_${sequence}`, ts: sequence,
    type: 'item.completed', revision: 1, payload: {}, ...overrides,
  }
}

const completed = createExecutionStoreV3()
completed.applyEvent(event(1, { type: 'run.started' }))
completed.applyEvent(event(2, { item_kind: 'commentary', item_id: 'commentary_1', payload: { text: '我会先核对公开资料和内部知识库，再根据证据差异确定报告结构。' } }))
completed.applyEvent(event(3, { type: 'item.started', item_kind: 'activity', item_id: 'search_1', payload: { category: 'search', label: '查询内部知识库' } }))
completed.applyEvent(event(4, { item_kind: 'activity', item_id: 'search_1', revision: 2, payload: { category: 'search', label: '查询内部知识库' } }))
completed.applyEvent(event(5, { item_kind: 'final_answer', item_id: 'final', payload: { text: '完成' } }))
completed.applyEvent(event(6, { type: 'run.completed' }))

const running = createExecutionStoreV3()
running.applyEvent(event(7, { type: 'run.started' }))
running.applyEvent(event(8, { item_kind: 'commentary', item_id: 'commentary_1', payload: { text: '我会先确认客户信息，再写入对应的 CRM 档案。' } }))
running.applyEvent(event(9, { type: 'item.started', item_kind: 'activity', item_id: 'crm_1', payload: { category: 'tool', label: '更新客户系统' } }))

const failed = createExecutionStoreV3()
failed.applyEvent(event(11, { type: 'run.started' }))
failed.applyEvent(event(12, { type: 'item.failed', item_kind: 'error', item_id: 'error_1', payload: { message: '网络请求失败' } }))
failed.applyEvent(event(13, { type: 'run.failed', payload: { message: '网络请求失败' } }))

createApp({
  render: () => h('main', { style: 'max-width:720px;margin:40px auto;font-family:system-ui' }, [
    h('h1', 'Execution V3 组件验证'),
    h('h2', '运行态'), h(ExecutionViewV3, { store: running, live: true }),
    h('h2', '完成态'), h(ExecutionViewV3, { store: completed, live: false }),
    h('h2', '失败态'), h(ExecutionViewV3, { store: failed, live: false }),
  ]),
}).mount('#app')
