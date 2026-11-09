<script setup lang="ts">
import { t } from '../composables/i18n'

defineProps<{
  desktop: boolean
  items: { icon: string; label: string }[]
  searchOpen: boolean
  loggedIn: boolean
  avatarUrl: string
  avatarText: string
  displayName: string
  accountTierLabel: string
}>()

const emit = defineEmits<{
  (event: 'action', icon: string): void
  (event: 'account'): void
  (event: 'login'): void
  (event: 'avatar-error', value: Event): void
}>()
</script>

<template>
  <aside class="app-sidebar w-[260px] bg-[#f8fafc] flex flex-col border-r border-gray-200 shadow-[1px_0_0_rgba(0,0,0,0.02)]">
    <div v-if="!desktop" class="flex h-14 items-center gap-2.5 px-5" aria-label="MOVO">
      <img src="/movo-logo.png" alt="" class="h-8 w-10 object-contain" />
      <span class="text-[15px] font-extrabold tracking-[0.14em] text-slate-800">MOVO</span>
    </div>
    <div class="sidebar-quick-actions flex items-center gap-1.5 px-3 pb-2 pt-2">
      <button
        v-for="item in items.filter(action => action.icon === 'plus')"
        :key="item.label"
        class="group flex min-h-10 min-w-0 flex-1 items-center gap-2 rounded-xl px-3 text-left text-sm font-medium text-gray-700 transition-all hover:bg-gray-200/60 active:scale-95"
        @click="emit('action', item.icon)"
      >
        <span class="text-gray-500 group-hover:text-gray-900 transition-colors">
          <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12h14m-7-7v14"/></svg>
        </span>
        <span class="truncate">{{ item.label }}</span>
      </button>
      <button
        v-for="item in items.filter(action => action.icon !== 'plus')"
        :key="item.label"
        class="group flex h-10 w-10 shrink-0 items-center justify-center rounded-xl text-gray-600 transition-all hover:bg-gray-200/60 active:scale-95"
        :class="item.icon === 'search' && searchOpen ? 'border border-gray-200 bg-white text-blue-700 shadow-sm' : ''"
        :title="item.label"
        :aria-label="item.label"
        @click="emit('action', item.icon)"
      >
        <svg v-if="item.icon === 'clock'" xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/></svg>
        <svg v-else-if="item.icon === 'search'" xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/></svg>
      </button>
    </div>

    <slot name="history" />
    <slot name="features" />

    <div :class="desktop ? 'desktop-account-menu-host' : 'p-4 border-t border-gray-200 bg-white/50'" data-user-menu>
      <div
        v-if="!desktop && loggedIn"
        class="flex items-center gap-3 p-2 rounded-xl hover:bg-gray-200/70 cursor-pointer transition-colors"
        @click.stop="emit('account')"
      >
        <div class="w-9 h-9 rounded-xl overflow-hidden bg-gradient-to-br from-blue-500 to-indigo-600 flex items-center justify-center text-white font-bold shadow-sm">
          <img v-if="avatarUrl" :src="avatarUrl" alt="" class="w-full h-full object-cover" @error="emit('avatar-error', $event)" />
          <span v-else>{{ avatarText }}</span>
        </div>
        <div class="flex-1 min-w-0">
          <div class="text-xs font-semibold text-gray-900 truncate">{{ displayName }}</div>
          <div class="text-[10px] text-gray-400 font-medium">{{ accountTierLabel }}</div>
        </div>
        <svg class="w-3 h-3 text-gray-400 shrink-0" xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m6 9 6 6 6-6"/></svg>
      </div>
      <div v-else-if="!desktop" class="flex items-center gap-3 p-2 rounded-xl hover:bg-gray-200/70 cursor-pointer transition-colors" @click="emit('login')">
        <div class="w-9 h-9 rounded-xl bg-gray-200 flex items-center justify-center text-gray-400 font-bold border border-gray-300 border-dashed">?</div>
        <div class="text-sm font-semibold text-gray-700">{{ t('app.sidebar.login_register') }}</div>
      </div>
      <slot name="account-menu" />
    </div>
  </aside>
</template>
