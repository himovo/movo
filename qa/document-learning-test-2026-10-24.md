# 文档上传、学习与问答测试记录（2026-10-24）

## 测试环境与流程

- 管理后台：`http://localhost:3100/knowledge/documents`，系统管理员账号，目标目录为根目录。
- 样本来源：`/Users/jack/Downloads/测试文档`，共 14 份，覆盖 DOC、DOCX、PDF、XLS、XLSX、PPTX。
- 在「上传文档」窗口分两次选入全部文件，点击「上传 14 个文档」；浮动进度面板显示 14/14 Success，列表由 6 份增至 20 份。
- 上传 API 会自动提交解析任务；解析成功后才会切段、向 Weaviate 建索引。只有索引完成才视为「学习完成」。
- 后台当前问答来源设置为「外部知识库」（检索工具 `search_documents · E2E External Knowledge MCP`）。该设置下，用户问答不会检索本次上传的 MOVO 文档。尚未切换全局来源。

## 当前结果

以下为 2026-10-24 10:54（Asia/Shanghai）附近读取数据库及后台列表得到的状态；队列中的文档需要后续复查。

| 文件 | 解析与分段 | 索引/学习 | 备注 |
| --- | --- | --- | --- |
| 李煜最著名的十首词.docx | 成功，3 段 | 失败 | Weaviate 连接被拒绝；后台片段页可见正文 |
| 北交所上市企业列表.xlsx | 失败，0 段 | 未开始 | 源文件 `xl/workbook.xml` 的工作表 `state="show"`；openpyxl 仅接受 `visible`、`hidden`、`veryHidden`；预览也失败 |
| 亚热带季风气候.doc | 成功，1 段 | 失败 | Weaviate 连接被拒绝 |
| 火山引擎AI 一体机核心介绍v1.0.pdf | 失败，0 段 | 未开始 | Docling 模型目录 `/opt/docling/models` 缺少所需模型 |
| 2021-2023集团地坪材料集中采购协议.docx | 解析排队中 | 未开始 | 预览转换调用 LibreOffice 超过 180 秒，失败；解析仍需复查 |
| 8.热熔胶胶水机说明书（照片JP）.doc | 失败，0 段 | 未开始 | LibreOffice 将 DOC 转换成 DOCX 超过 180 秒；原文预览成功 |
| 门店销售数据表.xlsx | 成功，425 段 | 失败 | Weaviate 连接被拒绝；分段数较多，需检查分段质量 |
| 员工考勤及假期管理规定.pdf | 失败，0 段 | 未开始 | Docling 模型目录缺失 |
| 口令修改操作指导.pdf | 失败，0 段 | 未开始 | Docling 模型目录缺失 |
| 工装挂历制度.pdf | 失败，0 段 | 未开始 | Docling 模型目录缺失 |
| NPJiangsu-07-TSH-093 电工安全操作规程.xls | 成功，35 段 | 失败 | Weaviate 连接被拒绝 |
| 李煜最著名的十首词.pdf | 失败，0 段 | 未开始 | Docling 模型目录缺失 |
| 国双GVP产品及案例介绍.pptx | 成功，5 段 | 失败 | Weaviate 连接被拒绝 |
| 副本标品操作手册截图-AskBot 0811.pptx | 成功，121 段 | 失败 | 预览转换调用 LibreOffice 超过 180 秒，失败；列表显示学习失败，索引错误待复查 |

## 问题清单

1. **索引服务不可用**：解析成功的 DOC/DOCX/XLS/XLSX/PPTX 文档报 `Weaviate unavailable: <urlopen error [Errno 61] Connection refused>`。影响已解析文档的学习完成和问答检索。
2. **PDF 解析模型缺失**：PDF 报 `self.artifacts_path=PosixPath('/opt/docling/models') is not valid`，提示目录必须包含管线所需全部模型。影响本次全部 PDF。
3. **单份 XLSX 格式兼容性**：`北交所上市企业列表.xlsx` 可通过 ZIP 完整性检查，但 `xl/workbook.xml` 使用 `state="show"`；openpyxl 报 `Value must be one of {'visible', 'hidden', 'veryHidden'}`。后台解析错误为 `Input document source.xlsx is not valid.`，预览错误为 `Unable to read workbook ... invalid XML`。需要决定是否在导入时兼容/修复该非法值，并明确展示可操作的错误。
4. **问答来源不匹配**：当前全局来源是外部知识库。即使文档完成索引，在当前配置下直接提问也不能验证 MOVO 文档召回。待取得临时切换并恢复配置的确认后，执行问答测试。
5. **错误可见性不足**：列表只显示「学习失败」；例如 `李煜最著名的十首词.docx` 解析和分段成功，但索引失败。详情页显示分段成功/学习失败，未展示 `index_error`，需要查数据库才能定位。
6. **LibreOffice 转换超时**：`8.热熔胶胶水机说明书（照片JP）.doc` 的解析转换在 180 秒后失败；`2021-2023集团地坪材料集中采购协议.docx` 和 `副本标品操作手册截图-AskBot 0811.pptx` 的在线预览转换也在 180 秒后失败。解析与预览应分别记录，不能把预览失败等同于学习失败。
7. **问答运行故障**：临时切换到 MOVO 知识库后，在用户端提问「请仅根据企业内部知识文档《李煜最著名的十首词.docx》回答：文档列出的第十首词是什么？请给出引用来源。」；对话最终显示 `DSH Runtime Host rejected the request: isolated plugin Runtime did not start`，未返回答案或引用。问答来源随后已恢复为原先的外部知识库，并在重新加载页面后核实。
8. **统计口径不覆盖索引失败**：后台「Failed」卡片统计的是文档 `status=failed`，解析成功但 `index_status=failed` 的文件未计入该数字；因此页面显示的失败数低于列表中的「学习失败」行数。该口径会误导批量测试验收。
9. **任务长时间排队**：`2021-2023集团地坪材料集中采购协议.docx` 从 10:42 上传后到 10:54 仍为 `parse_status=queued`，未产生分段。需要检查任务队列和 worker 消费情况。

## 截图证据

- [上传后文档列表及状态](../output/document-learning-test/uploaded-documents-status.png)
- [用户问答运行错误](../output/document-learning-test/question-runtime-error.png)
- [恢复后的外部知识库配置](../output/document-learning-test/knowledge-source-restored.png)

## 待执行的问答用例

在索引服务恢复、相关文件学习完成后，用 MOVO 知识库提问，并核对答案与引用文件及片段：

| 文档 | 问题 | 预期核对点 |
| --- | --- | --- |
| 李煜最著名的十首词.docx / .pdf | 文档列出的李煜十首词中，第十首是什么？ | 《长相思·一重山》；引用对应文件 |
| 火山引擎AI 一体机核心介绍v1.0.pdf | 文档声称 Serving Kit 的综合性价比提升多少？ | `50%+`；引用相关页 |
| 员工考勤及假期管理规定.pdf | 这份规定适用于哪些公司员工？ | 按原文列出适用范围，不推断 |
| 门店销售数据表.xlsx | 表格中有哪些工作表、各有多少条数据？ | 能准确读取表格结构；必要时区分检索问答与精确统计能力 |
| 国双GVP产品及案例介绍.pptx | 文档介绍的 GVP 产品主要能力是什么？ | 引用幻灯片正文，不凭文件名猜测 |
| 亚热带季风气候.doc | 文档如何描述亚热带季风气候的特点？ | 引用 DOC 解析片段 |

已执行首题，但运行故障阻止回答；其余用例尚未执行。目前本次样本无一完成索引，全局问答来源已恢复为外部知识库。不能把模型常识回答视为文档问答通过。
