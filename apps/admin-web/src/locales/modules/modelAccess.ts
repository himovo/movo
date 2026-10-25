import type { LabelMap } from '../messages'

export const modelAccessMessages: Record<string, LabelMap> = {
  'legacy.enterprise_22d8d86': { 'zh-CN': '企业版', 'en-US': 'Enterprise' },
  'legacy.model_access': { 'zh-CN': '模型使用权限', 'en-US': 'Model Access' },
  'legacy.only_employees_matching_the_audience_can_see_and_use': { 'zh-CN': '只有命中适用对象的员工才能看到并调用该模型。', 'en-US': 'Only employees matching the audience can see and use this model.' },
  'legacy.select_all_employees_or_at_least_one_audience_target': { 'zh-CN': '请选择企业全员或至少一个适用对象', 'en-US': 'Select all employees or at least one audience target' },
  'legacy.the_model_was_saved_but_its_access_policy_could': { 'zh-CN': '模型已保存，但使用权限保存失败', 'en-US': 'The model was saved, but its access policy could not be saved' },
}
