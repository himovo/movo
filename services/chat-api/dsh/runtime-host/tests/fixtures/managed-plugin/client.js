window.__ModuleLoader__.load({
  id: 'movo-dsh-test-bundle',
  factory(require) {
    const React = require('react')
    return {
      inject: ['slots'],
      apply(ctx) {
        ctx.slots.inject('main', () => ctx.slots.register(
          { name: 'main', key: 'movo-fixture' },
          () => {
            const [result, setResult] = React.useState('')
            return React.createElement('div', { id: 'movo-fixture-page' },
              React.createElement('button', {
                type: 'button',
                onClick: async () => {
                  const response = await fetch('/movo-fixture/ready')
                  setResult((await response.json()).marker)
                },
              }, 'Run fixture action'),
              React.createElement('output', {}, result),
            )
          },
        ))
      },
    }
  },
})
