# Knowledge Base Curator Skill

面向系统手册、FAQ、流程图和产品资料的知识库整理 Skill。将原资料核对、图文对应、角色范围、任务分段与交付检查沉淀为可复用流程。

适用于 CRM、SRM、ERP、OA 等系统知识库，也可按型号/规格整理产品知识。不会把示例业务规则套用到其他系统，不会自动替业务人员确认冲突内容，不会自动发布到 Dify。

## 安装

本仓库的 Skill 位于 `skills/knowledge-base-curator`。把该完整目录复制到 Codex 的 `$CODEX_HOME/skills/`；未设置 CODEX_HOME 时使用 `~/.codex/skills/`。也可以让支持 GitHub 安装的技能安装器从本仓库的这个目录安装。

重新打开会话或刷新技能后，使用：

```text
请使用 $knowledge-base-curator，把这些系统手册整理成带来源和配图的知识卡。
适用系统：示例业务系统。
角色：经办人、审核人分别处理。
保留原文件；未知规则列为待确认，输出 Markdown 与完整备份包。
```

## 包含什么

- 证据优先的整理流程与操作/FAQ/流程/产品/规则卡模型。
- DOCX、Markdown、TXT 文本和 DOCX 嵌图提取工具。
- JSON 到 Markdown、离线配图、索引、待确认事项和 ZIP 的确定性打包工具。
- 结构、引用、范围、图片覆盖与原始文件校验。
- 平台无关的验收方法，以及按需使用的 Dify 适配说明。

脚本仅需 Python 3.10+ 标准库。它们不会调用模型、联网、上传或自动识别业务事实。图片阅读、复杂表格与扫描件 OCR 由调用 Skill 的代理使用适合的工具完成。

## 本地演示

```text
python skills/knowledge-base-curator/scripts/extract_sources.py examples/fictional-manual.md --out demo-evidence
python skills/knowledge-base-curator/scripts/validate_kb.py examples/cards.json
python skills/knowledge-base-curator/scripts/package_kb.py examples/cards.json --out demo-output
python -m unittest discover -s tests -v
```

示例全部虚构，用于验证工具行为，不能用作真实系统操作依据。生成目录已加入 .gitignore。

## 能验证与不能验证的事

工具能发现重复 ID、未知来源、错引图片、遗漏图片、非法路径和结构问题；不能证明业务规则正确或线上召回达标。交付报告明确标记是否实际执行检索测试。主 Markdown 没有可用远程图片地址时，会保留本地引用并报告云端图片尚未就绪。

仓库只包含通用 Skill、工具和虚构测试资料，不包含企业原手册、截图或密钥。
