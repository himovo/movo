export type PromptGuideConfigTarget = 'skills' | 'tools'

export type PromptGuideItem = {
  label: string
  prompt?: string
  icon: string
  available: boolean
  configTarget?: PromptGuideConfigTarget
  configTitle?: string
  configDescription?: string
}

export type PromptGuideCategory = {
  key: string
  label: string
  icon: string
  tone: string
  requiresConfig?: boolean
  configTarget?: PromptGuideConfigTarget
  configTitle?: string
  configDescription?: string
  items: PromptGuideItem[]
}

function svgIcon(paths: string): string {
  return `<svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">${paths}</svg>`
}

const svgIcons = {
  albums: svgIcon('<rect x="4" y="5" width="16" height="14" rx="2"></rect><path d="M7 3h10"></path><path d="M8 9h8"></path><path d="M8 13h5"></path>'),
  analytics: svgIcon('<path d="M4 19V5"></path><path d="M4 19h16"></path><path d="M8 15l3-4 3 2 5-7"></path><path d="M18 6h2v2"></path>'),
  briefcase: svgIcon('<rect x="3" y="7" width="18" height="13" rx="2"></rect><path d="M8 7V5a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path><path d="M3 12h18"></path>'),
  build: svgIcon('<path d="M14.7 6.3a4 4 0 0 0-5.4 5.4L4 17v3h3l5.3-5.3a4 4 0 0 0 5.4-5.4l-3 3-3-3 3-3Z"></path>'),
  cart: svgIcon('<circle cx="9" cy="20" r="1"></circle><circle cx="18" cy="20" r="1"></circle><path d="M2 3h3l3 12h10l2-8H7"></path>'),
  create: svgIcon('<path d="M12 20h9"></path><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4Z"></path>'),
  document: svgIcon('<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8Z"></path><path d="M14 2v6h6"></path><path d="M8 13h8"></path><path d="M8 17h6"></path>'),
  earth: svgIcon('<circle cx="12" cy="12" r="10"></circle><path d="M2 12h20"></path><path d="M12 2a15.3 15.3 0 0 1 0 20"></path><path d="M12 2a15.3 15.3 0 0 0 0 20"></path>'),
  easel: svgIcon('<rect x="4" y="3" width="16" height="10" rx="2"></rect><path d="M12 13v8"></path><path d="M8 21h8"></path><path d="M8 17l-3 4"></path><path d="M16 17l3 4"></path>'),
  files: svgIcon('<path d="M5 4h11l3 3v13H5Z"></path><path d="M16 4v4h4"></path><path d="M8 12h8"></path><path d="M8 16h5"></path>'),
  globe: svgIcon('<circle cx="12" cy="12" r="10"></circle><path d="M2 12h20"></path><path d="M12 2c3 3 4 6 4 10s-1 7-4 10"></path><path d="M12 2C9 5 8 8 8 12s1 7 4 10"></path>'),
  grid: svgIcon('<rect x="3" y="3" width="7" height="7" rx="1"></rect><rect x="14" y="3" width="7" height="7" rx="1"></rect><rect x="3" y="14" width="7" height="7" rx="1"></rect><rect x="14" y="14" width="7" height="7" rx="1"></rect>'),
  image: svgIcon('<rect x="3" y="3" width="18" height="18" rx="2"></rect><circle cx="8.5" cy="8.5" r="1.5"></circle><path d="M21 15l-5-5L5 21"></path>'),
  language: svgIcon('<path d="M4 5h8"></path><path d="M8 3v2"></path><path d="M10 5c-.7 3.5-2.6 6-6 8"></path><path d="M5 9c1.2 1.6 2.8 2.8 5 4"></path><path d="M14 21l4-10 4 10"></path><path d="M16 17h4"></path>'),
  library: svgIcon('<path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"></path><path d="M4 4.5A2.5 2.5 0 0 1 6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5Z"></path><path d="M8 6h8"></path><path d="M8 10h7"></path>'),
  lock: svgIcon('<rect x="4" y="10" width="16" height="10" rx="2"></rect><path d="M8 10V7a4 4 0 0 1 8 0v3"></path>'),
  newspaper: svgIcon('<path d="M4 5h13a3 3 0 0 1 3 3v11H6a2 2 0 0 1-2-2Z"></path><path d="M8 9h7"></path><path d="M8 13h8"></path><path d="M8 17h5"></path>'),
  people: svgIcon('<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"></path><circle cx="9" cy="7" r="4"></circle><path d="M22 21v-2a4 4 0 0 0-3-3.87"></path><path d="M16 3.13a4 4 0 0 1 0 7.75"></path>'),
  qa: svgIcon('<path d="M21 15a4 4 0 0 1-4 4H8l-5 3V7a4 4 0 0 1 4-4h10a4 4 0 0 1 4 4Z"></path><path d="M9 9a3 3 0 0 1 6 0c0 2-3 2-3 4"></path><path d="M12 17h.01"></path>'),
  search: svgIcon('<circle cx="11" cy="11" r="7"></circle><path d="M20 20l-3.5-3.5"></path>'),
  server: svgIcon('<rect x="3" y="4" width="18" height="6" rx="2"></rect><rect x="3" y="14" width="18" height="6" rx="2"></rect><path d="M7 7h.01"></path><path d="M7 17h.01"></path>'),
  settings: svgIcon('<circle cx="12" cy="12" r="3"></circle><path d="M19.4 15a1.7 1.7 0 0 0 .34 1.88l.06.06-2.83 2.83-.06-.06A1.7 1.7 0 0 0 15 19.4a1.7 1.7 0 0 0-1 .6V21h-4v-1a1.7 1.7 0 0 0-1-.6 1.7 1.7 0 0 0-1.88.34l-.06.06-2.83-2.83.06-.06A1.7 1.7 0 0 0 4.6 15a1.7 1.7 0 0 0-.6-1H3v-4h1a1.7 1.7 0 0 0 .6-1 1.7 1.7 0 0 0-.34-1.88l-.06-.06 2.83-2.83.06.06A1.7 1.7 0 0 0 9 4.6a1.7 1.7 0 0 0 1-.6V3h4v1a1.7 1.7 0 0 0 1 .6 1.7 1.7 0 0 0 1.88-.34l.06-.06 2.83 2.83-.06.06A1.7 1.7 0 0 0 19.4 9c.18.37.39.7.6 1h1v4h-1a1.7 1.7 0 0 0-.6 1Z"></path>'),
  shield: svgIcon('<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10Z"></path><path d="M9 12l2 2 4-5"></path>'),
  stats: svgIcon('<path d="M4 19V5"></path><path d="M4 19h16"></path><rect x="7" y="11" width="3" height="5"></rect><rect x="12" y="8" width="3" height="8"></rect><rect x="17" y="5" width="3" height="11"></rect>'),
}

export const promptGuideUiIcons = {
  lock: svgIcons.lock,
  settings: svgIcons.settings,
}

export const promptGuideCategories: PromptGuideCategory[] = [
  {
    key: 'content',
    label: '内容生成',
    icon: svgIcons.create,
    tone: 'guide-tone-content',
    items: [
      {
        label: '微信/小红书',
        icon: svgIcons.newspaper,
        available: true,
        prompt: '帮我生成一篇适合微信或小红书发布的内容，主题是：{主题}。要求标题有吸引力，正文有场景、有痛点、有解决方案，并给出3个标题备选。',
      },
      {
        label: '报告方案',
        icon: svgIcons.document,
        available: true,
        prompt: '帮我生成一份{主题}报告方案，包含背景、现状、核心问题、原因分析、解决建议和执行计划。',
      },
      {
        label: 'PPT生成',
        icon: svgIcons.easel,
        available: true,
        prompt: '帮我生成一份{主题}汇报PPT大纲，适合给管理层展示，控制在12页以内，每页包含标题、要点和可视化建议。',
      },
      {
        label: '图片转PRD',
        icon: svgIcons.image,
        available: true,
        prompt: '我会上传产品截图，请根据界面内容整理一份PRD，包含页面目标、功能说明、交互规则、字段说明和验收标准。',
      },
      {
        label: '文档翻译',
        icon: svgIcons.language,
        available: true,
        prompt: '我会上传一份文档，请翻译成中文，并保留原有结构、标题层级、表格和关键术语。',
      },
      {
        label: '文档填表',
        icon: svgIcons.grid,
        available: true,
        prompt: '我会上传文档和表格模板，请根据文档内容提取信息并填入表格，缺失字段请标记为“待补充”。',
      },
    ],
  },
  {
    key: 'external',
    label: '外部搜索',
    icon: svgIcons.globe,
    tone: 'guide-tone-external',
    items: [
      {
        label: '联网查资料',
        icon: svgIcons.search,
        available: true,
        prompt: '请帮我联网搜索{主题}的最新公开资料，整理来源、核心观点、关键数据和风险提示。',
      },
      {
        label: '行业研究',
        icon: svgIcons.earth,
        available: true,
        prompt: '请围绕{行业/主题}做一份行业研究，包含市场趋势、主要玩家、关键数据、机会和风险。',
      },
      {
        label: '竞品分析',
        icon: svgIcons.analytics,
        available: true,
        prompt: '请帮我调研{竞品/领域}，对比产品定位、核心功能、价格策略、优劣势和可借鉴点。',
      },
      {
        label: '政策/新闻',
        icon: svgIcons.shield,
        available: true,
        prompt: '请搜索{主题}相关的最新政策或新闻，按时间线整理，并说明对业务可能产生的影响。',
      },
      {
        label: '资料综述',
        icon: svgIcons.albums,
        available: true,
        prompt: '请收集并综述{主题}的公开资料，按观点分类，标注来源，并给出结论摘要。',
      },
      {
        label: '事实核查',
        icon: svgIcons.stats,
        available: true,
        prompt: '请联网核查以下说法是否准确：{待核查内容}。请给出依据、可信度和不确定点。',
      },
    ],
  },
  {
    key: 'internal',
    label: '内部知识',
    icon: svgIcons.library,
    tone: 'guide-tone-internal',
    requiresConfig: true,
    configTarget: 'skills',
    configTitle: '内部知识需要先配置',
    configDescription: '请先配置知识库或上传内部资料。未配置时可以先填写需求，但无法真实检索企业内部内容。',
    items: [
      { label: '搜知识库', icon: svgIcons.qa, available: true, prompt: '请在内部知识库中搜索和{主题}相关的资料，整理成背景、关键事实、可引用观点和待确认问题。' },
      { label: '查历史文档', icon: svgIcons.files, available: true, prompt: '请检索历史文档中与{主题}相关的内容，按文档来源、核心结论和可复用材料整理。' },
      { label: '查企业制度', icon: svgIcons.briefcase, available: true, prompt: '请查询企业制度中关于{主题}的规定，整理适用范围、关键要求、注意事项和执行建议。' },
      { label: '查项目资料', icon: svgIcons.albums, available: true, prompt: '请检索项目资料中与{项目/客户/主题}相关的信息，整理项目背景、进展、问题和下一步建议。' },
      { label: '查客户资料', icon: svgIcons.people, available: true, prompt: '请查询客户资料中关于{客户名称/客户群体}的信息，整理客户背景、历史沟通、需求和风险点。' },
      { label: '查培训材料', icon: svgIcons.document, available: true, prompt: '请检索培训材料中与{主题}相关的内容，整理成学习提纲、关键概念和实践要点。' },
    ],
  },
  {
    key: 'systems',
    label: '连接系统',
    icon: svgIcons.server,
    tone: 'guide-tone-systems',
    requiresConfig: true,
    configTarget: 'tools',
    configTitle: '连接系统需要先配置',
    configDescription: '请先配置 HTTP 工具或 MCP 服务。未配置时可以先填写需求，但无法真实查询业务系统。',
    items: [
      { label: '查销售', icon: svgIcons.cart, available: true, prompt: '请查询本周销售情况，按门店、品类、销售额、订单量、转化率汇总，并指出异常波动。' },
      { label: '找根因', icon: svgIcons.analytics, available: true, prompt: '请根据最近30天销售数据，分析销售下滑的主要原因，区分流量、转化率、客单价、库存、活动和价格因素。' },
      { label: '查库存', icon: svgIcons.files, available: true, prompt: '请查询当前库存和近7天销量，识别即将缺货、库存积压和需要补货的商品。' },
      { label: '查客户', icon: svgIcons.people, available: true, prompt: '请查询最近30天客户增长、复购、流失情况，并找出需要重点运营的人群。' },
      { label: '经营日报', icon: svgIcons.document, available: true, prompt: '请生成今日经营日报，包含销售、订单、客户、库存、异常问题和明日建议。' },
      { label: '调用MCP', icon: svgIcons.build, available: true, prompt: '请调用已配置的 MCP 工具完成以下任务：{任务目标}。请先说明会使用哪些工具，再执行并汇总结果。' },
    ],
  },
]
