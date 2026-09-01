<script setup lang="ts">
import { onMounted, ref, computed } from 'vue'
import {
  NProgress,
  NInput,
  NButton,
  NAlert,
  NSpace,
  NCard,
  NTag,
  NForm,
  NFormItem,
  useMessage,
} from 'naive-ui'
import {
  fetchOrgBilling,
  upgradeOrg,
  createBillingOrder,
  confirmBillingOrderDev,
  createNewOrg,
  renameOrg,
  addOrgMember,
  getAdminSSOToken,
  type BillingOrder,
} from '../api/auth'
import { t, useLocale } from '../composables/i18n'
import { buildAdminSsoUrl } from '../utils/adminUrl'
import { openResource } from '../platform'

const props = defineProps<{
  open: boolean
  token: string
  canAccessAdmin?: boolean
}>()

const emit = defineEmits<{
  (e: 'close'): void
  (e: 'upgrade-success', payload: { token: string; username: string; profile: any }): void
}>()

const message = useMessage()
const { locale } = useLocale()

// 状态变量
const loading = ref(false)
const billingData = ref<any>(null)
const errorMsg = ref('')

// 新建组织
const newOrgName = ref('')
const isCreatingOrg = ref(false)

// 空间更名
const renameInput = ref('')
const isRenaming = ref(false)

// 邀请加人
const memberUsername = ref('')
const memberPassword = ref('')
const memberDisplayName = ref('')
const isAddingMember = ref(false)

// 升级与单点
const isUpgrading = ref(false)
const isSSOStarting = ref(false)
const currentOrder = ref<BillingOrder | null>(null)

// 计算属性
const remainingPercent = computed(() => {
  if (!billingData.value) return 100
  const total = billingData.value.totalPoints || 1000000
  const used = billingData.value.usedPoints || 0
  const percent = Math.round(((total - used) / total) * 100)
  return Math.max(0, Math.min(100, percent))
})

const tierLabel = computed(() => {
  if (!billingData.value) return locale.value === 'zh' ? '免费版' : 'Free'
  const tVal = billingData.value.tier
  if (tVal === 'plus') return locale.value === 'zh' ? '个人 Plus 版' : 'Personal Plus'
  if (tVal === 'pro') return locale.value === 'zh' ? '专业团队版' : 'Pro Team'
  if (tVal === 'enterprise') return locale.value === 'zh' ? '企业版' : 'Enterprise'
  return locale.value === 'zh' ? '免费版' : 'Free'
})

const formatPoints = (val: number) => {
  if (val >= 1000000) return `${(val / 1000000).toFixed(1)}M`
  if (val >= 1000) return `${(val / 1000).toFixed(0)}K`
  return String(val)
}

async function loadBillingInfo() {
  if (!props.token) return
  loading.value = true
  errorMsg.value = ''
  try {
    const res = await fetchOrgBilling(props.token)
    if (res.ok) {
      billingData.value = res.data
      renameInput.value = res.data.orgName || ''
    } else {
      errorMsg.value = res.message || t('billing.load_failed')
    }
  } catch (err: any) {
    errorMsg.value = err.message || t('billing.load_error')
  } finally {
    loading.value = false
  }
}

const planCodeForTier = (tier: 'plus' | 'pro') => {
  return tier === 'plus' ? 'personal_plus_monthly' : 'org_pro_monthly'
}

// 创建支付订单；真实微信支付接入后，paymentUrl 会替换为微信 Native code_url。
async function handleUpgrade(tier: 'plus' | 'pro' | 'enterprise') {
  isUpgrading.value = true
  try {
    if (tier !== 'enterprise') {
      const res = await createBillingOrder(planCodeForTier(tier), props.token, 'wechat_native')
      if (res.ok && res.order) {
        currentOrder.value = res.order
        message.success(res.message || (locale.value === 'zh' ? '支付订单已创建' : 'Payment order created'))
      } else {
        message.error(res.message || t('billing.payment_order_failed'))
      }
      return
    }
    const res = await upgradeOrg(tier, props.token)
    if (res.ok) {
      message.success(res.message || t('billing.upgrade_success'))
      await loadBillingInfo()
    } else {
      message.error(res.message || t('api.auth.create_org_failed'))
    }
  } catch (err: any) {
    message.error(err.message || t('api.auth.create_org_failed'))
  } finally {
    isUpgrading.value = false
  }
}

async function handleConfirmPayment() {
  if (!currentOrder.value) return
  isUpgrading.value = true
  try {
    const res = await confirmBillingOrderDev(currentOrder.value.orderNo, props.token)
    if (res.ok) {
      currentOrder.value = res.order || currentOrder.value
      message.success(res.message || t('billing.upgrade_success'))
      await loadBillingInfo()
    } else {
      message.error(res.message || t('billing.payment_confirm_failed'))
    }
  } catch (err: any) {
    message.error(err.message || t('billing.payment_confirm_failed'))
  } finally {
    isUpgrading.value = false
  }
}

function clearCurrentOrder() {
  currentOrder.value = null
}

// 免密 SSO 跳转
async function handleSSORedirect() {
  if (!props.canAccessAdmin) return
  isSSOStarting.value = true
  try {
    const res = await getAdminSSOToken(props.token)
    if (res.ok && res.ssoToken) {
      message.success(t('billing.sso_success'))
      const adminUrl = buildAdminSsoUrl(res.ssoToken)
      await openResource(adminUrl, 'internal')
    } else {
      message.error(res.message || t('billing.sso_failed'))
    }
  } catch (err: any) {
    message.error(err.message || t('billing.sso_error'))
  } finally {
    isSSOStarting.value = false
  }
}

// 组织更名
async function handleRename() {
  if (!renameInput.value.trim()) {
    message.warning(locale.value === 'zh' ? '请填写新空间名称' : 'Please enter a name for the new space')
    return
  }
  isRenaming.value = true
  try {
    const res = await renameOrg(renameInput.value.trim(), props.token)
    if (res.ok && res.token && res.profile) {
      message.success(t('billing.org_rename_success'))
      emit('upgrade-success', {
        token: res.token,
        username: res.profile.username || '',
        profile: res.profile,
      })
      await loadBillingInfo()
    } else {
      message.error(res.message || t('billing.org_rename_failed'))
    }
  } catch (err: any) {
    message.error(err.message || t('billing.org_rename_error'))
  } finally {
    isRenaming.value = false
  }
}

// 新建组织
async function handleCreateOrg() {
  if (!newOrgName.value.trim()) {
    message.warning(locale.value === 'zh' ? '请填写新组织名称' : 'Please enter a name for the new organization')
    return
  }
  isCreatingOrg.value = true
  try {
    const res = await createNewOrg(newOrgName.value.trim(), props.token)
    if (res.ok && res.token && res.profile) {
      const successText = locale.value === 'zh'
        ? `成功创建新组织：${newOrgName.value.trim()}！已自动切换。`
        : `Organization "${newOrgName.value.trim()}" created successfully! Switched automatically.`
      message.success(successText)
      newOrgName.value = ''
      emit('upgrade-success', {
        token: res.token,
        username: res.profile.username || '',
        profile: res.profile,
      })
      emit('close')
    } else {
      message.error(res.message || t('api.auth.create_org_failed'))
    }
  } catch (err: any) {
    message.error(err.message || t('api.auth.create_org_failed'))
  } finally {
    isCreatingOrg.value = false
  }
}

// 添加成员
async function handleAddMember() {
  if (!memberUsername.value.trim() || !memberPassword.value.trim()) {
    message.warning(t('billing.member_credentials_required'))
    return
  }
  isAddingMember.value = true
  try {
    const res = await addOrgMember(
      memberUsername.value.trim(),
      memberPassword.value,
      memberDisplayName.value.trim(),
      props.token
    )
    if (res.ok) {
      const successText = locale.value === 'zh'
        ? `成功添加成员：${memberUsername.value.trim()}！`
        : `Member "${memberUsername.value.trim()}" added successfully!`
      message.success(successText)
      memberUsername.value = ''
      memberPassword.value = ''
      memberDisplayName.value = ''
      await loadBillingInfo()
    } else {
      message.error(res.message || t('api.auth.add_member_failed'))
    }
  } catch (err: any) {
    message.error(err.message || t('api.auth.add_member_failed'))
  } finally {
    isAddingMember.value = false
  }
}

onMounted(() => {
  if (props.open) {
    loadBillingInfo()
  }
})
</script>

<template>
  <div v-if="open" class="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 p-4 backdrop-blur-[2px]">
    <div class="w-full max-w-4xl rounded-3xl bg-white shadow-2xl overflow-hidden border border-slate-100 flex flex-col md:flex-row max-h-[90vh]">
      
      <!-- 左侧：账单核心与额度看板 -->
      <div class="flex-1 bg-gradient-to-br from-slate-900 via-slate-800 to-slate-950 p-8 text-white flex flex-col justify-between overflow-y-auto">
        <div>
          <div class="flex items-center justify-between mb-6">
            <h2 class="text-xl font-bold tracking-tight">{{ t('billing.dashboard_title') }}</h2>
            <n-tag :bordered="false" type="info" size="medium" class="!bg-blue-600/30 !text-blue-300">
              {{ tierLabel }}
            </n-tag>
          </div>

          <n-alert v-if="errorMsg" type="error" class="mb-4">{{ errorMsg }}</n-alert>

          <!-- 额度统计 -->
          <div v-if="billingData" class="flex flex-col items-center my-6">
            <!-- 环形进度条 -->
            <n-progress
              type="circle"
              :percentage="remainingPercent"
              :stroke-width="8"
              color="#3b82f6"
              rail-color="#334155"
              class="w-36 h-36"
            >
              <div class="text-center">
                <span class="text-2xl font-extrabold text-blue-400">{{ remainingPercent }}%</span>
                <div class="text-[10px] text-slate-400 mt-1">{{ locale === 'zh' ? '剩余免费 Token' : 'Remaining Free Tokens' }}</div>
              </div>
            </n-progress>

            <!-- 详细数据明细 -->
            <div class="w-full mt-6 grid grid-cols-2 gap-4 text-center border-t border-slate-700/50 pt-4">
              <div>
                <span class="block text-[11px] text-slate-400">{{ t('billing.current_used_quota') }}</span>
                <span class="text-lg font-bold text-slate-200">{{ formatPoints(billingData.usedPoints) }} Tokens</span>
              </div>
              <div>
                <span class="block text-[11px] text-slate-400">{{ t('billing.platform_shared_quota') }}</span>
                <span class="text-lg font-bold text-slate-200">{{ formatPoints(billingData.totalPoints) }} Tokens</span>
              </div>
              <div class="col-span-2 border-t border-slate-800/40 pt-3 flex justify-between px-6">
                <div>
                  <span class="block text-[10px] text-slate-400 text-left">{{ t('billing.org_members') }}</span>
                  <span class="text-sm font-semibold text-slate-300">{{ billingData.currentMembersCount }} / {{ billingData.userLimit }} {{ locale === 'zh' ? '人' : 'members' }}</span>
                </div>
                <div>
                  <span class="block text-[10px] text-slate-400 text-right">{{ t('billing.own_model_free') }}</span>
                  <span class="text-sm font-semibold" :class="billingData.isOwnModel ? 'text-emerald-400' : 'text-slate-500'">
                    {{ billingData.isOwnModel ? (locale === 'zh' ? '已开启' : 'Enabled') : (locale === 'zh' ? '未开启' : 'Disabled') }}
                  </span>
                </div>
              </div>
            </div>
          </div>
          <div v-else-if="loading" class="flex flex-col items-center my-10 italic text-slate-400">
            {{ locale === 'zh' ? '加载数据中...' : 'Loading...' }}
          </div>
        </div>

        <!-- SSO 及控制区 -->
        <div v-if="billingData && canAccessAdmin" class="space-y-3 mt-6 border-t border-slate-700/50 pt-6">
          <div class="text-xs text-slate-400">
            {{ billingData.isOwnModel 
              ? t('billing.own_model_enabled')
              : t('billing.own_model_disabled') }}
          </div>
          <button
            class="w-full rounded-2xl bg-blue-600 hover:bg-blue-500 text-white font-semibold py-2.5 text-sm transition-all active:scale-[0.98] flex items-center justify-center gap-2"
            :disabled="isSSOStarting"
            @click="handleSSORedirect"
          >
            <svg class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M15 3h6v6M10 14 21 3M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/></svg>
            {{ isSSOStarting ? t('billing.sso_loading') : t('billing.sso_button') }}
          </button>
        </div>
      </div>

      <!-- 右侧：升级计划与设置修改 -->
      <div class="flex-1 bg-slate-50 p-8 text-slate-800 flex flex-col justify-between overflow-y-auto">
        <div class="space-y-6">
          <div class="flex items-center justify-between">
            <h3 class="text-base font-bold text-slate-900">{{ t('billing.sub_and_team') }}</h3>
            <button class="text-slate-400 hover:text-slate-600 font-bold" @click="emit('close')">&#10005;</button>
          </div>

          <div v-if="currentOrder" class="rounded-2xl border border-blue-200 bg-blue-50 p-4 text-sm text-slate-800">
            <div class="flex items-start justify-between gap-3">
              <div>
                <div class="font-bold text-slate-900">{{ t('billing.payment_order_title') }}</div>
                <div class="mt-1 text-xs text-slate-500">{{ currentOrder.planName }} · {{ currentOrder.amountText }}</div>
              </div>
              <n-tag size="small" :bordered="false" :type="currentOrder.status === 'applied' ? 'success' : 'info'">
                {{ currentOrder.status }}
              </n-tag>
            </div>
            <div class="mt-3 space-y-1 text-xs text-slate-600">
              <div>{{ t('billing.payment_order_no') }}：{{ currentOrder.orderNo }}</div>
              <div>{{ t('billing.payment_method') }}：{{ currentOrder.paymentMethod }}</div>
              <div class="break-all">{{ t('billing.payment_url') }}：{{ currentOrder.paymentUrl }}</div>
            </div>
            <div class="mt-3 flex gap-2">
              <n-button
                v-if="currentOrder.status !== 'applied'"
                type="primary"
                size="small"
                :loading="isUpgrading"
                @click="handleConfirmPayment"
              >
                {{ t('billing.payment_confirm_dev') }}
              </n-button>
              <n-button size="small" secondary @click="clearCurrentOrder">
                {{ t('ui.close') }}
              </n-button>
            </div>
          </div>

          <!-- 1. 升级选项 -->
          <div v-if="billingData" class="space-y-3">
            <div class="text-xs font-bold text-slate-400 uppercase tracking-wider">{{ locale === 'zh' ? '订阅升级' : 'Subscription Upgrade' }}</div>
            
            <div class="grid grid-cols-1 gap-3">
              <!-- Plus 计划 -->
              <div 
                v-if="billingData.tier === 'free' && billingData.currentMembersCount === 1"
                class="bg-white p-4 rounded-2xl border border-slate-200 flex items-center justify-between"
              >
                <div>
                  <span class="font-bold text-slate-900 text-sm">{{ t('billing.upgrade_plus') }}</span>
                  <span class="block text-xs text-slate-500 mt-0.5">{{ t('billing.upgrade_plus_desc') }}</span>
                </div>
                <n-button 
                  type="info" 
                  size="small" 
                  round 
                  :loading="isUpgrading"
                  @click="handleUpgrade('plus')"
                >
                  {{ locale === 'zh' ? '¥20/月' : '¥20/mo' }}
                </n-button>
              </div>

              <!-- Pro 团队计划 -->
              <div 
                v-if="billingData.tier === 'free' || billingData.tier === 'plus'"
                class="bg-white p-4 rounded-2xl border border-slate-200 flex items-center justify-between"
              >
                <div>
                  <span class="font-bold text-slate-900 text-sm">{{ t('billing.upgrade_pro') }}</span>
                  <span class="block text-xs text-slate-500 mt-0.5">{{ t('billing.upgrade_pro_desc') }}</span>
                </div>
                <n-button 
                  type="primary" 
                  size="small" 
                  round 
                  :loading="isUpgrading"
                  @click="handleUpgrade('pro')"
                >
                  {{ locale === 'zh' ? '¥49/人/月' : '¥49/member/mo' }}
                </n-button>
              </div>

              <!-- Enterprise 企业定制 -->
              <div class="bg-white p-4 rounded-2xl border border-slate-200 flex items-center justify-between">
                <div>
                  <span class="font-bold text-slate-900 text-sm">{{ t('billing.upgrade_ent') }}</span>
                  <span class="block text-xs text-slate-500 mt-0.5">{{ t('billing.upgrade_ent_desc') }}</span>
                </div>
                <n-button 
                  size="small" 
                  round 
                  :loading="isUpgrading"
                  @click="handleUpgrade('enterprise')"
                >
                  {{ locale === 'zh' ? '联系商务' : 'Contact Sales' }}
                </n-button>
              </div>
            </div>
          </div>

          <!-- 2. 团队空间管理（创建组织/更名） -->
          <div v-if="billingData" class="space-y-4 pt-2 border-t border-slate-200/60">
            <div class="text-xs font-bold text-slate-400 uppercase tracking-wider">{{ t('billing.rename_label').includes('Rename') ? 'Space Management' : '空间管理' }}</div>
            
            <n-space vertical :size="12">
              <!-- 组织更名 (仅 owner 可行) -->
              <div v-if="billingData.isOwner">
                <label class="block text-[11px] font-semibold text-slate-500 mb-1">{{ t('billing.rename_label') }}</label>
                <div class="flex gap-2">
                  <n-input v-model:value="renameInput" size="small" :placeholder="locale === 'zh' ? '例如：格物科技' : 'e.g. Gewu Tech'" class="flex-1" />
                  <n-button type="info" size="small" secondary :loading="isRenaming" @click="handleRename">{{ t('ui.save') }}</n-button>
                </div>
              </div>

              <!-- 新建全新项目/组织 (支持多组织并存) -->
              <div>
                <label class="block text-[11px] font-semibold text-slate-500 mb-1">{{ t('billing.create_label') }}</label>
                <div class="flex gap-2">
                  <n-input v-model:value="newOrgName" size="small" :placeholder="locale === 'zh' ? '输入新空间名' : 'Enter new space name'" class="flex-1" />
                  <n-button type="primary" size="small" secondary :loading="isCreatingOrg" @click="handleCreateOrg">{{ t('ui.create') }}</n-button>
                </div>
              </div>
            </n-space>
          </div>

          <!-- 3. 添加组织成员 (Free < 5, Pro < 50, Plus = 1) -->
          <div v-if="billingData" class="space-y-3 pt-2 border-t border-slate-200/60">
            <div class="text-xs font-bold text-slate-400 uppercase tracking-wider">
              {{ locale === 'zh' ? `添加成员 (限 ${billingData.userLimit} 人)` : `Add Member (Limit ${billingData.userLimit} members)` }}
            </div>
            
            <div v-if="billingData.currentMembersCount >= billingData.userLimit" class="text-xs text-rose-500 font-medium">
              {{ t('billing.member_limit_reached') }}
            </div>
            <div v-else class="space-y-2.5 bg-white p-4 rounded-2xl border border-slate-200">
              <div class="grid grid-cols-2 gap-2">
                <n-input v-model:value="memberUsername" size="small" :placeholder="t('billing.username_placeholder')" />
                <n-input v-model:value="memberDisplayName" size="small" :placeholder="t('billing.name_placeholder')" />
              </div>
              <div class="flex gap-2">
                <n-input v-model:value="memberPassword" type="password" size="small" :placeholder="t('billing.password_placeholder')" class="flex-1" />
                <n-button type="primary" size="small" :loading="isAddingMember" @click="handleAddMember">{{ locale === 'zh' ? '添加成员' : 'Add Member' }}</n-button>
              </div>
            </div>
          </div>
        </div>
        
        <div class="text-[10px] text-slate-400 text-center mt-6">
          {{ t('billing.copyright') }}
        </div>
      </div>

    </div>
  </div>
</template>
