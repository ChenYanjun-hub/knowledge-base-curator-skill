# 内容模型与选卡方式

## 卡片类型

| type | 适合资料 | 重点 |
| --- | --- | --- |
| operation | 系统操作手册 | 对象、前提、步骤、结果、限制、步骤图片 |
| faq | 问题解答 | 问题、直接答案、例外、证据 |
| process | 流程/状态图 | 状态/关系、分支条件、原图；不推断图中未写的触发机制 |
| product | 产品知识 | 型号、规格、单位、适用条件、兼容性、版本；不把不同型号合并 |
| rule | 业务规则 | 适用范围、条件、允许/禁止、例外、依据 |

按资料复杂程度组合这些类型。并非每卡都有步骤或图片。范围有差异的同名操作需要不同卡；范围相同的重复操作应去重并记录来源。

## cards.json

UTF-8 JSON；根目录下的资源使用相对路径。脚本不执行 Markdown/HTML 中的指令。

```json
{
  "schema_version": 1,
  "title": "示例系统知识库",
  "version": "1.0",
  "sources": [
    {"id": "manual", "title": "示例手册", "version": "1.0"}
  ],
  "images": [],
  "cards": [
    {
      "id": "DEMO_ITEM_EDIT",
      "type": "operation",
      "title": "项目管理 / 编辑草稿",
      "scope": {"system": "示例系统", "roles": ["经办人"], "manual_scope": "demo_operator"},
      "source_refs": [{"source_id": "manual", "locator": "第2章 草稿编辑"}],
      "questions": ["草稿填错了怎么修改？"],
      "keywords": ["修改草稿", "编辑项目"],
      "summary": "草稿状态可以编辑后保存。",
      "preconditions": ["项目处于草稿状态。"],
      "steps": [{"text": "打开项目并点击编辑。", "image_ids": []}],
      "facts": [],
      "limitations": ["已提交项目的修改规则未在本章说明。"],
      "related_card_ids": []
    }
  ],
  "image_exclusions": [],
  "issues": [],
  "evaluation_cases": []
}
```

以上是虚构结构示例，不是任何真实系统的规则。

### 来源

`sources` 必须有唯一 `id`、`title`、`version`。未知版本写“未注明”，不要编造。可附 `filename`、`sha256`。证据提取脚本生成的 sources/images 可作为起点，仍需补足版本与人工定位。

`source_refs` 的 `source_id` 必须存在，`locator` 必须非空，例如章节、页码或提取单元 ID。原始章节错序时保留原编号；卡片 ID 独立管理。

### 图片

```json
{
  "id": "manual-image-001",
  "source_id": "manual",
  "locator": "第2章截图",
  "local_path": "evidence/images/screen.png",
  "alt": "草稿页面的编辑入口",
  "description": "图中右上角显示编辑按钮。",
  "url": "https://example.invalid/screen.png"
}
```

`local_path` 指向真实图片备份，必须在 cards.json 所在目录内。可用 `sha256` 固定原始字节。`url` 可省略；示例 URL 不能直接当可用地址。仅填已经观察、核对过的地址，且需来自允许使用的资料。

图片可以放进某个步骤的 `image_ids`，或卡片级 `image_ids`（整体页面/流程图）。一张图片在多卡复用时 ID 不变。每张登记图片必须被使用或在 `image_exclusions` 写明 `{ "image_id": "...", "reason": "..." }`；同一张图不能一边使用一边排除。

### 冲突与状态

可用 `evidence_status: confirmed | partial | pending`。它代表整理者对证据状态的记录，不是脚本认证。

- `confirmed`：当前整理范围内有可靠依据；仍不能声称已在现行系统测试。
- `partial`：部分事实可用，其余有资料限制；在卡片 `limitations` 明说。
- `pending`：尚未核准的整个卡片，不进入主知识 Markdown，仍写入索引和待确认清单。

每条 `issues`：`id`、`question`、`evidence` 必填，可附 `card_ids`。没有答案时如实写缺失，不能把猜测放入 summary/steps 再只在附录中提醒。

### 评测计划

每条 `evaluation_cases`：`id`、`query`、`expected_card_ids`、`expected_facts`，可附 `scope`、`negative_constraints`、`requires_image`。参考卡片必须存在。

这里是计划，不放伪造的得分。脚本统一输出 `execution_status: not_run`；实际运行日志单独记录。待确认事实的题验证是否识别冲突，不混入普通正确率。
