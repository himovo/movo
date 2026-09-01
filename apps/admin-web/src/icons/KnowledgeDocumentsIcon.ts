import { defineComponent, h } from 'vue';

export const KnowledgeDocumentsIcon = defineComponent({
  name: 'KnowledgeDocumentsIcon',
  setup() {
    return () =>
      h(
        'svg',
        {
          xmlns: 'http://www.w3.org/2000/svg',
          viewBox: '0 0 24 24',
          fill: 'none',
          stroke: 'currentColor',
          'stroke-width': '2',
          'stroke-linecap': 'round',
          'stroke-linejoin': 'round',
        },
        [
          h('path', { d: 'M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z' }),
          h('path', { d: 'M14 2v6h6' }),
          h('path', { d: 'M16 13H8' }),
          h('path', { d: 'M16 17H8' }),
          h('path', { d: 'M10 9H8' }),
        ],
      );
  },
});
