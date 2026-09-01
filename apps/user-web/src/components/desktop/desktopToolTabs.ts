export type DesktopToolTabKind = 'browser' | 'changes' | 'files' | 'terminal'

export interface DesktopToolTab {
  id: DesktopToolTabKind
  kind: DesktopToolTabKind
}

