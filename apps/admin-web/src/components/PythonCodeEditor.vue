<template>
  <div ref="editorHost" class="python-code-editor" />
</template>

<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue';
import { EditorState } from '@codemirror/state';
import { indentWithTab } from '@codemirror/commands';
import { keymap, placeholder as editorPlaceholder } from '@codemirror/view';
import { EditorView, basicSetup } from 'codemirror';
import { python } from '@codemirror/lang-python';

const props = withDefaults(defineProps<{
  modelValue?: string;
  placeholder?: string;
}>(), {
  modelValue: '',
  placeholder: '',
});

const emit = defineEmits<{
  (event: 'update:modelValue', value: string): void;
}>();

const editorHost = ref<HTMLElement | null>(null);
let editorView: EditorView | null = null;
let syncingFromEditor = false;

const editorTheme = EditorView.theme({
  '&': {
    height: '100%',
    backgroundColor: '#0f172a',
    color: '#e2e8f0',
    fontSize: '13px',
  },
  '&.cm-focused': {
    outline: '2px solid #4f8cff',
    outlineOffset: '-2px',
  },
  '.cm-scroller': {
    overflow: 'auto',
    fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace',
    lineHeight: '1.65',
  },
  '.cm-content': {
    minHeight: '100%',
    padding: '12px 0',
    caretColor: '#93c5fd',
  },
  '.cm-line': {
    padding: '0 16px',
  },
  '.cm-gutters': {
    minWidth: '48px',
    borderRight: '1px solid #26344f',
    backgroundColor: '#111c31',
    color: '#70809d',
  },
  '.cm-lineNumbers .cm-gutterElement': {
    minWidth: '38px',
    padding: '0 10px 0 6px',
  },
  '.cm-activeLine': {
    backgroundColor: '#17233b',
  },
  '.cm-activeLineGutter': {
    backgroundColor: '#1d2c49',
    color: '#bfdbfe',
  },
  '.cm-selectionBackground, ::selection': {
    backgroundColor: '#29446f !important',
  },
  '.cm-cursor': {
    borderLeftColor: '#93c5fd',
  },
  '.cm-searchMatch': {
    backgroundColor: '#725c16',
  },
  '.cm-searchMatch.cm-searchMatch-selected': {
    backgroundColor: '#8b6f19',
  },
  '.cm-tooltip, .cm-panels': {
    backgroundColor: '#17233b',
    color: '#e2e8f0',
  },
  '.cm-panels': {
    borderColor: '#334155',
  },
}, { dark: true });

onMounted(() => {
  if (!editorHost.value) return;
  editorView = new EditorView({
    parent: editorHost.value,
    state: EditorState.create({
      doc: props.modelValue || '',
      extensions: [
        basicSetup,
        python(),
        keymap.of([indentWithTab]),
        EditorState.tabSize.of(4),
        editorTheme,
        editorPlaceholder(props.placeholder),
        EditorView.updateListener.of((update) => {
          if (!update.docChanged) return;
          syncingFromEditor = true;
          emit('update:modelValue', update.state.doc.toString());
          queueMicrotask(() => {
            syncingFromEditor = false;
          });
        }),
      ],
    }),
  });
});

watch(() => props.modelValue, (value) => {
  if (!editorView || syncingFromEditor) return;
  const nextValue = value || '';
  const currentValue = editorView.state.doc.toString();
  if (currentValue === nextValue) return;
  editorView.dispatch({
    changes: { from: 0, to: currentValue.length, insert: nextValue },
  });
});

onBeforeUnmount(() => {
  editorView?.destroy();
  editorView = null;
});
</script>

<style scoped>
.python-code-editor {
  width: 100%;
  height: 100%;
  min-height: 0;
  overflow: hidden;
  background: #0f172a;
}
</style>
