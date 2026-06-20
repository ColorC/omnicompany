/**
 * entities/review/MaterialDetail — 主详情视图 (verdict 三键+理由输入 / 分级 select /
 * 返回源按钮 / 文本选择定位 / 内容区走 MaterialContentView 统一分发).
 *
 * R2 从 standalone 审阅台剪切而来 (结构搬移, 行为零变化); R4 起 standalone 已退役,
 * 消费方为驾驶舱 review_queue / review_material 面板.
 */

import { useCallback, useState, type ReactNode } from 'react'
import { Check, X } from 'lucide-react'
import type {
  Material,
  MaterialStatus,
  MaterialTier,
  CommentFeedbackStatus,
} from '../../api/reviewstageClient'
import {
  COLORS,
  TIER_LABELS,
  STATUS_LABELS,
  getStructureWarnings,
  type ReviewSource,
} from './shared'
import { MaterialContentView } from './MaterialViews'
import { StructureWarningsBadge } from './MaterialSidebar'
import { useReviewActive } from '../../stores/reviewActiveStore'


// ── 主详情视图 (含 verdict 按钮 + tier 调整) ────────────────────────

export function MaterialDetail({
  material, onVerdict, onCommentSubmit, onFeedbackChange, onTierChange, source, onReturnToSource, compact = false,
  headerLeft, headerActions,
}: {
  material: Material
  onVerdict: (verdict: MaterialStatus, reason: string) => Promise<void>
  onCommentSubmit: (content: string, target?: Record<string, unknown>) => Promise<void>
  onFeedbackChange: (commentId: string, status: CommentFeedbackStatus) => Promise<void>
  onTierChange: (tier: MaterialTier) => Promise<void>
  source: ReviewSource | null
  onReturnToSource: () => void
  compact?: boolean
  /** 消费方(如 review_queue)塞进顶栏左侧的件(如侧栏收起开关)。 */
  headerLeft?: ReactNode
  /** 消费方塞进顶栏右侧的审阅动作(源/在页签打开/归档/删除/刷新), 合并成一层薄顶栏。 */
  headerActions?: ReactNode
}) {
  const [pendingVerdict, setPendingVerdict] = useState<MaterialStatus | null>(null)
  const [reason, setReason] = useState('')
  const structureWarnings = getStructureWarnings(material)
  // 评论已独立成区(C 区: 右栏/次级侧栏), 不再藏在材料面板的切换里。这里只负责正文 +
  // 顶栏审阅动作; 选中正文一段文字 → 写共享 store 的待写锚点, C 区评论框接住(可跨 webview)。
  const setPendingAnchor = useReviewActive((s) => s.setPendingAnchor)
  const setActiveMaterial = useReviewActive((s) => s.setActiveMaterial)

  // html 选元素入口已撤(由 dashboard 全局捕获工具承担); 保留 no-op 满足 MaterialContentView prop。
  const onElementSelect = useCallback(() => {}, [])

  // 选中正文文本 → 作为锚点写进共享 store(评论落每材料 .md 文件, 不发总控)。同时确保 C 区看的是本材料。
  const onTextSelection = useCallback(() => {
    if (material.kind === 'html' || material.kind === 'image') return
    const selectedText = window.getSelection()?.toString().trim()
    if (!selectedText) return
    setActiveMaterial(material.id)
    setPendingAnchor(selectedText.slice(0, 200))
  }, [material.kind, material.id, setActiveMaterial, setPendingAnchor])

  // minHeight:0 必须有：flex 子项默认 min-height:auto 会被长 markdown 撑开，
  // 外层面板 overflow:hidden 直接裁掉 → 整个审阅台滚不动（2026-06-12 用户上报）
  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', background: COLORS.bg, color: COLORS.text, minWidth: 0, minHeight: 0 }} data-testid="material-detail">
      <div style={{
        padding: '6px 12px', borderBottom: `1px solid ${COLORS.border}`,
        display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap',
      }}>
        {headerLeft}
        <div
          style={{ flex: 1, minWidth: 120, display: 'flex', alignItems: 'baseline', gap: 8, overflow: 'hidden' }}
          title={`${material.title} · ${TIER_LABELS[material.tier]} · ${STATUS_LABELS[material.status]}${material.source_plan_id ? ` · plan=${material.source_plan_id}` : ''}${material.pushed_to_user ? ` · 📌${material.pushed_reason || ''}` : ''}`}
        >
          <span data-testid="material-title" style={{ fontSize: 15, fontWeight: 600, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{material.title}</span>
          <span data-testid="material-tier-status" style={{ fontSize: 12, color: COLORS.textDim, flexShrink: 0, whiteSpace: 'nowrap' }}>{TIER_LABELS[material.tier]} · {STATUS_LABELS[material.status]}</span>
        </div>
        {source && (
          <button
            type="button"
            data-testid="review-return-source"
            onClick={onReturnToSource}
            style={{
              padding: '5px 10px',
              background: COLORS.panel,
              color: COLORS.borderActive,
              border: `1px solid ${COLORS.border}`,
              borderRadius: 4,
              cursor: 'pointer',
              fontSize: 14,
            }}
            title={source.title || source.id}
          >
            Return source
          </button>
        )}
        <select
          value={material.tier}
          onChange={(e) => onTierChange(e.target.value as MaterialTier)}
          style={{
            padding: '4px 8px', background: COLORS.panel, color: COLORS.text,
            border: `1px solid ${COLORS.border}`, borderRadius: 4, fontSize: 14,
          }}
          data-testid="tier-select"
        >
          {(['mandatory', 'important', 'processual', 'ignored'] as MaterialTier[]).map(t => (
            <option key={t} value={t}>调级: {TIER_LABELS[t]}</option>
          ))}
        </select>
        <button
          data-testid="verdict-accept"
          onClick={() => onVerdict('accepted', '')}
          disabled={material.status === 'accepted'}
          title={material.status === 'accepted' ? '已通过' : '通过'}
          style={{
            padding: '6px 11px', background: material.status === 'accepted' ? COLORS.border : COLORS.accepted,
            color: '#fff', border: 'none', borderRadius: 4, display: 'inline-flex', alignItems: 'center',
            cursor: material.status === 'accepted' ? 'default' : 'pointer',
          }}
        ><Check size={16} /></button>
        <button
          data-testid="verdict-reject"
          onClick={() => setPendingVerdict('rejected')}
          title="拒绝"
          style={{
            padding: '6px 11px', background: COLORS.rejected,
            color: '#fff', border: 'none', borderRadius: 4, cursor: 'pointer', display: 'inline-flex', alignItems: 'center',
          }}
        ><X size={16} /></button>
        {headerActions}
      </div>

      <StructureWarningsBadge warnings={structureWarnings} />

      {pendingVerdict && (
        <div style={{
          padding: 16, background: '#2d1b3d', borderBottom: `1px solid ${COLORS.border}`,
          display: 'flex', gap: 8, alignItems: 'center',
        }}>
          <span>拒绝 原因:</span>
          <input
            value={reason}
            onChange={e => setReason(e.target.value)}
            placeholder="(可选)"
            data-testid="verdict-reason"
            style={{
              flex: 1, padding: 6, background: COLORS.panel, color: COLORS.text,
              border: `1px solid ${COLORS.border}`, borderRadius: 4,
            }}
          />
          <button
            data-testid="verdict-confirm"
            onClick={async () => {
              await onVerdict(pendingVerdict, reason)
              setPendingVerdict(null); setReason('')
            }}
            style={{
              padding: '6px 14px',
              background: COLORS.rejected,
              color: '#fff', border: 'none', borderRadius: 4,
              cursor: 'pointer',
            }}
          >确认</button>
          <button onClick={() => { setPendingVerdict(null); setReason('') }}
            style={{
              padding: '6px 14px', background: 'transparent', color: COLORS.text,
              border: `1px solid ${COLORS.border}`, borderRadius: 4, cursor: 'pointer',
            }}>取消</button>
        </div>
      )}

      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minHeight: 0 }}>
        <MaterialContentView m={material} onElementSelect={onElementSelect} onTextSelection={onTextSelection} />
      </div>
    </div>
  )
}
