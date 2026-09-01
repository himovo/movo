<script setup lang="ts">
import { nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { Terminal } from '@xterm/xterm'
import { FitAddon } from '@xterm/addon-fit'
import '@xterm/xterm/css/xterm.css'
import { closeDshProjectTerminal, createDshProjectTerminal, onDshProjectTerminalEvent, resizeDshProjectTerminal, writeDshProjectTerminal } from '../../platform'

const props = defineProps<{ sessionId: string }>()
const host = ref<HTMLElement | null>(null)
let terminal: Terminal | null = null
let fit: FitAddon | null = null
let terminalId = ''
let observer: ResizeObserver | null = null
let disposeEvents = () => {}

onMounted(async () => {
  terminal = new Terminal({ cursorBlink: true, convertEol: true, fontSize: 12, fontFamily: 'SFMono-Regular, Menlo, Monaco, Consolas, monospace', theme: { background: '#0b1220', foreground: '#dbe5f2', cursor: '#93c5fd', selectionBackground: '#334155' } })
  fit = new FitAddon(); terminal.loadAddon(fit); terminal.open(host.value!); fit.fit()
  disposeEvents = onDshProjectTerminalEvent(event => {
    if (event.session_id !== props.sessionId || (terminalId && event.terminal_id !== terminalId)) return
    if (event.type === 'data' && event.data) terminal?.write(event.data)
    if (event.type === 'exit') terminal?.writeln(`\r\n[process exited ${event.exit_code ?? ''}]`)
  })
  const created = await createDshProjectTerminal(props.sessionId, terminal.cols, terminal.rows)
  terminalId = created.terminal_id
  terminal.onData(data => { if (terminalId) void writeDshProjectTerminal(terminalId, data) })
  observer = new ResizeObserver(() => {
    void nextTick(() => { fit?.fit(); if (terminalId && terminal) void resizeDshProjectTerminal(terminalId, terminal.cols, terminal.rows) })
  })
  observer.observe(host.value!)
  terminal.focus()
})

onBeforeUnmount(() => {
  observer?.disconnect(); disposeEvents(); terminal?.dispose()
  if (terminalId) void closeDshProjectTerminal(terminalId).catch(() => {})
})
</script>

<template><div ref="host" class="project-terminal" aria-label="Project terminal"></div></template>
<style scoped>.project-terminal{box-sizing:border-box;width:100%;height:100%;overflow:hidden;background:#0b1220;padding:8px}:deep(.xterm){height:100%}:deep(.xterm-viewport){border-radius:6px}</style>

