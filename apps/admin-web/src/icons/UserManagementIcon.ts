import { defineComponent, h } from 'vue';

export const UserManagementIcon = defineComponent({
  name: 'UserManagementIcon',
  setup() {
    return () =>
      h(
        'svg',
        {
          xmlns: 'http://www.w3.org/2000/svg',
          viewBox: '0 0 24 24',
          fill: 'none',
        },
        [
          h(
            'g',
            {
              fill: 'none',
              stroke: 'currentColor',
              'stroke-width': '2',
              'stroke-linecap': 'round',
              'stroke-linejoin': 'round',
            },
            [
              h('circle', {
                cx: '12',
                cy: '7',
                r: '4',
              }),
              h('path', {
                d: 'M6 21v-2a4 4 0 0 1 4-4h4a4 4 0 0 1 4 4v2',
              }),
            ],
          ),
        ],
      );
  },
});
