import { defineComponent, h } from 'vue';

export const TrafficAllocationIcon = defineComponent({
  name: 'TrafficAllocationIcon',
  setup() {
    return () =>
      h(
        'svg',
        {
          xmlns: 'http://www.w3.org/2000/svg',
          viewBox: '0 0 512 512',
          fill: 'none',
        },
        [
          h('path', {
            d: 'M256 64C132.3 64 32 164.3 32 288c0 56.2 20.7 107.6 54.9 147h338.2A223.1 223.1 0 0 0 480 288C480 164.3 379.7 64 256 64Z',
            stroke: 'currentColor',
            'stroke-width': 36,
            'stroke-linejoin': 'round',
          }),
          h('path', {
            d: 'M256 128v48M128 288H80M432 288h-48M161.5 193.5l-34-34M350.5 193.5l34-34',
            stroke: 'currentColor',
            'stroke-width': 36,
            'stroke-linecap': 'round',
          }),
          h('path', {
            d: 'M256 320c-17.7 0-32-14.3-32-32 0-10.7 5.3-20.7 14.1-26.6L352 184l-77.4 113.9A31.9 31.9 0 0 1 256 320Z',
            fill: 'currentColor',
          }),
        ],
      );
  },
});
