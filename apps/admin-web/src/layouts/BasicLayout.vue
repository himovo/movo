<template>
  <n-layout class="app-shell has-background" has-sider position="absolute">
    <n-layout-sider
      bordered
      :collapsed="collapsed"
      collapse-mode="width"
      :collapsed-width="64"
      :width="180"
      class="shell-sider"
      content-style="padding: 16px 8px 14px;"
      style="backdrop-filter: blur(16px);"
    >
      <div class="brand-block" :class="{ compact: collapsed }">
        <img class="brand-logo" :src="movoLogo" alt="MOVO" />
        <span v-if="!collapsed" class="brand-name">MOVO</span>
      </div>
      <n-menu
        :collapsed="collapsed"
        :collapsed-width="48"
        :collapsed-icon-size="18"
        :indent="16"
        :options="menuOptions"
        :expanded-keys="expandedKeys"
        :value="selectedKey"
        @update:value="handleUpdate"
        @update:expanded-keys="handleExpandedKeysUpdate"
      />
      <div class="sider-footer">
        <n-button tertiary circle @click="toggleSidebar">
          {{ collapsed ? '»' : '«' }}
        </n-button>
      </div>
    </n-layout-sider>

    <n-layout>
      <n-layout-header bordered class="shell-header">
        <div class="header-left">
          <n-button
            v-if="showBackButton"
            quaternary
            class="header-back-pill"
            :title="backButtonTitle"
            :aria-label="backButtonTitle"
            @click="handleBack"
          >
            <span class="header-back-icon" aria-hidden="true">
              <svg
                xmlns="http://www.w3.org/2000/svg"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                stroke-width="2"
                stroke-linecap="round"
                stroke-linejoin="round"
              >
                <path d="M19 12H5" />
                <path d="m12 19-7-7 7-7" />
              </svg>
            </span>
            <span>{{ backButtonText }}</span>
          </n-button>
          <div class="header-title-row">
            <div class="header-title">{{ currentRouteTitle }}</div>
            <span v-if="dynamicRouteTag" class="header-type-tag">{{ dynamicRouteTag }}</span>
            <div id="header-title-teleport-target" class="header-title-teleport"></div>
          </div>
        </div>
        <n-space align="center" :size="12">
          <div id="header-actions-teleport-target" class="header-actions-teleport"></div>
          <n-dropdown trigger="hover" :options="languageOptions" @select="handleLanguageSelect">
            <n-button quaternary circle class="header-round-button" :title="`${t('语言')}: ${currentLanguageLabel}`">
              <span class="header-icon" aria-hidden="true">
                <svg
                  xmlns="http://www.w3.org/2000/svg"
                  width="24"
                  height="24"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  stroke-width="2"
                  stroke-linecap="round"
                  stroke-linejoin="round"
                >
                  <path d="m5 8 6 6" />
                  <path d="m4 14 6-6 2-3" />
                  <path d="M2 5h12" />
                  <path d="M7 2h1" />
                  <path d="m22 22-5-10-5 10" />
                  <path d="M14 18h6" />
                </svg>
              </span>
            </n-button>
          </n-dropdown>
          <!-- <n-dropdown trigger="hover" :options="noticeOptions" @select="handleNoticeSelect">
            <n-badge :value="3" :max="99" class="notice-badge">
              <n-button quaternary circle class="header-round-button" :title="t('系统通知')">
                <span class="header-icon" aria-hidden="true">
                  <svg
                    data-v-798ba459=""
                    xmlns="http://www.w3.org/2000/svg"
                    width="24"
                    height="24"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    stroke-width="2"
                    stroke-linecap="round"
                    stroke-linejoin="round"
                  >
                    <path d="M10.268 21a2 2 0 0 0 3.464 0" />
                    <path
                      d="M3.262 15.326A1 1 0 0 0 4 17h16a1 1 0 0 0 .74-1.673C19.41 13.956 18 12.499 18 8A6 6 0 0 0 6 8c0 4.499-1.411 5.956-2.738 7.326"
                    />
                  </svg>
                </span>
              </n-button>
            </n-badge>
          </n-dropdown> -->
          <n-dropdown trigger="hover" :options="profileOptions" @select="handleSelect">
            <div class="profile-trigger">
              <span class="header-avatar" :class="{ 'has-image': showProfileAvatar }">
                <img v-if="showProfileAvatar" :key="profileAvatarUrl" :src="profileAvatarUrl" alt="" @error="handleProfileAvatarError" />
                <span v-else>{{ profileInitial }}</span>
              </span>
              <span class="profile-text">
                {{ profileDisplayName }}
              </span>
            </div>
          </n-dropdown>
        </n-space>
      </n-layout-header>

      <n-layout-content>
        <router-view />
      </n-layout-content>
    </n-layout>
  </n-layout>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue';
import { useMessage } from 'naive-ui';
import { useRoute, useRouter } from 'vue-router';
import { appRoutes } from '@/router/routes';
import { useMenuOptions } from '@/composables/useMenuOptions';
import { useAuthStore } from '@/stores/auth';
import movoLogo from '@/assets/images/movo-logo.png';
import { resolveAdminAssetUrlWithVersion } from '@/composables/adminAsset';
import { isLocale, useLocale, t } from '@/composables/i18n';
import { displayAdminName, isMobileLike } from '@/composables/privacy';

const router = useRouter();
const route = useRoute();
const message = useMessage();
const authStore = useAuthStore();
const collapsed = ref(false);
const dynamicRouteTitle = ref('');
const dynamicRouteTag = ref('');
const { menuOptions, selectedKey, expandedKeys, handleUpdate, handleExpandedKeysUpdate } = useMenuOptions();
const { locale: currentLanguage, setLocale } = useLocale();

const routeTitleMap = new Map<string, string>();
const rootRoute = appRoutes.find((item) => item.path === '/');
for (const child of rootRoute?.children ?? []) {
  if (typeof child.path !== 'string' || !child.path) {
    continue;
  }
  routeTitleMap.set(child.path, (child.meta?.title as string) || child.path);
}

const currentRouteTitle = computed(() => {
  if (dynamicRouteTitle.value) {
    return t(dynamicRouteTitle.value);
  }
  const metaTitle = route.meta?.title;
  if (typeof metaTitle === 'string' && metaTitle) {
    return t(metaTitle);
  }
  return routeTitleMap.get(route.path) ? t(routeTitleMap.get(route.path)!) : 'MOVO Admin';
});
const isToolEditPage = computed(() => route.path === '/tools/new' || route.name === 'ToolEdit');
const isSkillConfigPage = computed(() => route.name === 'SkillConfig');
const showBackButton = computed(() => isToolEditPage.value || isSkillConfigPage.value);
const backButtonText = computed(() => t('返回'));
const backButtonTitle = computed(() => (isSkillConfigPage.value ? t('返回 Skill 列表') : t('返回工具列表')));
const profileDisplayName = computed(() => displayAdminName(authStore.profile, t('管理员')));
const profileAvatarUrl = computed(() => resolveAdminAssetUrlWithVersion(authStore.profile?.avatarUrl, authStore.profile?.avatarUpdatedAt));
const profileAvatarFailedUrl = ref('');
const showProfileAvatar = computed(() => Boolean(profileAvatarUrl.value) && profileAvatarFailedUrl.value !== profileAvatarUrl.value);
const profileInitial = computed(() => (isMobileLike(profileDisplayName.value) || profileDisplayName.value.includes('****') ? '管' : profileDisplayName.value.slice(0, 1).toUpperCase()));
const currentLanguageLabel = computed(() =>
  currentLanguage.value === 'en-US' ? 'English' : '简体中文',
);

const profileOptions = computed(() => [
  {
    label: t('个人中心'),
    key: 'profile',
  },
  {
    label: t('退出登录'),
    key: 'logout',
  },
]);

const languageOptions = [
  { label: '简体中文', key: 'zh-CN' },
  { label: 'English', key: 'en-US' },
];

const noticeOptions = computed(() => [
  { label: t('系统升级窗口将于今晚 23:00 开始'), key: 'notice-1' },
  { label: t('模型配置变更待审批: 2 条'), key: 'notice-2' },
  { label: t('今日活跃组织数较昨日提升 12%'), key: 'notice-3' },
]);

function toggleSidebar() {
  collapsed.value = !collapsed.value;
}

function backToTools() {
  router.push('/tools');
}

function backToSkills() {
  router.push('/skills');
}

function handleBack() {
  if (isSkillConfigPage.value) {
    backToSkills();
    return;
  }
  backToTools();
}

function handleLanguageSelect(key: string) {
  if (!isLocale(key)) return;
  setLocale(key);
  message.success(key === 'en-US' ? 'Language switched to English' : '语言已切换为简体中文');
}

function handleNoticeSelect() {
  message.info(t('通知详情页待接入'));
}

function handleProfileAvatarError() {
  profileAvatarFailedUrl.value = profileAvatarUrl.value;
}

function handleRouteTitleChange(event: Event) {
  const detail = (event as CustomEvent<{ routeName?: string; title?: string; tag?: string }>).detail;
  if (detail?.routeName && detail.routeName !== String(route.name || '')) {
    return;
  }
  dynamicRouteTitle.value = detail?.title || '';
  dynamicRouteTag.value = detail?.tag || '';
}

watch(
  () => route.fullPath,
  () => {
    dynamicRouteTitle.value = '';
    dynamicRouteTag.value = '';
  },
);

onMounted(() => {
  window.addEventListener('askai-admin-title-change', handleRouteTitleChange);
});

onUnmounted(() => {
  window.removeEventListener('askai-admin-title-change', handleRouteTitleChange);
});

async function handleSelect(key: string) {
  if (key === 'profile') {
    router.push('/profile');
    return;
  }
  if (key === 'logout') {
    await authStore.logout();
    router.push('/login');
  }
}


</script>

<style scoped>
.brand-block {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  padding: 8px 6px 18px;
}

.shell-sider {
  position: relative;
  background: rgba(255, 255, 255, 0.8) !important;
}

html.dark .shell-sider {
  background: rgba(17, 24, 39, 0.86) !important;
  border-color: #263044 !important;
}

.brand-block.compact {
  justify-content: center;
  padding-left: 0;
  padding-right: 0;
}

.brand-logo {
  display: block;
  width: 38px;
  height: 38px;
  object-fit: contain;
  flex-shrink: 0;
}

.brand-block.compact .brand-logo {
  width: 36px;
  height: 36px;
}

.brand-name {
  color: #14213d;
  font-size: 20px;
  font-weight: 800;
  letter-spacing: 0.12em;
}

html.dark .brand-name {
  color: #f8fafc;
}

.sider-footer {
  position: absolute;
  left: 0;
  right: 0;
  bottom: 14px;
  display: flex;
  justify-content: center;
  padding: 0;
}

:deep(.n-menu-item-content-header) {
  font-size: 14px;
}

:deep(.menu-symbol) {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  font-size: 18px;
  font-weight: 700;
  line-height: 1;
}

:deep(.menu-symbol svg) {
  width: 18px;
  height: 18px;
}

:deep(.n-menu:not(.n-menu--collapsed) .n-menu-item-content) {
  padding-right: 12px !important;
}

:deep(.n-menu:not(.n-menu--collapsed) .n-menu-item--child .n-menu-item-content) {
  padding-left: 16px !important;
}

:deep(.n-menu.n-menu--collapsed .n-menu-item-content__icon) {
  flex: 0 0 auto !important;
  display: flex;
  justify-content: center;
  align-items: center;
}

:deep(.n-menu.n-menu--collapsed .menu-symbol) {
  width: 20px !important;
  justify-content: center;
}

:deep(.n-menu.n-menu--collapsed .n-submenu .n-menu-item-content__arrow) {
  display: none !important;
}

:deep(.n-menu.n-menu--collapsed .n-menu-item-content-header) {
  display: none !important;
}

.shell-header {
  position: relative;
  z-index: 10;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 15px 24px;
  background: rgba(255, 255, 255, 0.72);
  backdrop-filter: blur(16px);
  box-shadow:
    0 8px 24px rgba(23, 53, 118, 0.08),
    0 1px 0 rgba(255, 255, 255, 0.8) inset;
}

html.dark .shell-header {
  background: rgba(17, 24, 39, 0.78);
  box-shadow:
    0 8px 24px rgba(0, 0, 0, 0.28),
    0 1px 0 rgba(255, 255, 255, 0.06) inset;
}

.shell-header::after {
  content: '';
  position: absolute;
  left: 0;
  right: 0;
  bottom: -1px;
  height: 1px;
  background: linear-gradient(90deg, rgba(110, 145, 235, 0.2), rgba(110, 145, 235, 0.55), rgba(110, 145, 235, 0.2));
  pointer-events: none;
}

html.dark .shell-header::after {
  background: linear-gradient(90deg, rgba(37, 99, 235, 0.1), rgba(96, 165, 250, 0.38), rgba(37, 99, 235, 0.1));
}

.header-left {
  display: flex;
  align-items: center;
  gap: 12px;
}

.header-back-pill {
  height: 32px;
  padding: 0 12px !important;
  border-radius: 999px;
  border: 1px solid #d7e2f5;
  background: #f7faff;
  color: #3558a8;
  font-weight: 600;
}

.header-back-pill:hover {
  border-color: #b7c9ee;
  background: #eef4ff;
}

html.dark .header-back-pill {
  border-color: #334155;
  background: #111827;
  color: #bfdbfe;
}

html.dark .header-back-pill:hover {
  border-color: #3b82f6;
  background: #172033;
}

.header-back-icon {
  width: 16px;
  height: 16px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  margin-right: 6px;
}

.header-back-icon svg {
  width: 16px;
  height: 16px;
}

.header-title {
  font-size: 16px;
  font-weight: 800;
  color: #12234b;
}

html.dark .header-title {
  color: #f8fafc;
}

.header-title-row {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}

.header-type-tag {
  display: inline-flex;
  align-items: center;
  height: 24px;
  border-radius: 6px;
  background: #fff2dd;
  color: #d97706;
  font-size: 13px;
  font-weight: 700;
  line-height: 1;
  padding: 0 10px;
  white-space: nowrap;
}

html.dark .header-type-tag {
  background: rgba(217, 119, 6, 0.18);
  color: #fbbf24;
}

.header-subtitle {
  color: #5f736d;
  font-size: 12px;
  margin-top: 1px;
}

html.dark .header-subtitle {
  color: #9ca3af;
}

.header-round-button {
  font-size: 14px;
}

.header-icon {
  width: 16px;
  height: 16px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}

.header-icon svg {
  width: 16px;
  height: 16px;
}

:deep(.notice-badge .n-badge-sup) {
  min-width: 14px;
  height: 14px;
  line-height: 14px;
  font-size: 10px;
  padding: 0 4px;
  top: 3px !important;
  right: 3px !important;
  transform: translate(-84%, -15%) !important;
}

.profile-trigger {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 4px 8px;
  border-radius: 999px;
  cursor: pointer;
  transition: background-color 0.2s ease;
}

.profile-trigger:hover {
  background: rgba(54, 106, 255, 0.09);
}

.header-avatar {
  display: inline-grid;
  place-items: center;
  width: 28px;
  height: 28px;
  flex: 0 0 28px;
  overflow: hidden;
  border-radius: 50%;
  background: #366aff;
  color: #fff;
  font-size: 14px;
  font-weight: 700;
  line-height: 1;
}

.header-avatar img {
  display: block;
  width: 100%;
  height: 100%;
  object-fit: cover;
}

html.dark .profile-trigger:hover {
  background: rgba(96, 165, 250, 0.14);
}

.profile-text {
  font-size: 13px;
  color: #1b2c52;
}

html.dark .profile-text {
  color: #e5e7eb;
}

.shell-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 24px;
  color: #5f736d;
  font-size: 12px;
  background: rgba(255,255,255,0.64);
}

:deep(.n-layout.n-layout--static-positioned),
:deep(.n-layout.n-layout--static-positioned > .n-layout-scroll-container) {
  overflow: hidden !important;
}

/* ==================== 暗色模式框架自适应适配 ==================== */
html.dark .app-shell {
  background-color: #101014 !important;
}

html.dark :deep(.n-layout) {
  --n-color: #101014 !important;
}

html.dark :deep(.n-layout-scroll-container) {
  background-color: #101014 !important;
}

html.dark .shell-header {
  background: rgba(24, 24, 28, 0.72) !important;
  box-shadow:
    0 8px 24px rgba(0, 0, 0, 0.3),
    0 1px 0 rgba(255, 255, 255, 0.05) inset;
}

html.dark .shell-header::after {
  background: linear-gradient(90deg, rgba(110, 145, 235, 0.1), rgba(110, 145, 235, 0.3), rgba(110, 145, 235, 0.1));
}

html.dark .header-title {
  color: #e2e8f0;
}

html.dark .profile-text {
  color: currentColor;
}

html.dark .header-back-pill {
  border-color: #2c2c32;
  background: #1e2433;
  color: #8ba7e8;
}

html.dark .header-back-pill:hover {
  border-color: #3e4d6d;
  background: #2b354a;
}

html.dark .shell-footer {
  background: rgba(24, 24, 28, 0.64);
  color: #8b96a8;
}

.header-title-teleport {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  margin-left: 12px;
  padding-left: 12px;
  border-left: 1px solid #e2e8f0;
}

html.dark .header-title-teleport {
  border-color: #334155;
}

/* 当传送容器不为空时，自动隐藏原本的全局路由标题，并去除左侧分界线 */
.header-title-row:has(.header-title-teleport > *) .header-title {
  display: none;
}

.header-title-row:has(.header-title-teleport > *) .header-title-teleport {
  margin-left: 0;
  padding-left: 0;
  border-left: none;
}

.header-actions-teleport {
  display: inline-flex;
  align-items: center;
  gap: 8px;
}
</style>
