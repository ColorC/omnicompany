/**
 * entities/review/shared — 审阅台共享纯工具 (设计 token / 标签 / 纯函数).
 *
 * R2 从 standalone 审阅台剪切而来 (结构搬移, 行为零变化); R4 起 standalone 已退役,
 * 消费方为驾驶舱 review_queue / review_material 面板.
 */

import type * as React from 'react'
import type {
  Material,
  MaterialKind,
  MaterialStatus,
  MaterialTier,
  CommentFeedbackStatus,
} from '../../api/reviewstageClient'
import type { EntitySearchResult } from '../../api/entitiesClient'

// ── 设计 token ──────────────────────────────────────────────────────
export const COLORS = {
  bg: '#0d1117',
  panel: '#161b22',
  panelHover: '#1c2128',
  border: '#30363d',
  borderActive: '#58a6ff',
  text: '#e6edf3',
  textDim: '#8b949e',
  // tier 色
  mandatory: '#f85149',
  important: '#d29922',
  processual: '#8b949e',
  ignored: '#484f58',
  // status 色
  pending: '#d29922',
  accepted: '#3fb950',
  rejected: '#f85149',
  blocked: '#a371f7',
}

export interface StructureWarning {
  code?: string
  severity?: string
  message?: string
  path?: string
}

export function getStructureWarnings(material: Material): StructureWarning[] {
  const raw = material.extra?.structure_warnings
  if (!Array.isArray(raw)) return []
  return raw.filter((item): item is StructureWarning => !!item && typeof item === 'object')
}

export interface EntityMention {
  uri: string
  display: string
  kind: string
  id: string
  title: string
}

export function getTargetMentions(target: Record<string, unknown> | undefined): EntityMention[] {
  const raw = target?.mentions
  if (!Array.isArray(raw)) return []
  return raw.filter((item): item is EntityMention =>
    !!item &&
    typeof item === 'object' &&
    typeof (item as any).uri === 'string' &&
    typeof (item as any).display === 'string',
  )
}

export function mentionFromResult(item: EntitySearchResult): EntityMention {
  return {
    uri: item.uri,
    display: item.display,
    kind: item.kind,
    id: item.id,
    title: item.title,
  }
}

export function findMentionQuery(text: string, caret: number): { start: number; query: string } | null {
  const before = text.slice(0, caret)
  const at = before.lastIndexOf('@')
  if (at < 0) return null
  if (at > 0 && /\S/.test(before[at - 1])) return null
  const query = before.slice(at + 1)
  if (/\s/.test(query) || query.length > 80) return null
  return { start: at, query }
}

export const TIER_LABELS: Record<MaterialTier, string> = {
  mandatory: '必验收',
  important: '重要',
  processual: '过程性',
  ignored: '其余',
}

export const STATUS_LABELS: Record<MaterialStatus, string> = {
  pending: '待审',
  accepted: '已通过',
  rejected: '已拒绝',
  blocked: '已阻断',
}

export const FEEDBACK_LABELS: Record<CommentFeedbackStatus, string> = {
  delivered: '已送达',
  read: '已读',
  to_todo: '转 todo',
  todo_done: 'todo 完成',
}

export const KIND_LABELS: Record<MaterialKind, string> = {
  image: '图',
  markdown: '文档',
  html: '网页',
  key_question: '关键问题',
  custom_web_template: '自定义模板',
}

// 审阅来源 (从哪里进入 material 详情, "返回源"按钮用)
export interface ReviewSource {
  type: string
  id: string
  title?: string
}

// ── Helpers ─────────────────────────────────────────────────────────

export function batchButtonStyle(background: string): React.CSSProperties {
  return {
    minHeight: 28,
    padding: '5px 10px',
    background,
    color: '#fff',
    border: `1px solid ${COLORS.border}`,
    borderRadius: 4,
    cursor: 'pointer',
    fontSize: 14,
  }
}

export function tierColor(t: MaterialTier): string {
  return COLORS[t] || COLORS.ignored
}

export function statusColor(s: MaterialStatus): string {
  return COLORS[s] || COLORS.textDim
}

export function formatTs(iso: string): string {
  try {
    const d = new Date(iso)
    return d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', second: '2-digit' })
  } catch { return iso }
}
