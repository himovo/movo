window.__ModuleLoader__.load({
  id: 'movo-plugin-client-shell',
  factory(require) {
    const React = require('react')
    const { Service } = require('@deepseek-ai/cordis')
    const conversation = require('movo-plugin-conversation-shell')
    return {
      inject: ['slots', 'sessions'],
      apply(ctx) {
        const conversationMode = new URLSearchParams(window.location.search).get('surface') === 'conversation'
        class PluginWorkspaceNavigation extends Service {
          constructor() { super(ctx, 'uiWorkspace') }
          openSession(sessionId) {
            if (typeof sessionId !== 'string' || !sessionId) return
            window.dispatchEvent(new CustomEvent('movo:plugin-open-session', { detail: { sessionId } }))
            if (window.parent !== window) {
              window.parent.postMessage({ type: 'movo:plugin-open-session', sessionId }, '*')
            }
          }
        }
        new PluginWorkspaceNavigation()
        ctx.slots.register({
          name: 'root',
          children: conversationMode
            ? { 'conversation.view': { kind: 'list', scope: 'session' } }
            : { main: { kind: 'keyed', scope: 'root' },
                'sidebar.panellist': { kind: 'list', scope: 'root' } },
        }, ({ renderSlot, SessionProvider }) => {
          if (conversationMode) {
            return conversation.render(ctx, SessionProvider, renderSlot)
          }
          React.useSyncExternalStore(
            React.useCallback(notify => ctx.slots.subscribe('main', notify), []),
            React.useCallback(() => ctx.slots.getVersion('main'), []),
          )
          const entries = ctx.slots.entries('main')
          const initial = new URLSearchParams(window.location.search).get('panel')
          const [active, setActive] = React.useState(initial)
          const keys = entries.filter(entry => entry.registrant === window.__MOVO_PLUGIN_MODULE__)
            .map(entry => entry.options.key).filter(Boolean)
          const key = keys.includes(active) ? active : keys[0]
          return React.createElement('main', {
            style: { width: '100%', height: '100vh', overflow: 'hidden', background: '#fff' },
          },
          keys.length > 1 ? React.createElement('nav', {
            style: { display: 'flex', gap: 8, padding: 12, borderBottom: '1px solid #e5e7eb' },
          }, keys.map(panel => React.createElement('button', {
            key: panel,
            type: 'button',
            onClick: () => setActive(panel),
            'aria-current': panel === key ? 'page' : undefined,
            style: { border: 0, padding: '8px 12px', cursor: 'pointer', background: panel === key ? '#eaf1ff' : 'transparent' },
          }, panel))) : null,
          key ? renderSlot('main', {}, { entryKey: key }) : null)
        })
      },
    }
  },
})
