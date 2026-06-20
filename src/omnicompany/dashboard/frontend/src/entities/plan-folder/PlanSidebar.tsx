import React, { useEffect, useMemo, useState } from 'react'
import type { SidebarViewProps } from '../registry'
import type { PlanEntity } from './index'
import { openInVscode } from '../../lib/openInVscode'

interface PlanDetailFile {
  path: string
  is_md: boolean
  size: number
  mtime: number
  note_id_if_md: string | null
}

interface DirNode {
  name: string
  path: string  // category prefix like "_infra" or "domain/voxel_engine"
  children: Map<string, DirNode>
  plans: PlanEntity[]
}

function buildTree(plans: PlanEntity[]): DirNode {
  const root: DirNode = { name: '', path: '', children: new Map(), plans: [] }
  for (const p of plans) {
    // p.id is like "_infra/[2026-05-01]WEB-FOUNDATION" or "[2026-04-22]X" (no category)
    const parts = p.id.split('/')
    const planLeaf = parts[parts.length - 1]
    const dirParts = parts.slice(0, -1)
    let cur = root
    for (const seg of dirParts) {
      let next = cur.children.get(seg)
      if (!next) {
        next = { name: seg, path: cur.path ? `${cur.path}/${seg}` : seg, children: new Map(), plans: [] }
        cur.children.set(seg, next)
      }
      cur = next
    }
    cur.plans.push(p)
  }
  return root
}

const S: Record<string, any> = {
  empty: { padding: 8, color: '#888', fontSize: 14 },
  treeRoot: { fontSize: 14, fontFamily: 'Consolas, Menlo, monospace' },
  dir: (depth: number): React.CSSProperties => ({
    padding: '2px 0', paddingLeft: 4 + depth * 12, cursor: 'pointer',
    color: '#a8a8a8', userSelect: 'none' as const,
    fontWeight: depth === 0 ? 'bold' as const : 'normal' as const,
  }),
  arr: { color: '#666', display: 'inline-block', width: 12 },
  count: { color: '#777', marginLeft: 6, fontSize: 14 },
  plan: (depth: number, active: boolean): React.CSSProperties => ({
    padding: '2px 0', paddingLeft: 4 + depth * 12 + 12, cursor: 'pointer',
    color: active ? '#90caf9' : '#d0d0d0',
    background: active ? '#1a2a3a' : 'transparent',
    overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' as const,
  }),
  fileRow: (depth: number, active: boolean): React.CSSProperties => ({
    padding: '1px 0', paddingLeft: 4 + depth * 12 + 24, cursor: 'pointer',
    color: active ? '#79c0ff' : '#a8a8a8',
    background: active ? '#1a2a3a' : 'transparent',
    overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' as const,
    fontSize: 14,
  }),
  badge: (color: string): React.CSSProperties => ({
    display: 'inline-block', padding: '1px 5px', borderRadius: 2, marginLeft: 4,
    fontSize: 14, color, background: '#1a1a1a',
  }),
}

interface DirRowProps {
  node: DirNode
  depth: number
  expandedDirs: Set<string>
  expandedPlans: Set<string>
  toggleDir: (path: string) => void
  togglePlan: (id: string) => void
  planFiles: Map<string, PlanDetailFile[]>
  loadingPlanIds: Set<string>
  activeId: string | null
  onOpenNote: (noteId: string) => void
  onOpenPlanTab: (planId: string, title: string) => void
  forceExpand?: boolean
}

function DirRow({
  node, depth, expandedDirs, expandedPlans, toggleDir, togglePlan,
  planFiles, loadingPlanIds, activeId, onOpenNote, onOpenPlanTab, forceExpand,
}: DirRowProps) {
  const isExpanded = forceExpand || expandedDirs.has(node.path)
  const total = countPlans(node)
  // project.md 立于 plan 之上的元数据 — 含 vision + exit_criteria + plan 列表
  // depth >= 1 (即非顶层 category) 时尝试给个 link, 失败 (无 project.md) 显 empty note 用户能感知
  const showProjectLink = depth >= 1 && total > 0
  const openProjectMd = (e: React.MouseEvent) => {
    e.stopPropagation()
    onOpenNote(`plans/${node.path}/project`)
  }
  return (
    <div>
      <div style={S.dir(depth)} onClick={() => toggleDir(node.path)} title={node.path || '(root)'}>
        <span style={S.arr}>{isExpanded ? '▾' : '▸'}</span>
        {node.name || 'plans'}
        <span style={S.count}>{total}</span>
        {showProjectLink && (
          <span
            onClick={openProjectMd}
            title={`打开 ${node.path}/project.md (vision + 退出条件)`}
            data-project-md={node.path}
            style={{ marginLeft: 8, color: '#666', cursor: 'pointer', fontSize: 14 }}
          >
            📄
          </span>
        )}
      </div>
      {isExpanded && (
        <div>
          {[...node.children.values()].map((c) => (
            <DirRow
              key={c.path} node={c} depth={depth + 1}
              expandedDirs={expandedDirs} expandedPlans={expandedPlans}
              toggleDir={toggleDir} togglePlan={togglePlan}
              planFiles={planFiles} loadingPlanIds={loadingPlanIds}
              activeId={activeId} onOpenNote={onOpenNote} onOpenPlanTab={onOpenPlanTab}
              forceExpand={forceExpand}
            />
          ))}
          {node.plans.map((p) => {
            const tabId = `plan:${p.id}`
            const isOpen = expandedPlans.has(p.id)
            const files = planFiles.get(p.id) || []
            const loading = loadingPlanIds.has(p.id)
            return (
              <div key={p.id}>
                <div
                  style={S.plan(depth + 1, activeId === tabId)}
                  title={p.id}
                  onClick={() => togglePlan(p.id)}
                  data-plan-id={p.id}
                >
                  <span style={S.arr}>{isOpen ? '▾' : '▸'}</span>
                  {p.title}
                  {p.archived && <span style={S.badge('#ffb74d')}>archived</span>}
                  {/* 开 plan 全页 (RelatedCcSessions 反查块在 Editor 里) */}
                  <span
                    onClick={(e) => { e.stopPropagation(); onOpenPlanTab(p.id, p.title) }}
                    title={`在 omnidashboard 打开 ${p.id} 全页 (含关联 cc_sessions 反查)`}
                    data-open-plan-tab={p.id}
                    style={{ marginLeft: 'auto', color: '#666', cursor: 'pointer', fontSize: 14, paddingLeft: 8 }}
                  >
                    📋
                  </span>
                  {/* 在 VSCode 里真打开计划文件夹(2026-06-14 用户#3) */}
                  {p.folder_path && (
                    <span
                      onClick={(e) => { e.stopPropagation(); openInVscode(p.folder_path!) }}
                      title={`在 VSCode 打开计划文件夹 ${p.folder_path}`}
                      data-open-plan-vscode={p.id}
                      style={{ color: '#0098FF', cursor: 'pointer', fontSize: 12, fontWeight: 700, paddingLeft: 8 }}
                    >
                      VS
                    </span>
                  )}
                </div>
                {isOpen && (
                  <div>
                    {loading && <div style={{ ...S.empty, paddingLeft: depth * 12 + 32 }}>加载中…</div>}
                    {!loading && files.length === 0 && (
                      <div style={{ ...S.empty, paddingLeft: depth * 12 + 32 }}>无文件</div>
                    )}
                    {files.filter(f => f.is_md).map((f) => {
                      const noteId = f.note_id_if_md
                      const noteTab = noteId ? `note:${noteId}` : ''
                      return (
                        <div
                          key={f.path}
                          style={S.fileRow(depth + 1, activeId === noteTab)}
                          title={f.path}
                          data-plan-file={f.path}
                          onClick={(e) => { e.stopPropagation(); if (noteId) onOpenNote(noteId) }}
                        >
                          {f.path}
                        </div>
                      )
                    })}
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}

function countPlans(n: DirNode): number {
  let c = n.plans.length
  for (const ch of n.children.values()) c += countPlans(ch)
  return c
}

export default function PlanSidebar({ filter, activeId, openTab }: SidebarViewProps) {
  const [list, setList] = useState<PlanEntity[]>([])
  const [loading, setLoading] = useState(true)
  const [expandedDirs, setExpandedDirs] = useState<Set<string>>(new Set())
  const [expandedPlans, setExpandedPlans] = useState<Set<string>>(new Set())
  const [planFiles, setPlanFiles] = useState<Map<string, PlanDetailFile[]>>(new Map())
  const [loadingPlanIds, setLoadingPlanIds] = useState<Set<string>>(new Set())

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    fetch('/api/plans').then((r) => r.json()).then((d: { items: any[] }) => {
      if (cancelled) return
      const items: PlanEntity[] = d.items.map((p: any) => ({
        type: 'plan' as const,
        id: p.id,
        title: p.date ? `${p.date} ${p.topic}` : p.topic,
        topic: p.topic,
        date: p.date,
        folder_path: p.folder_path,
        archived: p.archived,
        has_plan_md: p.has_plan_md,
        file_count: p.file_count,
        tags: p.archived ? ['archived'] : [],
      }))
      setList(items)
      // default-expand top-level (_infra / domain / _cross) + project subdir 二层
      // (例 _infra/dashboard, _infra/agent-framework, domain/gameplay_system/ux-figma)
      // round 5 plan 重组后 plan dir 在二层 project subdir 下, 不展二层 plan 看不到
      const expandSet = new Set<string>()
      for (const it of items) {
        const parts = it.id.split('/')
        if (parts.length >= 2) {
          expandSet.add(parts[0])  // top: _infra
        }
        if (parts.length >= 3) {
          expandSet.add(`${parts[0]}/${parts[1]}`)  // project: _infra/dashboard
        }
      }
      setExpandedDirs(expandSet)
      setLoading(false)
    }).catch(() => setLoading(false))
    return () => { cancelled = true }
  }, [])

  const tree = useMemo(() => {
    const ql = filter.trim().toLowerCase()
    const filtered = ql
      ? list.filter((p) => p.id.toLowerCase().includes(ql) || p.topic.toLowerCase().includes(ql))
      : list
    return buildTree(filtered)
  }, [list, filter])

  const toggleDir = (path: string) => setExpandedDirs((s) => {
    const n = new Set(s); n.has(path) ? n.delete(path) : n.add(path); return n
  })

  const togglePlan = async (id: string) => {
    setExpandedPlans((s) => {
      const n = new Set(s); n.has(id) ? n.delete(id) : n.add(id); return n
    })
    if (planFiles.has(id)) return
    setLoadingPlanIds((s) => new Set(s).add(id))
    try {
      const r = await fetch(`/api/plans/${id}`)
      const d = await r.json()
      setPlanFiles((m) => new Map(m).set(id, d.files || []))
    } catch {
      setPlanFiles((m) => new Map(m).set(id, []))
    } finally {
      setLoadingPlanIds((s) => { const n = new Set(s); n.delete(id); return n })
    }
  }

  const onOpenNote = (noteId: string) => {
    const title = noteId.split('/').pop() || noteId
    openTab({ type: 'note', id: noteId }, title)
  }

  const onOpenPlanTab = (planId: string, title: string) => {
    // 跟 SessionContextPanel 同 pattern: openTab({type:'plan'}) → 走 plan-folder Editor
    // (含 RelatedCcSessions 反查块, 列绑定此 plan 的所有 cc_sessions)
    openTab({ type: 'plan', id: planId }, planId.split('/').pop() || title)
  }

  if (loading) return <div style={S.empty}>加载中…</div>
  if (tree.children.size === 0 && tree.plans.length === 0) {
    return <div style={S.empty}>{filter ? '无匹配' : '无 plan'}</div>
  }

  return (
    <div style={S.treeRoot} data-tree="plan">
      {[...tree.children.values()].map((c) => (
        <DirRow
          key={c.path} node={c} depth={0}
          expandedDirs={expandedDirs} expandedPlans={expandedPlans}
          toggleDir={toggleDir} togglePlan={togglePlan}
          planFiles={planFiles} loadingPlanIds={loadingPlanIds}
          activeId={activeId} onOpenNote={onOpenNote} onOpenPlanTab={onOpenPlanTab}
          forceExpand={!!filter.trim()}
        />
      ))}
      {tree.plans.length > 0 && (
        <div>
          {tree.plans.map((p) => {
            const isOpen = expandedPlans.has(p.id)
            const files = planFiles.get(p.id) || []
            const loading = loadingPlanIds.has(p.id)
            // root 直接子 plan = orphan (缺 project subdir, 应放进某个 project)
            const isOrphan = !p.id.includes('/')
            return (
              <div key={p.id}>
                <div
                  style={{ ...S.plan(0, false), ...(isOrphan ? { borderLeft: '3px solid #ef5350', paddingLeft: 1 } : {}) }}
                  onClick={() => togglePlan(p.id)}
                  title={isOrphan
                    ? `⚠ orphan plan (在 docs/plans/ 根下, 缺 project subdir). 应放入某个 project (例 _infra/<project>/${p.id})`
                    : p.id}
                  data-orphan={isOrphan ? 'true' : undefined}
                >
                  <span style={S.arr}>{isOpen ? '▾' : '▸'}</span>
                  {p.title}
                  {isOrphan && <span style={S.badge('#ef5350')}>orphan</span>}
                  {p.archived && <span style={S.badge('#ffb74d')}>archived</span>}
                  <span
                    onClick={(e) => { e.stopPropagation(); onOpenPlanTab(p.id, p.title) }}
                    title={`打开 ${p.id} 全页 (含关联 cc_sessions 反查)`}
                    data-open-plan-tab={p.id}
                    style={{ marginLeft: 'auto', color: '#666', cursor: 'pointer', fontSize: 14, paddingLeft: 8 }}
                  >
                    📋
                  </span>
                </div>
                {isOpen && (
                  <div>
                    {loading && <div style={S.empty}>加载中…</div>}
                    {!loading && files.filter(f => f.is_md).map((f) => (
                      <div
                        key={f.path}
                        style={S.fileRow(0, activeId === `note:${f.note_id_if_md}`)}
                        title={f.path}
                        onClick={() => f.note_id_if_md && onOpenNote(f.note_id_if_md)}
                      >
                        {f.path}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
