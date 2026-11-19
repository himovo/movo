export const codeHistoryMessages = {
  'code.history.account_changed': { zh: '账号已切换，请重新选择项目。', en: 'Your account changed. Select the project again.' },
  'code.history.locations': { zh: 'Code 会话位置', en: 'Code task location' },
  'code.history.tab_local': { zh: '本机', en: 'This device' },
  'code.history.tab_other': { zh: '其他设备', en: 'Other devices' },
  'code.history.empty': { zh: '暂无项目会话', en: 'No project tasks here' },
  'code.history.folder_missing': { zh: '目录不可用', en: 'Folder unavailable' },
  'code.history.migration_required': { zh: '历史记录可以查看，但项目文件不会自动同步。如需在本机继续，请先将项目文件迁移到本机，或从 Git 仓库克隆项目，再选择对应目录创建新会话。', en: 'You can view the history, but project files are not synced automatically. To continue on this device, first transfer the project files or clone the Git repository, then select the corresponding local folder to create a new task.' },
  'code.history.continue_local': { zh: '已迁移，选择本地项目', en: 'Files ready — select local project' },
  'code.history.continue_hint': { zh: '新会话会带入已加载的最近对话文字作为参考，并重新检查本地文件和权限。', en: 'The new task uses the recently loaded conversation text as reference and checks local files and permissions again.' },
} as const
