window.__ModuleLoader__.load({
  id: 'movo-plugin-conversation-shell',
  factory(require) {
    const React = require('react')
    const locales = require('movo-plugin-conversation-locales')
    function ViewBody({ renderSlot, id, onSelect }) {
      return renderSlot('conversation.view', {
        inspectCall: undefined,
        viewRequest: null,
        openView: view => onSelect(view),
        completeViewRequest: () => {},
      }, { only: id })
    }
    function LegacyViewProbe({ ctx }) {
      const version = React.useSyncExternalStore(
        React.useCallback(notify => ctx.slots.subscribe('conversation.view', notify), []),
        React.useCallback(() => ctx.slots.getVersion('conversation.view'), []),
      )
      const entries = ctx.slots.entriesOfSlot('conversation.view')
        .filter(entry => entry.options?.id && entry.options.id !== 'chat')
      React.useEffect(() => {
        const timer = setTimeout(() => window.parent.postMessage({
          type: 'movo:conversation-view-probe', count: entries.length,
        }, '*'), 700)
        return () => clearTimeout(timer)
      }, [version])
      return null
    }
    return {
      render(ctx, SessionProvider, renderSlot) {
        const params = new URLSearchParams(window.location.search)
        if (params.get('probe') === 'conversation-view') {
          return React.createElement(LegacyViewProbe, { ctx })
        }
        const sessionId = params.get('session')
        const english = params.get('locale') === 'en'
        const labels = english ? locales.en : locales.zh
        const [reference, setReference] = React.useState(null)
        const [failed, setFailed] = React.useState(false)
        const [selected, setSelected] = React.useState(null)
        React.useEffect(() => {
          ctx.sessions.refresh().catch(() => setFailed(true))
        }, [])
        const catalog = React.useSyncExternalStore(
          React.useCallback(notify => ctx.sessions.list.subscribe(notify), []),
          React.useCallback(() => ctx.sessions.list.getSnapshot(), []),
        )
        React.useEffect(() => {
          if (!sessionId || !ctx.sessions) { setFailed(true); return }
          if (!catalog.byId[sessionId]) {
            if (catalog.phase === 'ready') setFailed(true)
            return
          }
          let live = true
          let retained
          try { retained = ctx.sessions.retain(sessionId, { source: 'mainView' }) }
          catch { setFailed(true); return }
          retained.ready.then(() => {
            if (live) { setFailed(false); setReference(retained) }
          }, () => { if (live) setFailed(true) })
          return () => { live = false; retained.release() }
        }, [sessionId, Boolean(catalog.byId[sessionId]), catalog.phase])
        React.useSyncExternalStore(
          React.useCallback(notify => ctx.slots.subscribe('conversation.view', notify), []),
          React.useCallback(() => ctx.slots.getVersion('conversation.view'), []),
        )
        const entries = ctx.slots.entriesOfSlot('conversation.view')
          .filter(entry => entry.options?.id && entry.options.id !== 'chat')
          .sort((left, right) => (left.options.order ?? 0) - (right.options.order ?? 0))
        const id = entries.some(entry => entry.options.id === selected)
          ? selected : entries[0]?.options.id
        const body = failed ? labels.failed : !reference ? labels.loading : !id ? labels.empty : null
        return React.createElement('main', {
          style: { height: '100vh', display: 'flex', flexDirection: 'column', background: '#fff' },
        },
        entries.length > 1 ? React.createElement('nav', {
          role: 'tablist',
          style: { display: 'flex', gap: 4, padding: '8px 16px', borderBottom: '1px solid #e5e7eb', background: '#fff' },
        }, entries.map(entry => React.createElement('button', {
          key: entry.options.id, type: 'button', onClick: () => setSelected(entry.options.id),
          role: 'tab',
          'aria-selected': id === entry.options.id,
          style: {
            border: 0,
            borderRadius: 8,
            padding: '7px 12px',
            background: id === entry.options.id ? '#eaf1ff' : 'transparent',
            color: id === entry.options.id ? '#2563eb' : '#475569',
            fontSize: 13,
            fontWeight: id === entry.options.id ? 600 : 500,
            cursor: 'pointer',
          },
        }, typeof entry.options.label === 'function' ? entry.options.label() : entry.options.id))) : null,
        body ? React.createElement('div', { style: { padding: 24, color: '#64748b' } }, body)
          : React.createElement(SessionProvider, { session: reference },
            React.createElement('div', { style: { flex: 1, minHeight: 0, overflow: 'auto' } },
              React.createElement(ViewBody, { renderSlot, id, onSelect: setSelected }))))
      },
    }
  },
})
