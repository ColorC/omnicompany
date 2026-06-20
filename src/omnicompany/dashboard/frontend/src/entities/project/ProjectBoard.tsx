// 项目工作板(首页) — 用户原话(2026-06-12 /goal): "工作时第一考虑的是我要搞的是什么内容
// 相关的东西", 首页从 agent/plan 列表换成项目卡片。按主分组分区, 卡片 = 背景图 + 名称 +
// 最后活跃 + 一键复制 index 文件路径; 点开进项目详情(计划/对话/文件/审阅)。
// 数据: GET /api/projects (注册表 + index frontmatter 浮出), 与 omni project CLI 同源(总控共用)。

import React, { useCallback, useEffect, useState } from 'react'
import { Copy, RefreshCw, Pin, Check, FolderOpen } from 'lucide-react'
import { DynamicIcon } from 'lucide-react/dynamic'
import { projectsApi, type ProjectItem, type ProjectsBoard } from '../../api/projectsClient'
import { usePanels } from '../../stores/panelsStore'
import { useRefreshBus } from '../../stores/refreshBus'
import { openProps } from '../../utils/middleClick'
import { copyText } from '../../lib/copyText'
import { relTimeZh } from '../../lib/time'
import { openChatInVscode } from '../../lib/surface'
import KebabMenu, { type KebabItem } from '../../shared/view/ui/KebabMenu'

function relTime(iso?: string | null): string {
  return relTimeZh(iso) || '—'
}

function hashHue(s: string): number {
  let h = 0
  for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) >>> 0
  return h % 360
}

function cardBackground(p: ProjectItem): string {
  const bg = (p.bg || '').trim()
  if (bg) {
    if (/^(https?:|data:|\/|\.\/)/.test(bg) || /\.(png|jpe?g|webp|gif|svg)(\?|$)/i.test(bg)) {
      return `center/cover no-repeat url("${bg.replace(/"/g, '%22')}")`
    }
    return bg
  }
  const hue = hashHue(p.id)
  return `linear-gradient(120deg, hsl(${hue}, 45%, 32%) 0%, #0a0d10 95%)`
}

const S: Record<string, any> = {
  root: { height: '100%', overflow: 'auto', background: '#0a0a0a', color: '#e6edf3', padding: '18px 22px 40px', boxSizing: 'border-box' },
  head: { display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', marginBottom: 6 },
  title: { fontSize: 20, fontWeight: 750, color: '#e6edf3', letterSpacing: 0.2 },
  sub: { color: '#7d8da0', fontSize: 14, marginLeft: 10 },
  iconBtn: { width: 26, height: 26, border: '1px solid #263443', borderRadius: 5, background: '#101820', color: '#b8c7d9', cursor: 'pointer', display: 'inline-flex', alignItems: 'center', justifyContent: 'center', padding: 0 },
  groupHead: { display: 'flex', alignItems: 'center', gap: 8, margin: '18px 2px 8px', color: '#9fb2c6', fontSize: 16, fontWeight: 700 },
  groupCount: { color: '#586573', fontSize: 14, fontWeight: 400 },
  grid: { display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(252px, 1fr))', gap: 12 },
  card: { position: 'relative', borderRadius: 10, overflow: 'hidden', minHeight: 128, cursor: 'pointer', border: '1px solid #1d2630', display: 'flex', flexDirection: 'column', justifyContent: 'flex-end' },
  cardBgLayer: { position: 'absolute', inset: 0 },
  // 压暗层(2026-06-12 用户: 纯图片背景容易撞色压字) — 下半压重保字可读, 上缘留图
  cardOverlay: { position: 'absolute', inset: 0, background: 'linear-gradient(to top, rgba(4,7,10,.96) 0%, rgba(4,7,10,.78) 34%, rgba(4,7,10,.30) 68%, rgba(4,7,10,.12) 100%)' },
  cardInner: { position: 'relative', padding: '10px 12px' },
  cardName: { color: '#fff', fontSize: 16, fontWeight: 700, textShadow: '0 1px 4px rgba(0,0,0,.95)', display: 'flex', alignItems: 'center', gap: 6 },
  cardMeta: { color: 'rgba(255,255,255,.78)', fontSize: 13, marginTop: 6, textShadow: '0 1px 2px rgba(0,0,0,.9)', display: 'flex', alignItems: 'center', gap: 8 },
  copyBtn: { position: 'absolute', top: 8, right: 8, zIndex: 2, height: 24, border: '1px solid rgba(255,255,255,.28)', background: 'rgba(0,0,0,.42)', color: '#fff', borderRadius: 5, cursor: 'pointer', display: 'inline-flex', alignItems: 'center', gap: 4, padding: '0 7px', fontSize: 12.5 },
  tagChip: { display: 'inline-block', border: '1px solid rgba(255,255,255,.3)', borderRadius: 3, padding: '0 4px', fontSize: 12, color: '#fff', background: 'rgba(0,0,0,.3)' },
  empty: { color: '#586573', fontSize: 14, padding: '30px 8px', textAlign: 'center' },
  err: { color: '#ff8a80', fontSize: 14, padding: '8px' },
}

/** 项目小图标(lucide 矢量, kebab 名存在注册表 icon 字段)。未知名/未设置时不渲染, 不会崩。 */
export function ProjectIcon({ name, size = 15, color = '#fff' }: { name?: string; size?: number; color?: string }) {
  if (!name) return null
  return (
    <span data-testid="project-card-icon" style={{ display: 'inline-flex', alignItems: 'center', flexShrink: 0, color }}>
      <DynamicIcon name={name as never} size={size} />
    </span>
  )
}

/** 近 7 天逐日活跃格(旧→新, 末位=今天)。用户 2026-06-12: 比"N 个计划/动作"重要。 */
export function ActivityStrip({ days }: { days?: boolean[] }) {
  if (!days || days.length === 0) return null
  const activeCount = days.filter(Boolean).length
  return (
    <span
      data-testid="project-activity-strip"
      title={`近 7 天活跃 ${activeCount} 天(左旧右新, 最右=今天)`}
      style={{ display: 'inline-flex', gap: 2, alignItems: 'center' }}
    >
      {days.map((on, i) => (
        <span key={i} style={{
          width: 7, height: 7, borderRadius: 2,
          background: on ? '#3fb950' : 'rgba(255,255,255,.18)',
          boxShadow: on ? '0 0 4px rgba(63,185,80,.5)' : 'none',
        }} />
      ))}
    </span>
  )
}

/** 复制 index 路径按钮(卡片右上角): 一键把 PROJECT_INDEX.md 路径放进剪贴板, 粘给任何 AI 会话当引导。 */
function CopyIndexBtn({ p }: { p: ProjectItem }) {
  const [state, setState] = useState<'idle' | 'done' | 'fail'>('idle')
  if (!p.index_path) return null
  return (
    <button
      type="button"
      style={S.copyBtn}
      data-testid="project-card-copy-index"
      title={`复制 index 文件路径\n${p.index_path}${p.index_ok === false ? '\n⚠ index 文件校验未通过' : ''}`}
      onClick={(e) => {
        e.stopPropagation()
        void copyText(p.index_path!).then((ok) => {
          setState(ok ? 'done' : 'fail')
          window.setTimeout(() => setState('idle'), 1600)
        })
      }}
    >
      {state === 'done' ? <Check size={12} /> : <Copy size={12} />}
      {state === 'done' ? '已复制' : state === 'fail' ? '复制失败' : 'index'}
      {p.index_ok === false ? ' ⚠' : ''}
    </button>
  )
}

/** 卡片左上角「…更多」菜单(不挡右上角 index 复制钮)。第一批: 复制 id / 复制 index 路径 / 在编辑器打开根目录。 */
function CardKebab({ p }: { p: ProjectItem }) {
  const items: KebabItem[] = [
    { label: '复制项目 id', icon: <Copy size={14} />, testid: 'project-kebab-copy-id', onClick: () => { void copyText(p.id) } },
  ]
  if (p.index_path) items.push({ label: '复制 index 路径', icon: <Copy size={14} />, testid: 'project-kebab-copy-index', onClick: () => { void copyText(p.index_path!) } })
  const root = p.roots && p.roots[0]
  if (root) items.push({ label: '在编辑器打开根目录', icon: <FolderOpen size={14} />, testid: 'project-kebab-open-root', onClick: () => openChatInVscode('claude_code', root) })
  return (
    <div style={{ position: 'absolute', top: 8, left: 8, zIndex: 2 }} data-omni-capture-ignore="true">
      <KebabMenu items={items} testid="project-kebab" triggerStyle={{ border: '1px solid rgba(255,255,255,.28)', background: 'rgba(0,0,0,.42)', color: '#fff' }} />
    </div>
  )
}

export default function ProjectBoard() {
  const [board, setBoard] = useState<ProjectsBoard | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const openTab = usePanels((s) => s.openTab)
  const openTabBg = usePanels((s) => s.openTabBackground)
  const refreshNonce = useRefreshBus((s) => s.nonce)

  const load = useCallback((fresh = false) => {
    setBusy(true)
    projectsApi.list(fresh).then((raw) => {
      // 防御: 返回形状不对(代理/测试 fallthrough)时归一成空板
      const b: ProjectsBoard = raw && Array.isArray((raw as any).projects)
        ? raw : { projects: [], groups_order: [], group_labels: {} }
      setBoard(b)
      setError(null)
    }).catch((e) => setError(String(e?.message || e))).finally(() => setBusy(false))
  }, [])
  useEffect(() => { load(refreshNonce > 0) }, [load, refreshNonce])

  const open = (p: ProjectItem, bg = false) => {
    (bg ? openTabBg : openTab)({ type: 'project', id: p.id }, p.name || p.id)
  }

  const groups: string[] = board
    ? [...board.groups_order, ...Array.from(new Set(board.projects.map((p) => p.group))).filter((g) => !board.groups_order.includes(g))]
    : []

  return (
    <div style={S.root} data-testid="project-board">
      <div style={S.head}>
        <div>
          <span style={S.title}>项目工作板</span>
          <span style={S.sub}>项目是你和总控的共同入口 · 卡片右上角复制 index 引导文件</span>
        </div>
        <button type="button" style={{ ...S.iconBtn, opacity: busy ? 0.45 : 1 }} disabled={busy} title={busy ? '刷新中…' : '刷新(穿透缓存)'} data-testid="project-board-refresh" onClick={() => load(true)}><RefreshCw size={13} /></button>
      </div>
      {error && <div style={S.err}>{error}</div>}
      {board && board.projects.length === 0 && (
        <div style={S.empty}>还没有注册项目。用 <code>omni project register</code> 注册, 或让总控来。</div>
      )}
      {board && groups.map((g) => {
        const rows = board.projects.filter((p) => p.group === g)
        if (!rows.length) return null
        return (
          <div key={g} data-testid={`project-group-${g}`}>
            <div style={S.groupHead}>
              {board.group_labels[g] || g}
              <span style={S.groupCount}>{rows.length} 个项目</span>
            </div>
            <div style={S.grid}>
              {rows.map((p) => (
                <div
                  key={p.id}
                  style={S.card}
                  data-testid="project-card"
                  title={`${p.id} · 左键打开 / 中键后台开`}
                  {...openProps(() => open(p), () => open(p, true))}
                >
                  <div style={{ ...S.cardBgLayer, background: cardBackground(p) }} />
                  <div style={S.cardOverlay} />
                  <CopyIndexBtn p={p} />
                  <CardKebab p={p} />
                  <div style={S.cardInner}>
                    <div style={S.cardName}>
                      {p.pinned && <Pin size={13} />}
                      <ProjectIcon name={p.icon} />
                      {p.name || p.id}
                      {(p.tags || []).slice(0, 2).map((t) => <span key={t} style={S.tagChip}>{t}</span>)}
                    </div>
                    {/* 2026-06-12 用户: 描述不要(看名字就够); 近一周活跃 + 最后活跃比内容数重要 */}
                    <div style={S.cardMeta}>
                      <ActivityStrip days={p.activity_7d} />
                      <span data-testid="project-card-last-active">活跃 {relTime(p.last_active)}</span>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )
      })}
    </div>
  )
}
