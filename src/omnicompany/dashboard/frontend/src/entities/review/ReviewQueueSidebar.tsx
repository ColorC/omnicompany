/**
 * entities/review/ReviewQueueSidebar — 审阅材料列表(唯一真源)。
 *
 * 用户 2026-06-14: 列表收敛成一个, 放驾驶舱左栏(取代原 mini ReviewMaterialQueuePanel);
 * 点材料 = 出正文页签(B 区)+ 联动评论(C 区), 不再有"页面内的第二个侧栏"。
 * 这里 = 完整 MaterialSidebar(分组/批量/统计)+ 筛选条 + 数据/WS 接线, 选中项跟随
 * 共享 store 的"激活材料"。VSCode 原生形态(surface=queue)也复用本组件挂进主侧栏。
 */
import React, { useCallback, useEffect, useState } from 'react'
import { RefreshCw } from 'lucide-react'
import {
  reviewstageApi,
  type Material,
  type MaterialStats,
  type MaterialStatus,
  type MaterialTier,
} from '../../api/reviewstageClient'
import { MaterialSidebar } from './MaterialSidebar'
import { useReviewStream } from './streamStore'
import { useReviewActive } from '../../stores/reviewActiveStore'
import { COLORS } from './shared'

type ReviewFilter = 'all' | 'archived' | MaterialStatus

const FILTERS: Array<{ key: ReviewFilter; label: string }> = [
  { key: 'pending', label: 'Pending' },
  { key: 'blocked', label: 'Blocked' },
  { key: 'rejected', label: 'Rejected' },
  { key: 'accepted', label: 'Accepted' },
  { key: 'all', label: 'All' },
  { key: 'archived', label: '已归档' },
]

const tabSm = (active: boolean): React.CSSProperties => ({
  border: `1px solid ${active ? '#2f81f7' : '#2b3a49'}`, background: active ? '#10233f' : '#101820',
  color: active ? '#79c0ff' : '#b7c8d9', borderRadius: 4, padding: '2px 7px', cursor: 'pointer', fontSize: 13,
})
const iconBtn: React.CSSProperties = { border: '1px solid #2b3a49', background: '#101820', color: '#dbe7f3', borderRadius: 4, padding: '2px 6px', cursor: 'pointer', fontSize: 13, display: 'inline-flex', alignItems: 'center', gap: 4 }

function errText(e: unknown): string { return String(e instanceof Error ? e.message : e) }

export function ReviewQueueSidebar({ onOpenMaterial, headerActions }: { onOpenMaterial: (m: Material) => void; headerActions?: React.ReactNode }) {
  const [filter, setFilter] = useState<ReviewFilter>('pending')
  const [items, setItems] = useState<Material[]>([])
  const [stats, setStats] = useState<MaterialStats | null>(null)
  const [bulkIds, setBulkIds] = useState<string[]>([])
  const [error, setError] = useState<string | null>(null)
  const activeId = useReviewActive((s) => s.activeMaterialId)

  const load = useCallback(() => {
    setError(null)
    Promise.all([
      reviewstageApi.list(filter === 'all' ? {} : filter === 'archived' ? { archived_only: true } : { status: filter }),
      reviewstageApi.stats(),
    ])
      .then(([list, s]) => {
        setItems(list.items || [])
        setStats(s)
        setBulkIds((prev) => prev.filter((id) => list.items.some((it) => it.id === id)))
      })
      .catch((e) => setError(errText(e)))
  }, [filter])

  const streamVersion = useReviewStream((s) => s.version)
  useEffect(() => useReviewStream.getState().acquire(), [])
  useEffect(() => { load() }, [load])
  useEffect(() => { if (streamVersion > 0) load() }, [streamVersion, load])

  const onSelect = useCallback((id: string) => {
    const m = items.find((it) => it.id === id)
    if (m) onOpenMaterial(m)
  }, [items, onOpenMaterial])

  const toggleBulkId = useCallback((id: string) => {
    setBulkIds((prev) => prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id])
  }, [])

  const runBatch = async (fn: () => Promise<unknown>) => {
    if (bulkIds.length === 0) return
    setError(null)
    try { await fn(); setBulkIds([]); load() } catch (e) { setError(`批量操作失败: ${errText(e)}`) }
  }
  const onBatchVerdict = (verdict: MaterialStatus) => { void runBatch(() => reviewstageApi.batchVerdict(bulkIds, verdict, `batch ${verdict}`)) }
  const onBatchTier = (tier: MaterialTier) => { void runBatch(() => reviewstageApi.batchTier(bulkIds, tier)) }
  const onBatchDelete = () => { void runBatch(() => reviewstageApi.batchDelete(bulkIds, true)) }

  return (
    <div data-testid="review-queue-sidebar" style={{ height: '100%', minHeight: 0, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
      <div style={{ display: 'flex', gap: 5, flexWrap: 'wrap', padding: '6px 6px 6px', borderBottom: `1px solid ${COLORS.border}` }}>
        {FILTERS.map((f) => (
          <button key={f.key} type="button" style={tabSm(filter === f.key)} onClick={() => setFilter(f.key)}>{f.label}</button>
        ))}
        <span style={{ marginLeft: 'auto', display: 'inline-flex', gap: 4, alignItems: 'center' }}>
          {headerActions}
          <button type="button" style={iconBtn} onClick={load} data-testid="review-queue-sidebar-refresh" title="刷新"><RefreshCw size={13} /></button>
        </span>
      </div>
      {error && <div style={{ padding: '6px 10px', color: COLORS.rejected, fontSize: 13 }} data-testid="review-queue-sidebar-error">{error}</div>}
      <MaterialSidebar
        materials={items}
        selectedId={activeId}
        selectedIds={bulkIds}
        onSelect={onSelect}
        onToggleSelect={toggleBulkId}
        onBatchVerdict={onBatchVerdict}
        onBatchTier={onBatchTier}
        onBatchDelete={onBatchDelete}
        onClearBatch={() => setBulkIds([])}
        stats={stats}
        compact
      />
    </div>
  )
}
