import browserAutomationIcon from '../assets/workflow-node-icons/browser-automation.svg?raw'

export const BROWSER_AUTOMATION_NODE_TYPE = 'browser_automation' as const

export const browserAutomationNodeMeta = {
  type: BROWSER_AUTOMATION_NODE_TYPE,
  label: '浏览器自动化',
  shortLabel: '浏览器',
  color: '#0f766e',
  bg: '#ecfdf5',
  icon: browserAutomationIcon,
  defaultTitle: '执行浏览器操作',
  placeholder: '例如：打开微信公众号后台，进入草稿箱，添加图文并将上一步生成的文章保存为草稿，不要发布。',
  defaultConfig: { targetName: '', targetUrl: '', outputAlias: '浏览器执行结果' },
  usageDescription: '用于在网站或企业系统中完成查询、填写、上传、保存、提交等操作。描述业务目标和结束状态即可，不需要配置点击步骤或页面选择器。',
  usageExample: '打开微信公众号后台，进入草稿箱，新建图文内容，使用上一步生成的标题和正文填写文章，保存为草稿，不要直接发布。',
}

export function looksLikeBrowserAutomation(text: string): boolean {
  const value = String(text || '').toLowerCase()
  return [
    '浏览器', '打开网站', '打开网页', '进入后台', '登录后台', '网页操作',
    '草稿箱', '公众号后台', '知乎', '小红书', '淘宝', '京东',
  ].some((keyword) => value.includes(keyword))
}
