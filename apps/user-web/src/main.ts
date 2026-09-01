import { createApp } from 'vue'
import App from './App.vue'
import './style.css'

const storedThemeMode = localStorage.getItem('askai.theme-mode') || 'system'
const startsDark = storedThemeMode === 'dark'
  || (storedThemeMode === 'system' && window.matchMedia('(prefers-color-scheme: dark)').matches)
document.documentElement.classList.toggle('theme-dark', startsDark)
document.documentElement.style.colorScheme = startsDark ? 'dark' : 'light'

createApp(App).mount('#app')
