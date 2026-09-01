import { ref, computed } from 'vue';

export type ThemeMode = 'light' | 'dark' | 'system';
const STORAGE_KEY = 'askai-admin-theme';

function getSystemThemePreference(): 'light' | 'dark' {
  if (typeof window === 'undefined') return 'light';
  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
}

const storedTheme = localStorage.getItem(STORAGE_KEY) as ThemeMode | null;
const _theme = ref<ThemeMode>(
  storedTheme === 'dark' || storedTheme === 'light' || storedTheme === 'system'
    ? storedTheme
    : 'system' // 默认跟随系统
);

const activeThemeMode = ref<'light' | 'dark'>('light');

function updateActiveTheme() {
  if (_theme.value === 'system') {
    activeThemeMode.value = getSystemThemePreference();
  } else {
    activeThemeMode.value = _theme.value;
  }
  syncHtmlClass(activeThemeMode.value);
}

function syncHtmlClass(mode: 'light' | 'dark') {
  if (typeof document !== 'undefined') {
    if (mode === 'dark') {
      document.documentElement.classList.add('dark');
      document.documentElement.setAttribute('data-theme', 'dark');
    } else {
      document.documentElement.classList.remove('dark');
      document.documentElement.setAttribute('data-theme', 'light');
    }
  }
}

let mediaQuery: MediaQueryList | null = null;
const handleSystemThemeChange = () => {
  if (_theme.value === 'system') {
    updateActiveTheme();
  }
};

if (typeof window !== 'undefined') {
  mediaQuery = window.matchMedia('(prefers-color-scheme: dark)');
  if (mediaQuery.addEventListener) {
    mediaQuery.addEventListener('change', handleSystemThemeChange);
  } else {
    mediaQuery.addListener(handleSystemThemeChange);
  }
}

// 首次初始化
updateActiveTheme();

export function useTheme() {
  return {
    theme: computed(() => _theme.value),
    activeTheme: computed(() => activeThemeMode.value),
    setTheme(mode: ThemeMode) {
      _theme.value = mode;
      localStorage.setItem(STORAGE_KEY, mode);
      updateActiveTheme();
    },
  };
}
