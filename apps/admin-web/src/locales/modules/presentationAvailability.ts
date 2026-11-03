export const presentationAvailabilityMessages = {
  'presentation.description': { 'zh-CN': '内容模型规划文案与绘图提示词，图片模型生成每页完整画面。', 'en-US': 'The content model plans copy and image prompts; the image model generates each complete slide.' },
  'presentation.modelHelp': { 'zh-CN': '只需配置以下两类模型。每页以整张图片交付，文字不是可单独编辑的文本框。', 'en-US': 'Only these two model types are required. Each slide is delivered as a full-page image; text is not individually editable.' },
  'presentation.contentHelp': { 'zh-CN': '负责故事线、页面文案和图片生成提示词。', 'en-US': 'Plans the storyline, slide copy and image generation prompts.' },
  'presentation.imageHelp': { 'zh-CN': '根据页面规划生成完整幻灯片图片。', 'en-US': 'Generates complete slide images from the page plan.' },
  'presentation.selectImage': { 'zh-CN': '请选择图片生成模型。', 'en-US': 'Select an image generation model.' },
  'presentation.enable': { 'zh-CN': '启用内置 PPT 生成', 'en-US': 'Enable built-in PPT generation' },
  'presentation.help': { 'zh-CN': '开启并保存后，Agent 可使用内置 PPT 工具。不影响 Skill 的代码生成能力。', 'en-US': 'Enable and save to offer the built-in PPT tool to the Agent. Skill code execution is unaffected.' },
  'presentation.unavailable': { 'zh-CN': '请先选择可用的内容和图片生成模型，配置完整后才能开启。已删除或停用的模型不可用。', 'en-US': 'Select active content and image generation models before enabling. Deleted or disabled models are unavailable.' },
} as const;
