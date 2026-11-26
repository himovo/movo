window.__ModuleLoader__.load({
  id: 'movo-plugin-page-status',
  factory(require) {
    const React = require('react')
    const messages = {
      en: { loading: 'Loading plugin page', failed: 'The plugin page could not be opened.', retry: 'Retry' },
      zh: { loading: '\u6b63\u5728\u52a0\u8f7d\u63d2\u4ef6\u9875\u9762', failed: '\u63d2\u4ef6\u9875\u9762\u672a\u80fd\u6253\u5f00\u3002', retry: '\u91cd\u8bd5' },
    }
    function Status({ failed = false }) {
      const locale = new URLSearchParams(location.search).get('locale') || document.documentElement.lang || navigator.language
      const text = messages[locale.startsWith('zh') ? 'zh' : 'en']
      return React.createElement('div', { role: failed ? 'alert' : 'status', style: { padding: 32, textAlign: 'center' } },
        React.createElement('p', null, text[failed ? 'failed' : 'loading']),
        failed ? React.createElement('button', { type: 'button', onClick: () => location.reload() }, text.retry) : null)
    }
    function Waiting() {
      const [expired, setExpired] = React.useState(false)
      React.useEffect(() => {
        const timer = setTimeout(() => setExpired(true), 20000)
        return () => clearTimeout(timer)
      }, [])
      return React.createElement(Status, { failed: expired })
    }
    class Boundary extends React.Component {
      state = { failed: false }
      static getDerivedStateFromError() { return { failed: true } }
      componentDidCatch(error) { console.error('Plugin page render failed', error) }
      render() { return this.state.failed ? React.createElement(Status, { failed: true }) : this.props.children }
    }
    return { Waiting, Boundary, Status }
  },
})
