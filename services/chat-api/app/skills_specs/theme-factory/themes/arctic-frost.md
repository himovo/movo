# PPT 主题与视觉规范说明文档

本文档描述 PPT 系统的主题层设计目标、现状问题与下一步扩展方案。重点不是“有多少主题文件”，而是主题是否能真正接管页面视觉，让不同模板不再像同一种毛坯卡片。

## 1. 当前判断

目前模板结构已经较丰富，但主题系统仍偏基础，主要问题有：

1. `page_policy` 过粗。
   例如 `agenda` 目前通常只有 `background_policy / panel / number` 三类控制，导致同一页 4 张卡片容易同色同质。
2. family-level token 不足。
   `agenda`、`summary`、`progress`、`comparison` 等页面家族还缺少“同页内部多角色差异化”能力。
3. icon 只是附加资产，不是页面结构的一等公民。
   系统能规划 `icon_set`，但主题和模板还没有把 icon 变成稳定的视觉构件。
4. 模板和主题解耦不彻底。
   模板负责结构，但主题还没提供足够细的角色定义，导致很多页面虽然结构不同，最终视觉却趋同。

一句话：

**当前系统不是“主题数量少”，而是“主题表达层次不够”。**

---

## 2. 主题设计目标

下一步主题系统应满足以下目标：

1. 同一主题下，不同 page family 应明显不同。
   `cover`、`agenda`、`content`、`comparison`、`progress`、`summary` 应有不同的节奏感。
2. 同一页面内，多张卡片可有层次差异。
   例如 agenda 的 4 张卡，不能全部只是同一个 `surface_primary`。
3. icon、badge、chip、header band、number block 应成为主题控制对象。
4. 模板只描述结构角色，主题决定具体长相。
5. 主题输出应足够细，能支撑后续 HTML -> PPT 映射。

---

## 3. 主题分层模型

建议将主题系统分成 4 层：

### 3.1 Core Semantic Tokens
全局基础语义，不带具体模板含义。

典型包括：
- `canvas_bg`
- `surface_primary`
- `surface_secondary`
- `surface_muted`
- `surface_inverse`
- `text_on_dark`
- `text_on_light`
- `text_on_accent`
- `accent_fill`
- `border_subtle`
- `divider`
- `shadow_soft`
- `shadow_strong`
- `radius_sm / md / lg / pill`

### 3.2 Typography Tokens
统一控制文字层级。

建议包括：
- `hero_title`
- `section_title`
- `subtitle`
- `highlight_statement`
- `body_text`
- `body_bullets`
- `caption_text`
- `eyebrow_label`
- `number_badge_text`

### 3.3 Family Tokens
给页面家族专门提供的视觉角色，不再让所有页面都复用同一块 `surface_primary`。

例如：
- `agenda_card_surface`
- `agenda_card_surface_alt`
- `agenda_card_surface_emphasis`
- `agenda_number_badge`
- `agenda_icon_surface`
- `agenda_header_rule`
- `comparison_header_surface`
- `comparison_cell_surface`
- `progress_stage_surface`
- `progress_note_surface`
- `summary_card_surface`
- `summary_statement_surface`

### 3.4 Page Policy
决定某个 page family 如何组合 token。

例如：
- 背景是否浅色或深色
- 标题用什么文字 token
- 卡片主色和辅助色怎么分配
- 是否启用 icon
- 是否允许多卡片差异化配色

---

## 4. 建议扩展的 Page Policy

当前 `page_policy` 只控制很粗的背景和 panel。建议扩展为：

```json
{
  "agenda": {
    "background_policy": "light_gradient_with_subtle_grid",
    "title_text": "section_title",
    "card_layout_mode": "grid_cards",
    "card_surface_mode": "alternating",
    "card_tokens": [
      "agenda_card_surface",
      "agenda_card_surface_alt",
      "agenda_card_surface",
      "agenda_card_surface_alt"
    ],
    "number_badge": "agenda_number_badge",
    "header_rule": "agenda_header_rule",
    "icon_policy": {
      "enabled": true,
      "source": "icon_set",
      "icon_surface": "agenda_icon_surface",
      "icon_palette_mode": "per_card"
    }
  }
}
```

也就是说，`agenda` 不应只知道“卡片用哪个 panel”，而应知道：
- 卡片是同色还是交替色
- 编号长什么样
- 顶部高亮线长什么样
- icon 是否出现
- icon 的底托和颜色怎么分配

---

## 5. Agenda Family 专项设计

这是当前最需要补强的一类。

### 5.1 Agenda 页面当前问题
- 4 张卡片颜色过于统一
- 没有 icon 或 icon 不进入主结构
- 编号、标题、卡片关系单一
- 页面像“空面板”，不像“章节导航”

### 5.2 Agenda Family 目标效果
- 每张卡可略有差异，但仍保持同主题统一性
- 可以出现 icon、badge、彩色标题条、局部高亮
- 页面的第一眼要让人感知“这是导航页”，而不是内容页

### 5.3 建议新增 Agenda Tokens

| Token | 用途 | 说明 |
| :--- | :--- | :--- |
| `agenda_card_surface` | 主卡面 | Agenda 卡片的基础卡面 |
| `agenda_card_surface_alt` | 交替卡面 | 用于第二、第四张卡等形成节奏 |
| `agenda_card_surface_emphasis` | 强调卡面 | 用于首卡或重点章节卡 |
| `agenda_number_badge` | 编号块 | `01/02/03/04` 的视觉容器 |
| `agenda_header_rule` | 卡片顶部强调线 | 可以是纯色或渐变 |
| `agenda_icon_surface` | icon 底托 | 控制 icon 圆底/方底/胶囊底 |
| `agenda_icon_fill_1~4` | 每卡 icon 色 | 允许同页 4 张卡形成弱差异 |
| `agenda_text_on_card` | 卡片内标题/正文色 | 与卡面联动 |

### 5.4 Agenda Icon Policy

建议把 icon 正式纳入结构化视觉系统：

```json
{
  "icon_policy": {
    "enabled": true,
    "source": "icon_set",
    "placement": "inside_card_header",
    "shape": "pill",
    "size": "sm",
    "palette_mode": "per_card"
  }
}
```

这样 agenda 就不再只是：
- 标题
- 编号
- 两行字

而是：
- 标题
- icon
- 编号
- 章节预告

---

## 6. 预定义主题建议扩展

当前主题文件个数够用，下一步重点不是继续加主题数量，而是补主题内部层次。

### 6.1 每个主题至少应补齐
- 1 套全局 semantic token
- 1 套 typography token
- 1 套 family-level token
- 1 份 page policy
- 1 份 icon palette policy

### 6.2 主题文件建议结构

```json
{
  "id": "ocean-depths",
  "mode": "dark",
  "palette": {},
  "gradients": {},
  "shape": {},
  "elevation": {},
  "typography": {},
  "semantic_tokens": {},
  "family_tokens": {
    "agenda": {},
    "comparison": {},
    "progress": {},
    "summary": {}
  },
  "page_policy": {}
}
```

---

## 7. 令牌体系建议

### 7.1 保留的基础令牌
- `hero_title`
- `section_title`
- `subtitle`
- `highlight_statement`
- `body_text`
- `body_bullets`
- `surface_primary`
- `surface_secondary`
- `surface_muted`
- `accent_fill`
- `border_subtle`
- `background_diagram`

### 7.2 建议新增的全局令牌
- `shadow_soft`
- `shadow_strong`
- `radius_xs`
- `radius_sm`
- `radius_md`
- `radius_lg`
- `radius_pill`
- `eyebrow_label`
- `number_badge_text`

### 7.3 建议新增的 family-level 令牌
- `agenda_card_surface`
- `agenda_card_surface_alt`
- `agenda_card_surface_emphasis`
- `agenda_number_badge`
- `agenda_header_rule`
- `agenda_icon_surface`
- `comparison_header_surface`
- `comparison_row_header_surface`
- `comparison_body_surface`
- `progress_stage_surface`
- `progress_stage_surface_alt`
- `progress_note_surface`
- `summary_card_surface`
- `summary_statement_surface`

---

## 8. 自适应逻辑建议

系统不应只根据 `theme_mode` 做浅深映射，还应根据：
- `page family`
- `layout mode`
- `item count`
- `visual assets`

动态决定某页的 token 组合。

例如：
- 同一套深色主题中
  - `cover` 可深底重氛围
  - `agenda` 可浅底高对比
  - `summary` 可浅底但卡片更重
- 同一页 agenda 中
  - 4 张卡的 header rule 和 icon 可交替色
  - 但正文色和边框逻辑保持统一

---

## 9. 当前建议的优化顺序

如果后续进入实现，建议按这个顺序落地：

1. 扩展 `StylePlanner` 的 `page_policy` 字段
2. 给 `agenda` family 增加专属 token
3. 给 agenda 模板增加 `icon_set` 作为正式可消费结构
4. 让 preview/replay 都只按 family token + page policy 渲染
5. 再扩展 `comparison`、`progress`、`summary`

---

## 10. 当前结论

模板系统已经足够支撑结构变化。

下一阶段真正需要建设的是：

**“主题如何把这些结构装修起来。”**

尤其是：
- family-level token
- page_policy 扩展
- 同页多卡差异化
- icon 进入正式视觉系统

否则再多模板，最终也容易因为主题表达不够而显得同质化。
