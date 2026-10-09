export interface ComposerFocusEnvironment {
  activeElement: Element | null
  documentVisible: boolean
  hasBlockingOverlay: boolean
  hasTextSelection: boolean
  mobileDevice: boolean
}

export function isEditableElement(element: Element | null): boolean {
  if (!(element instanceof HTMLElement)) return false
  return element.isContentEditable || element.matches('input, textarea, select')
}

export function shouldAutofocusComposer(
  input: HTMLTextAreaElement,
  enabled: boolean,
  environment: ComposerFocusEnvironment,
  replaceCurrentFocus = false,
): boolean {
  if (!enabled || input.disabled || input.readOnly || environment.mobileDevice) return false
  if (!environment.documentVisible || environment.hasBlockingOverlay || environment.hasTextSelection) return false

  const active = environment.activeElement
  if (!active || active === input) return true
  if (active === document.body || active === document.documentElement) return true

  // Completing an explicit chat navigation (new chat or switching sessions)
  // should move focus from the navigation control to the destination composer.
  if (replaceCurrentFocus) return true

  // A hidden pane may still own focus while the user switches conversations.
  // In that one case, handing focus to the newly active composer is expected.
  if (active instanceof HTMLElement && active.dataset.chatComposerInput === 'true') return true

  // Never pull focus away from search, dialogs, menus, buttons, links, or
  // another editable control that the user deliberately selected.
  return false
}
