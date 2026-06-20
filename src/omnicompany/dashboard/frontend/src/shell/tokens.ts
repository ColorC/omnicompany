/**
 * Design tokens — 唯一视觉真源 (single source of truth).
 *
 * 2026-06 重做: 标准深色主题(参考协作平台深色 / Linear / Notion 深色)。原"纯黑 #08090a + 不及格灰字"
 * 整套换掉 —— 底色提亮分层、所有文字对比度达 WCAG AA(≥4.5:1)、字号地板硬化。
 *
 * 字号标准(地板硬化, 杜绝 11/12px 小字):
 *   small:   13px — 辅助信息 / 时间戳 / 计数 (UI 文字地板, 不再更小)
 *   body:    15px — 正文基准 / 列表项 / 按钮 (整体抬到 15)
 *   doc:     16px — 文档 / 写作正文 (协作平台文档手感)
 *   title:   17px — 段落标题 / 面板标题
 *   heading: 22px — 页面标题
 *   caption: 13px — 仅 1~2 字 badge (历史保留, 已不再用于正文)
 *
 * 字体: UI=Inter→中文回落; 代码/数据=等宽。
 */

// ── 颜色 (标准深色分层, 文字全部 AA) ───────────────────────────────────────
export const colors = {
  // 背景分层: 深 → 浅 (不再纯黑)
  bg:           '#1a1a1c',  // App 底
  bgPanel:      '#202023',  // 面板 / 卡片底
  bgCard:       '#2a2a2e',  // 悬浮卡片 / 输入框
  bgDoc:        '#242428',  // 文档 / 写作区 (像一张"纸", 略亮于面板)
  bgOverlay:    '#2f2f34',  // 遮罩 / 次级表面

  border:       '#38383e',  // 主边框
  borderSubtle: '#2c2c31',  // 更淡分割线

  // 文本层次 (全部 ≥4.5:1 on #1a1a1c)
  text:         '#ededee',  // 主文本 (~13:1)
  textSecondary:'#c4c6cb',  // 次要文本 (~9:1)
  textMuted:    '#a0a3aa',  // 标签 / 描述 (~6:1)
  textFaint:    '#909399',  // 时间戳 / 低优先 (~4.8:1, 地板)
  textGhost:    '#84878e',  // 占位符 (~4.5:1, 占位符也要读得见)

  // 语义强调
  accent:       '#6c78e6',  // 主强调 (填充)
  accentBg:     '#23243a',
  accentLime:   '#e4f222',  // 主操作 (Neon Lime, 深底高对比)
  link:         '#8aa6ff',  // 链接文字 (亮蓝, AA)
  wikilink:     '#8aa6ff',

  // 状态色 (深底 AA)
  success:      '#3fb950',  // Emerald
  warning:      '#f0616d',  // Warning Red
  info:         '#3bc9d8',  // Cyan Spark
  violet:       '#a78bfa',  // Amethyst
} as const

/** Status semantic color map. */
export const statusColor: Record<string, string> = {
  ok: colors.success, pass: colors.success, done: colors.success,
  finished: colors.success, success: colors.success,
  active: '#5aa9f0', running: '#f0a64b',
  pending: colors.textMuted, planned: colors.textMuted,
  paused: '#f0a64b', warn: '#f0a64b', warning: '#f0a64b',
  fail: colors.warning, failed: colors.warning, error: colors.warning,
  cancelled: colors.textMuted, unknown: colors.textFaint,
}

export function statusColorOf(status: string | null | undefined): string {
  if (!status) return statusColor.unknown
  return statusColor[status.toLowerCase()] || statusColor.unknown
}

// ── 间距 (4px 基准, 行内可点区纵向不低于 xs) ───────────────────────────────
export const spacing = {
  xs: 4,
  sm: 8,
  md: 12,
  lg: 16,
  xl: 24,
  xxl: 32,
} as const

// ── 字体 ───────────────────────────────────────────────────────────────
export const fonts = {
  // UI 正文: Inter 优先, 中文回落等线/微软雅黑
  ui: "'Inter', 'Inter Variable', '等线', 'DengXian', '微软雅黑', 'Microsoft YaHei', system-ui, -apple-system, sans-serif",
  // 等宽: Berkeley Mono 优先, 回落 Consolas/Menlo
  mono: "'Berkeley Mono', 'Consolas', 'Menlo', 'Monaco', 'IBM Plex Mono', monospace",
} as const

// ── 字号 (地板硬化) ─────────────────────────────────────────────────────
export const fontSize = {
  caption: 13,    // 仅 1~2 字 badge (历史保留)
  small:   13,    // 辅助信息地板 — 时间戳 / 计数
  body:    15,    // 正文基准 — 列表项 / 按钮 / kv 值
  doc:     16,    // 文档 / 写作正文
  title:   17,    // 段落标题 / 面板标题
  heading: 22,    // 页面标题
} as const

// ── 行高 ───────────────────────────────────────────────────────────────
export const lineHeight = {
  tight: 1.4,   // 密集列表 / 表格下限
  ui:    1.5,   // UI 文本
  doc:   1.6,   // 文档 / 写作
} as const

// ── 圆角 ───────────────────────────────────────────────────────────────
export const radius = {
  tags: 3,
  badges: 4,
  default: 6,   // 卡片 / 按钮 / 输入框
  xl: 12,
} as const
