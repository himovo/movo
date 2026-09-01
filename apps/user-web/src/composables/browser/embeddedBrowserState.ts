import { readonly, shallowRef, type DeepReadonly, type Ref } from 'vue'
import { capabilities, getEmbeddedBrowserState, onEmbeddedBrowserState, type EmbeddedBrowserState } from '../../platform'

const state = shallowRef<EmbeddedBrowserState>({
  session_id: '',
  active: false,
  visible: false,
  purpose: 'automation',
  owner: 'agent',
  url: '',
  title: '',
  loading: false,
  canGoBack: false,
  canGoForward: false,
  controllable: false,
  active_tab_id: '',
  tabs: [],
})
let initialized = false
let eventVersion = 0

export function useEmbeddedBrowserState(): Readonly<Ref<DeepReadonly<EmbeddedBrowserState>>> {
  if (!initialized && capabilities.embeddedBrowser) {
    initialized = true
    onEmbeddedBrowserState((value) => {
      eventVersion += 1
      state.value = value
    })
    const snapshotVersion = eventVersion
    void getEmbeddedBrowserState().then((value) => {
      if (eventVersion === snapshotVersion) state.value = value
    })
  }
  return readonly(state)
}
