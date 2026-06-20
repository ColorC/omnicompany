/**
 * entities/review/MaterialSidebar — 列表 sidebar + 批量操作工具条 + 结构警告徽标.
 *
 * R2 从 standalone 审阅台剪切而来 (结构搬移, 行为零变化); R4 起 standalone 已退役,
 * 消费方为驾驶舱 review_queue / review_material 面板.
 */

import { useMemo } from 'react'
import type {
  Material,
  MaterialStatus,
  MaterialTier,
  MaterialStats,
} from '../../api/reviewstageClient'
import {
  COLORS,
  TIER_LABELS,
  STATUS_LABELS,
  KIND_LABELS,
  type StructureWarning,
  batchButtonStyle,
  tierColor,
  statusColor,
} from './shared'


// ── 列表 sidebar (按 tier 分组, 必验收 sticky) ──────────────────────

export function BatchReviewToolbar({
  count, onAccept, onReject, onBlock, onTier, onDelete, onClear,
}: {
  count: number
  onAccept: () => void
  onReject: () => void
  onBlock: () => void
  onTier: (tier: MaterialTier) => void
  onDelete: () => void
  onClear: () => void
}) {
  if (count === 0) return null
  return (
    <div
      data-testid="review-batch-toolbar"
      style={{
        display: 'flex', alignItems: 'center', gap: 8, padding: '7px 12px',
        borderBottom: `1px solid ${COLORS.border}`, background: '#101820',
        color: COLORS.text, fontSize: 14, flexWrap: 'wrap',
      }}
    >
      <span>已选 {count}</span>
      <button type="button" onClick={onAccept} style={batchButtonStyle(COLORS.accepted)}>通过</button>
      <button type="button" onClick={onReject} style={batchButtonStyle(COLORS.rejected)}>拒绝</button>
      <button type="button" onClick={onBlock} style={batchButtonStyle(COLORS.blocked)}>阻断</button>
      <select
        onChange={(e) => {
          const value = e.target.value as MaterialTier | ''
          if (value) onTier(value)
          e.currentTarget.value = ''
        }}
        defaultValue=""
        style={{ background: COLORS.panel, color: COLORS.text, border: `1px solid ${COLORS.border}`, borderRadius: 4, padding: '3px 6px', fontSize: 14 }}
      >
        <option value="">调级...</option>
        {(['mandatory', 'important', 'processual', 'ignored'] as MaterialTier[]).map(t => (
          <option key={t} value={t}>{TIER_LABELS[t]}</option>
        ))}
      </select>
      <button type="button" onClick={onDelete} style={batchButtonStyle('#30363d')}>删除</button>
      <button type="button" onClick={onClear} style={batchButtonStyle('transparent')}>清空</button>
    </div>
  )
}


export function MaterialSidebar({
  materials, selectedId, selectedIds, onSelect, onToggleSelect,
  onBatchVerdict, onBatchTier, onBatchDelete, onClearBatch, stats, compact = false,
}: {
  materials: Material[]
  selectedId: string | null
  selectedIds: string[]
  onSelect: (id: string) => void
  onToggleSelect: (id: string) => void
  onBatchVerdict: (verdict: MaterialStatus) => void
  onBatchTier: (tier: MaterialTier) => void
  onBatchDelete: () => void
  onClearBatch: () => void
  stats: MaterialStats | null
  compact?: boolean
}) {
  // 按 tier 分组 — 必验收最上
  const groups = useMemo(() => {
    const g: Record<MaterialTier, Material[]> = {
      mandatory: [], important: [], processual: [], ignored: [],
    }
    for (const m of materials) {
      g[m.tier].push(m)
    }
    return g
  }, [materials])

  return (
    <div style={{
      width: compact ? '100%' : 320,
      borderRight: compact ? 'none' : `1px solid ${COLORS.border}`,
      display: 'flex', flexDirection: 'column',
      background: COLORS.panel, color: COLORS.text,
      minWidth: 0,
    }} data-testid="material-sidebar">
      {/* 无主标题/分组标题层(2026-06-14 用户: 没看到材料就先吃掉 1/5 空间)。tier 已由卡片左侧色条表达;
          唯一保留的"必验收待审"红字仅在真有未决必验收时冒出来, 是信号不是标题。 */}
      {stats && stats.mandatory_unaccepted > 0 && (
        <div style={{ padding: '4px 12px', fontSize: 13, color: COLORS.mandatory, fontWeight: 600 }} data-testid="stats-mandatory-unaccepted">
          ⚠ {stats.mandatory_unaccepted} 必验收待审
        </div>
      )}
      <BatchReviewToolbar
        count={selectedIds.length}
        onAccept={() => onBatchVerdict('accepted')}
        onReject={() => onBatchVerdict('rejected')}
        onBlock={() => onBatchVerdict('blocked')}
        onTier={onBatchTier}
        onDelete={onBatchDelete}
        onClear={onClearBatch}
      />
      <div style={{ flex: 1, overflowY: 'auto' }}>
        {(['mandatory', 'important', 'processual', 'ignored'] as MaterialTier[]).map((tier) => {
          const items = groups[tier]
          if (items.length === 0) return null
          return (
            <div key={tier}>
              {items.map((m) => {
                const selected = selectedId === m.id
                return (
                  <div
                    key={m.id}
                    data-testid={`material-card-${m.id}`}
                    onClick={() => onSelect(m.id)}
                    style={{
                      padding: '10px 16px',
                      cursor: 'pointer',
                      background: selected ? '#1c2c45' : 'transparent',
                      borderLeft: `3px solid ${tierColor(m.tier)}`,
                      borderBottom: `1px solid ${COLORS.border}`,
                      position: 'relative',
                    }}
                  >
                    <div style={{
                      display: 'flex', justifyContent: 'space-between', gap: 8,
                      fontSize: 15, fontWeight: selected ? 600 : 400,
                    }}>
                      <input
                        type="checkbox"
                        checked={selectedIds.includes(m.id)}
                        onChange={(e) => { e.stopPropagation(); onToggleSelect(m.id) }}
                        onClick={(e) => e.stopPropagation()}
                        aria-label={`select ${m.title}`}
                        style={{ margin: 0, flexShrink: 0 }}
                      />
                      <span style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                        {m.title}
                      </span>
                      <span style={{
                        fontSize: 14, padding: '1px 6px', borderRadius: 8,
                        background: statusColor(m.status), color: '#fff',
                      }}>
                        {STATUS_LABELS[m.status]}
                      </span>
                    </div>
                    <div style={{ fontSize: 14, color: COLORS.textDim, marginTop: 4, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={m.source_plan_id || undefined}>
                      {KIND_LABELS[m.kind]}
                      {m.source_plan_id && <span> · {m.source_plan_id}</span>}
                      {m.pushed_to_user && <span style={{ color: COLORS.important, marginLeft: 6 }}>📌</span>}
                    </div>
                  </div>
                )
              })}
            </div>
          )
        })}
        {materials.length === 0 && (
          <div style={{ padding: 24, color: COLORS.textDim, textAlign: 'center', fontSize: 15 }}>
            还没有 material. 跟总控对话, 让它派 subagent 干活并产出.
          </div>
        )}
      </div>
    </div>
  )
}


// ── 结构警告徽标 (MaterialDetail 头部下方) ──────────────────────────

export function StructureWarningsBadge({ warnings }: { warnings: StructureWarning[] }) {
  if (warnings.length === 0) return null
  return (
    <details
      data-testid="structure-warnings"
      style={{
        margin: '8px 20px 0',
        border: `1px solid ${COLORS.border}`,
        borderRadius: 4,
        background: '#1b1a12',
        color: COLORS.text,
        fontSize: 14,
      }}
    >
      <summary style={{
        cursor: 'pointer',
        padding: '6px 10px',
        color: COLORS.important,
        fontWeight: 600,
      }}>
        结构警告 ({warnings.length})
      </summary>
      <div style={{ padding: '0 10px 8px', display: 'grid', gap: 6 }}>
        {warnings.map((w, i) => (
          <div key={`${w.code || 'warning'}-${i}`} style={{ color: COLORS.textDim, lineHeight: 1.5 }}>
            <span style={{ color: COLORS.text }}>{w.code || 'warning'}</span>
            {w.path && <span> · {w.path}</span>}
            <span> · {w.message || 'structure warning'}</span>
          </div>
        ))}
      </div>
    </details>
  )
}
