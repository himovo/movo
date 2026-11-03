export const scriptAttemptMessages = {
  'execution.v3.script_output_path': { zh: '代码写入了只读位置，需要调整输出路径', en: 'Code wrote to a read-only location; adjust the output path' },
  'execution.v3.script_file_access': { zh: '代码访问文件受限，需要检查路径或权限', en: 'Code file access was denied; check the path or permissions' },
  'execution.v3.script_syntax': { zh: '代码语法需要调整', en: 'Code syntax needs adjustment' },
  'execution.v3.script_dependency': { zh: '代码缺少所需依赖', en: 'Code requires a missing dependency' },
  'execution.v3.script_input': { zh: '代码使用的文件或数据需要核对', en: 'Code file or data references need checking' },
  'execution.v3.script_logic': { zh: '代码逻辑需要调整', en: 'Code logic needs adjustment' },
} as const
