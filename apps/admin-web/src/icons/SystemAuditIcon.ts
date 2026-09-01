import { defineComponent, h } from 'vue';

export const SystemAuditIcon = defineComponent({
  name: 'SystemAuditIcon',
  setup() {
    return () => h('svg', {
      xmlns: 'http://www.w3.org/2000/svg', viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor',
      'stroke-width': '2', 'stroke-linecap': 'round', 'stroke-linejoin': 'round',
    }, [
      h('path', { d: 'M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z' }),
      h('path', { d: 'm9 12 2 2 4-4' }),
    ]);
  },
});
