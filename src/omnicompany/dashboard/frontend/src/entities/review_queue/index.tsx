import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { ExternalLink, FileSearch, RefreshCw, Archive, ArchiveRestore, Trash2, Crosshair } from 'lucide-react'
import { VscodeIcon } from '../../components/VscodeIcon'
import { postHostMessage, isInWebview } from '../../lib/surface'
import {
  reviewstageApi,
  type Material,
  type MaterialStats,
  type MaterialStatus,
  type MaterialTier,
  type CommentFeedbackStatus,
} from '../../api/reviewstageClient'
import type { Entity } from '../types'
import type { EntityRegistration, EntityResolver } from '../registry'
import { usePanels } from '../../stores/panelsStore'
import { useReviewQueueFocus } from '../../stores/reviewQueueFocusStore'
import { MaterialDetail, MaterialSidebar } from '../review'
import { useReviewStream } from '../review/streamStore'
import { materialTabTitle } from '../review_material'
import { VSplitter } from '../../shell/Splitter'

export interface ReviewQueueEntity extends Entity {
  type: 'review_queue'
}

const SINGLE: ReviewQueueEntity = {
  type: 'review_queue',
  id: 'main',
  title: 'Review Queue',
  tags: ['boss-sight', 'review'],
}

const resolver: EntityResolver<ReviewQueueEntity> = {
  type: 'review_queue',
  async fetch(id) {
    if (id === 'main') return SINGLE
    throw new Error(`review_queue: unknown id ${id}`)
  },
  async list() {
    return [SINGLE]
  },
}

const S: Record<string, any> = {
  root: { height: '100%', minHeight: 0, display: 'grid', gridTemplateRows: 'auto auto minmax(0, 1fr)', background: '#0a0d12', color: '#e6edf3', fontFamily: 'Consolas, Menlo, monospace', overflow: 'hidden' },
  header: { padding: '10px 12px', borderBottom: '1px solid #1f2937', display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12 },
  title: { color: '#9fd0ff', fontSize: 15, fontWeight: 700 },
  subtitle: { color: '#8b949e', fontSize: 14, marginTop: 3 },
  toolbar: { padding: 10, borderBottom: '1px solid #1f2937', display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' },
  button: { border: '1px solid #2b3a49', background: '#101820', color: '#dbe7f3', borderRadius: 4, padding: '6px 9px', cursor: 'pointer', display: 'inline-flex', alignItems: 'center', gap: 6, fontSize: 14 },
  danger: { border: '1px solid #7f1d1d', background: '#2a1010', color: '#ffb4b4', borderRadius: 4, padding: '6px 9px', cursor: 'pointer', display: 'inline-flex', alignItems: 'center', gap: 6, fontSize: 14 },
  tab: (active: boolean): React.CSSProperties => ({ border: `1px solid ${active ? '#2f81f7' : '#2b3a49'}`, background: active ? '#10233f' : '#101820', color: active ? '#79c0ff' : '#b7c8d9', borderRadius: 4, padding: '5px 8px', cursor: 'pointer', fontSize: 14 }),
  // R5: 筛选移进侧栏(紧凑), 顶栏只剩一层(MaterialDetail 头, 含审阅动作)。
  filterRow: { display: 'flex', gap: 5, flexWrap: 'wrap', padding: '8px 8px 6px', borderBottom: '1px solid #1f2937' },
  tabSm: (active: boolean): React.CSSProperties => ({ border: `1px solid ${active ? '#2f81f7' : '#2b3a49'}`, background: active ? '#10233f' : '#101820', color: active ? '#79c0ff' : '#b7c8d9', borderRadius: 4, padding: '2px 7px', cursor: 'pointer', fontSize: 13 }),
  iconBtn: { border: '1px solid #2b3a49', background: '#101820', color: '#dbe7f3', borderRadius: 4, padding: '4px 8px', cursor: 'pointer', fontSize: 13, display: 'inline-flex', alignItems: 'center', gap: 4 },
  // R4: 两栏从固定 grid 改 flex, 中间插 VSplitter 拖拽调宽(左列像素宽走 state)。
  body: { minHeight: 0, display: 'flex', overflow: 'hidden' },
  // R3.5: 左列换成共享 MaterialSidebar(entities/review, compact 撑满本列), 边框由本容器给。
  list: { minHeight: 0, overflow: 'hidden', display: 'flex', borderRight: '1px solid #1f2937' },
  // R3.5: 右列换成共享 MaterialDetail(与 review_material 面板同一份), 上方留一条
  // review_queue 特有动作(Source/归档/删除/web 页签/Detail 页签)。
  detail: { minHeight: 0, display: 'flex', flexDirection: 'column', overflow: 'hidden' },
  actionStrip: { display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap', padding: '8px 10px', borderBottom: '1px solid #1f2937' },
  empty: { padding: 18, color: '#8b949e' },
  error: { padding: '8px 12px', color: '#ff7b72', borderBottom: '1px solid #1f2937', background: '#160d0d' },
}

type ReviewFilter = 'all' | 'archived' | MaterialStatus

const FILTERS: Array<{ key: ReviewFilter; label: string }> = [
  { key: 'pending', label: 'Pending' },
  { key: 'blocked', label: 'Blocked' },
  { key: 'rejected', label: 'Rejected' },
  { key: 'accepted', label: 'Accepted' },
  { key: 'all', label: 'All' },
  { key: 'archived', label: '已归档' },
]

function webReviewTargetId(m: Material): string | null {
  const explicit = m.extra?.web_review_id
  if (typeof explicit === 'string' && explicit.trim()) return explicit.trim()
  const liveUrl = typeof m.extra?.live_url === 'string' ? m.extra.live_url : ''
  if (liveUrl.startsWith('/walker-game')) return 'walker-game'
  if (liveUrl.startsWith('/vilo-demo')) return 'vilo-demo'
  return null
}

function errText(e: unknown): string {
  return String(e instanceof Error ? e.message : e)
}

function ReviewQueuePanel({ initialSelectedId, focusNonce }: { initialSelectedId?: string; focusNonce?: number }) {
  const [filter, setFilter] = useState<ReviewFilter>(initialSelectedId ? 'all' : 'pending')
  const [leftWidth, setLeftWidth] = useState(360)
  const [sidebarOpen, setSidebarOpen] = useState(true)
  const [items, setItems] = useState<Material[]>([])
  const [stats, setStats] = useState<MaterialStats | null>(null)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [bulkIds, setBulkIds] = useState<string[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const openTab = usePanels((s) => s.openTab)

  const selected = useMemo(() => items.find((item) => item.id === selectedId) || items[0] || null, [items, selectedId])
  const selectedWebReviewId = selected ? webReviewTargetId(selected) : null

  const load = () => {
    setLoading(true)
    setError(null)
    Promise.all([
      reviewstageApi.list(
        filter === 'all' ? {} : filter === 'archived' ? { archived_only: true } : { status: filter },
      ),
      reviewstageApi.stats(),
    ])
      .then(([list, nextStats]) => {
        setItems(list.items || [])
        setStats(nextStats)
        setSelectedId((prev) => {
          if (prev && list.items.some((item) => item.id === prev)) return prev
          if (initialSelectedId && list.items.some((item) => item.id === initialSelectedId)) return initialSelectedId
          return list.items[0]?.id || null
        })
        setBulkIds((prev) => prev.filter((id) => list.items.some((item) => item.id === id)))
      })
      .catch((e) => setError(errText(e)))
      .finally(() => setLoading(false))
  }

  useEffect(() => {
    load()
  }, [filter, initialSelectedId])

  // R3: WS 实时流。连接生命周期在 streamStore(引用计数, 不受本面板 onlyWhenVisible
  // 卸载牵连); 这里只订阅 version, 每个流事件触发一次重拉(带当前 filter 的服务端过滤
  // + stats)。手动 Refresh 按钮保留。
  const streamVersion = useReviewStream((s) => s.version)
  useEffect(() => useReviewStream.getState().acquire(), [])
  useEffect(() => {
    if (streamVersion > 0) load()
  }, [streamVersion])

  // 单例 tab 下被要求聚焦某材料(点不同材料链接): 切到 All 并选中它。focusNonce 让同一材料再次点击也重聚焦。
  useEffect(() => {
    if (!initialSelectedId) return
    setSelectedId(initialSelectedId)
    setFilter('all')
  }, [initialSelectedId, focusNonce])

  const replaceItem = (updated: Material) => {
    setItems((prev) => prev.map((item) => item.id === updated.id ? updated : item))
  }

  // R3.5: 明细操作走共享 MaterialDetail 的回调形状(与 review_material 面板同源)。
  const onVerdict = useCallback(async (verdict: MaterialStatus, reason: string) => {
    if (!selected) return
    setError(null)
    try {
      replaceItem(await reviewstageApi.setVerdict(selected.id, verdict, reason || 'cockpit review queue'))
      setStats(await reviewstageApi.stats())
    } catch (e) {
      setError(`verdict 失败: ${errText(e)}`)
    }
  }, [selected])

  const onCommentSubmit = useCallback(async (content: string, target?: Record<string, unknown>) => {
    if (!selected) return
    setError(null)
    try {
      // 评论进审阅台 → comment_added → reviewstage.comment → ControllerWaker 唤起唯一总控
      // (P1 已验证), 人↔总控反馈闭环在驾驶舱内闭合。
      await reviewstageApi.addComment(selected.id, content, target)
      replaceItem(await reviewstageApi.get(selected.id))
    } catch (e) {
      setError(`评论失败: ${errText(e)}`)
    }
  }, [selected])

  const onFeedbackChange = useCallback(async (commentId: string, status: CommentFeedbackStatus) => {
    if (!selected) return
    setError(null)
    try {
      await reviewstageApi.setCommentFeedback(selected.id, commentId, status)
      replaceItem(await reviewstageApi.get(selected.id))
    } catch (e) {
      setError(`反馈状态失败: ${errText(e)}`)
    }
  }, [selected])

  const onTierChange = useCallback(async (tier: MaterialTier) => {
    if (!selected) return
    setError(null)
    try {
      replaceItem(await reviewstageApi.setTier(selected.id, tier))
      setStats(await reviewstageApi.stats())
    } catch (e) {
      setError(`调级失败: ${errText(e)}`)
    }
  }, [selected])

  // R3.5: 多选批量(共享 BatchReviewToolbar 内嵌在 MaterialSidebar)。
  const toggleBulkId = useCallback((id: string) => {
    setBulkIds((prev) => prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id])
  }, [])

  const runBatch = async (fn: () => Promise<unknown>) => {
    if (bulkIds.length === 0) return
    setError(null)
    try {
      await fn()
      setBulkIds([])
      load()
    } catch (e) {
      setError(`批量操作失败: ${errText(e)}`)
    }
  }
  const onBatchVerdict = (verdict: MaterialStatus) => { void runBatch(() => reviewstageApi.batchVerdict(bulkIds, verdict, `batch ${verdict}`)) }
  const onBatchTier = (tier: MaterialTier) => { void runBatch(() => reviewstageApi.batchTier(bulkIds, tier)) }
  const onBatchDelete = () => { void runBatch(() => reviewstageApi.batchDelete(bulkIds, true)) }

  const setArchivedSelected = async (archived: boolean) => {
    if (!selected) return
    setError(null)
    try {
      await reviewstageApi.setArchived(selected.id, archived)
      // 归档后(在非归档视图)它会从列表消失; 还原后(在已归档视图)同理。重载列表。
      setSelectedId(null)
      load()
    } catch (e) {
      setError(errText(e))
    }
  }

  const deleteSelected = async () => {
    if (!selected) return
    if (typeof window !== 'undefined' && !window.confirm('删除这条审阅材料? 不可恢复(会删文件)。如只想隐藏请用"归档"。')) return
    setError(null)
    try {
      await reviewstageApi.remove(selected.id)
      setSelectedId(null)
      load()
    } catch (e) {
      setError(errText(e))
    }
  }

  const openSource = () => {
    if (!selected) return
    if (selected.source_plan_id) {
      openTab({ type: 'plan', id: selected.source_plan_id }, selected.source_plan_id)
    } else if (selected.source_subagent_id) {
      openTab({ type: 'cc_session', id: selected.source_subagent_id }, selected.source_subagent_id)
    }
  }

  const showSidebar = sidebarOpen || !selected

  // 审阅材料动作(并进 MaterialDetail 那层薄顶栏)。全改 icon + 悬停 tooltip —— 人不靠文字认世界(用户 2026-06-14)。
  const reviewActions = selected ? (
    <>
      {/* 在 VSCode 编辑页签打开本材料(不必先用页签打开, desk 里直接就有, 仅 icon)。 */}
      {isInWebview() && (
        <button type="button" style={S.iconBtn} data-testid="review-queue-open-vscode" title="在 VSCode 编辑页签打开(仅正文+操作)"
          onClick={() => postHostMessage({ type: 'open-material-native', materialId: selected.id, title: selected.title })}>
          <VscodeIcon size={15} />
        </button>
      )}
      {(selected.source_plan_id || selected.source_subagent_id) && (
        <button type="button" style={S.iconBtn} onClick={openSource} data-testid="review-queue-source" title="跳到源(计划/会话)"><Crosshair size={15} /></button>
      )}
      {selected.archived ? (
        <button type="button" style={S.iconBtn} onClick={() => { void setArchivedSelected(false) }} data-testid="review-queue-unarchive" title="取消归档"><ArchiveRestore size={15} /></button>
      ) : (
        <button type="button" style={S.iconBtn} onClick={() => { void setArchivedSelected(true) }} data-testid="review-queue-archive" title="归档"><Archive size={15} /></button>
      )}
      <button type="button" style={S.danger} onClick={() => { void deleteSelected() }} data-testid="review-queue-delete" title="删除(不可恢复, 会删文件)"><Trash2 size={15} /></button>
      {/* "在页签打开": 有 live 网页就开网页本体页签, 否则开材料独立页签(仅 icon)。 */}
      <button type="button" style={S.iconBtn} data-testid="review-queue-open-detail-tab" title={selectedWebReviewId ? '在页签打开网页本体' : '在页签打开材料'}
        onClick={() => selectedWebReviewId
          ? openTab({ type: 'web_review', id: selectedWebReviewId }, selected.title)
          : openTab({ type: 'review_material', id: selected.id }, materialTabTitle(selected.title))}>
        {selectedWebReviewId ? <ExternalLink size={15} /> : <FileSearch size={15} />}
      </button>
    </>
  ) : null

  const collapseToggle = (
    <button type="button" style={S.iconBtn} onClick={() => setSidebarOpen((v) => !v)} data-testid="review-queue-toggle-sidebar"
      title={sidebarOpen ? '收起列表' : '展开列表'}>{sidebarOpen ? '◀' : '▶'}</button>
  )

  return (
    <div style={{ height: '100%', minHeight: 0, display: 'flex', flexDirection: 'column', background: '#0a0d12', color: '#e6edf3', fontFamily: 'Consolas, Menlo, monospace', overflow: 'hidden' }} data-testid="review-queue-panel">
      {error && <div style={S.error} data-testid="review-queue-error">{error}</div>}
      <div style={{ flex: 1, display: 'flex', minHeight: 0 }}>
        {showSidebar && (
          <div style={{ ...S.list, flexDirection: 'column', width: leftWidth, flexShrink: 0 }}>
            <div style={S.filterRow}>
              {FILTERS.map((f) => (
                <button key={f.key} type="button" style={S.tabSm(filter === f.key)} onClick={() => setFilter(f.key)}>{f.label}</button>
              ))}
              <button type="button" style={{ ...S.iconBtn, marginLeft: 'auto', padding: '2px 6px' }} onClick={load} data-testid="review-queue-refresh" title="刷新">
                <RefreshCw size={13} />
              </button>
            </div>
            <MaterialSidebar
              materials={items}
              selectedId={selected?.id || null}
              selectedIds={bulkIds}
              onSelect={setSelectedId}
              onToggleSelect={toggleBulkId}
              onBatchVerdict={onBatchVerdict}
              onBatchTier={onBatchTier}
              onBatchDelete={onBatchDelete}
              onClearBatch={() => setBulkIds([])}
              stats={stats}
              compact
            />
          </div>
        )}
        {showSidebar && <VSplitter side="right" onResize={(d) => setLeftWidth((w) => Math.max(240, Math.min(820, w + d)))} />}
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0, minHeight: 0 }} data-testid="review-queue-detail">
          {!selected && <div style={S.empty}>选择一条审阅材料。</div>}
          {selected && (
            <MaterialDetail
              material={selected}
              headerLeft={collapseToggle}
              headerActions={reviewActions}
              onVerdict={onVerdict}
              onCommentSubmit={onCommentSubmit}
              onFeedbackChange={onFeedbackChange}
              onTierChange={onTierChange}
              source={null}
              onReturnToSource={() => { /* 已在队列里 */ }}
            />
          )}
        </div>
      </div>
    </div>
  )
}

const Editor: React.FC<{ entity: ReviewQueueEntity; facet?: string }> = ({ facet }) => {
  // 聚焦哪条材料走 store(单例 tab, 不靠 facet 拼 tab id)。facet 作首开兜底。
  const focusedId = useReviewQueueFocus((s) => s.focusedId)
  const nonce = useReviewQueueFocus((s) => s.nonce)
  return <ReviewQueuePanel initialSelectedId={focusedId ?? facet} focusNonce={nonce} />
}

export const reviewQueueRegistration: EntityRegistration<ReviewQueueEntity> = {
  resolver,
  renderer: { type: 'review_queue', Editor },
  label: 'Review Queue',
  icon: 'R',
}
