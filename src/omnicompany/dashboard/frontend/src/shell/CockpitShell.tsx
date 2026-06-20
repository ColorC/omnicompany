import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  Bell,
  Boxes,
  Camera,
  ClipboardList,
  Copy,
  Crosshair,
  Eye,
  FolderKanban,
  MessageSquare,
  Maximize2,
  Minimize2,
  MoreHorizontal,
  MousePointer2,
  Network,
  NotebookPen,
  PanelBottom,
  PanelLeft,
  PanelRightOpen,
  RefreshCw,
  Send,
  Settings,
  UserRoundCog,
  X,
  type LucideIcon,
} from 'lucide-react'
import EditorArea from './EditorArea'
import BottomPanel from './BottomPanel'
import ProjectsPanel from './ProjectsPanel'
import { HSplitter, VSplitter } from './Splitter'
import { copyText } from '../lib/copyText'
import { useRefreshBus } from '../stores/refreshBus'
import { useReviewMaximize } from '../stores/reviewMaximizeStore'
import { bossSightApi, type BossSightBriefing, type BossSightWorkflowCtxSummary, type MaterialRegistryItem } from '../api/bossSightClient'
import { reviewstageApi, type Material, type MaterialStats, type ReviewCaptureKind } from '../api/reviewstageClient'
import { capturesApi } from '../api/capturesClient'
import { CONTROLLER_TAB_ID, usePanels, saveTabSnapshot, loadTabSnapshot, type DockPlacement, type OpenedTab } from '../stores/panelsStore'
import type { EntityType } from '../entities/types'
import { useControllerView } from '../entities/controller'
import { useReviewStream } from '../entities/review/streamStore'
import { CommentsPanel, ReviewQueueSidebar } from '../entities/review'
import { useReviewActive } from '../stores/reviewActiveStore'
import { materialTabTitle } from '../entities/review_material'
import { workerResolver } from '../entities/worker/resolver'
import { useBossSightObservability } from './useBossSightObservability'
import { openProps } from '../utils/middleClick'
import { colors as C, fontSize as FS, radius as R } from './tokens'

// 2026-06 重做: 导航四套合一为一条左侧 rail, 5 个统一目的地(每个=切到一个主区视图)。
type SpineKey = 'home' | 'authored' | 'review' | 'controller' | 'settings'
type OpenTab = ReturnType<typeof usePanels.getState>['openTab']
type SearchItem = {
  id: string
  title: string
  subtitle: string
  open_ref: any
}

type ReviewSource = {
  type: string
  id: string
  title?: string
}
type CaptureMode = 'element_comment' | 'debug_start' | null
type ElementTarget = {
  selector: string
  label: string
  tag: string
  id?: string
  testid?: string
  role?: string
  text?: string
  form_values?: {
    selector: string
    tag: string
    id?: string
    name?: string
    label?: string
    value?: string
    checked?: boolean
  }[]
  rect: { x: number; y: number; width: number; height: number }
  page_rect: { x: number; y: number; width: number; height: number }
  outer_html?: string
}
type CaptureDialogState = {
  kind: ReviewCaptureKind
  title: string
  target?: ElementTarget
  debugAllowed?: boolean
}

const S: Record<string, any> = {
  root: { position: 'relative' as const, display: 'flex', flexDirection: 'column', height: '100vh', background: '#0a0d10', color: '#d7dee7', minWidth: 0 },
  top: { height: 48, flexShrink: 0, display: 'grid', gridTemplateColumns: 'minmax(220px, 1fr) minmax(260px, 520px) auto', gap: 12, alignItems: 'center', padding: '0 12px', borderBottom: '1px solid #202a35', background: '#0d1217' },
  brand: { display: 'flex', alignItems: 'center', gap: 10, minWidth: 0 },
  brandIcon: { width: 28, height: 28, borderRadius: 6, display: 'inline-flex', alignItems: 'center', justifyContent: 'center', background: '#122234', color: '#79c0ff', border: '1px solid #234563', flexShrink: 0 },
  brandText: { minWidth: 0 },
  title: { fontSize: 15, fontWeight: 700, color: '#e6edf3', overflow: 'hidden', whiteSpace: 'nowrap', textOverflow: 'ellipsis' },
  subtitle: { fontSize: 14, color: '#8b949e', marginTop: 2, overflow: 'hidden', whiteSpace: 'nowrap', textOverflow: 'ellipsis' },
  search: { height: 30, border: '1px solid #263443', background: '#080b0e', color: '#d7dee7', borderRadius: 5, padding: '0 10px', fontSize: 14, minWidth: 0 },
  searchWrap: { position: 'relative' as const, minWidth: 0 },
  popover: { position: 'absolute' as const, zIndex: 30, top: 40, right: 12, width: 320, maxWidth: 'calc(100vw - 24px)', maxHeight: '70vh', overflow: 'auto', border: '1px solid #263443', borderRadius: 6, background: '#0c1116', boxShadow: '0 18px 40px rgba(0,0,0,.42)', padding: 8 },
  searchPanel: { position: 'absolute' as const, zIndex: 30, top: 36, left: 0, right: 0, maxHeight: 320, overflow: 'auto', border: '1px solid #263443', borderRadius: 6, background: '#0c1116', boxShadow: '0 18px 40px rgba(0,0,0,.42)', padding: 6 },
  panelTitle: { color: '#9fd0ff', fontSize: 14, fontWeight: 700, padding: '4px 6px 8px' },
  resultLine: { display: 'grid', gridTemplateColumns: 'minmax(0, 1fr) 30px', alignItems: 'stretch', gap: 4, marginBottom: 2 },
  resultButton: { width: '100%', display: 'grid', gap: 3, border: '1px solid transparent', background: 'transparent', color: '#d7dee7', borderRadius: 5, padding: '7px 8px', cursor: 'pointer', textAlign: 'left' as const, minWidth: 0 },
  splitButton: { width: 30, border: '1px solid #263443', background: '#101820', color: '#b8c7d9', borderRadius: 5, cursor: 'pointer', display: 'inline-flex', alignItems: 'center', justifyContent: 'center', padding: 0 },
  actionBar: { display: 'flex', flexWrap: 'wrap' as const, gap: 6, marginTop: 8 },
  smallAction: { border: '1px solid #263443', background: '#101820', color: '#b8c7d9', borderRadius: 5, padding: '5px 7px', fontSize: 14, cursor: 'pointer' },
  topActions: { display: 'flex', alignItems: 'center', gap: 8 },
  iconButton: { width: 32, height: 32, border: '1px solid #263443', borderRadius: 5, background: '#101820', color: '#b8c7d9', cursor: 'pointer', display: 'inline-flex', alignItems: 'center', justifyContent: 'center', padding: 0 },
  activeIconButton: { width: 32, height: 32, border: '1px solid #2f81f7', borderRadius: 5, background: '#10233a', color: '#79c0ff', cursor: 'pointer', display: 'inline-flex', alignItems: 'center', justifyContent: 'center', padding: 0 },
  dispatchButton: { height: 32, border: '1px solid #2f81f7', borderRadius: 5, background: '#10233a', color: '#79c0ff', cursor: 'pointer', display: 'inline-flex', alignItems: 'center', padding: '0 10px', fontSize: 14, whiteSpace: 'nowrap' as const },
  debugPill: { border: '1px solid #735c20', background: '#221b0b', color: '#f0d47c', borderRadius: 5, padding: '3px 7px', fontSize: 14, whiteSpace: 'nowrap' as const },
  body: { flex: 1, minHeight: 0, display: 'grid', gridTemplateColumns: '220px minmax(0, 1fr) 300px', overflow: 'hidden' },
  spine: { borderRight: '1px solid #202a35', background: '#0c1116', padding: 10, overflow: 'auto' },
  spineGroup: { color: '#768390', fontSize: 14, textTransform: 'uppercase' as const, margin: '8px 6px 6px', letterSpacing: 0 },
  spineButton: (active: boolean, narrow = false): React.CSSProperties => ({
    width: '100%',
    height: 38,
    display: 'grid',
    gridTemplateColumns: narrow ? '1fr' : '24px minmax(0, 1fr) auto',
    alignItems: 'center',
    justifyItems: narrow ? 'center' : undefined,
    gap: 8,
    border: `1px solid ${active ? '#2f81f7' : 'transparent'}`,
    background: active ? '#10233a' : 'transparent',
    color: active ? '#dbeafe' : '#b8c7d9',
    borderRadius: 6,
    cursor: 'pointer',
    padding: narrow ? 0 : '0 8px',
    textAlign: narrow ? 'center' as const : 'left' as const,
    marginBottom: 3,
    fontSize: 14,
  }),
  spineMeta: { color: '#8b949e', fontSize: 14 },
  // 左侧 rail(导航四套合一的唯一入口, token 化标准深色)
  rail: (open: boolean): React.CSSProperties => ({
    width: '100%', height: '100%', boxSizing: 'border-box', background: C.bgPanel,
    borderRight: `1px solid ${C.border}`, padding: open ? '12px 10px' : '12px 6px',
    display: 'flex', flexDirection: 'column', gap: 4, overflow: 'auto',
  }),
  railBtn: (active: boolean, collapsed: boolean): React.CSSProperties => ({
    width: '100%', height: 42, display: 'flex', alignItems: 'center',
    justifyContent: collapsed ? 'center' : 'flex-start', gap: 11,
    padding: collapsed ? 0 : '0 12px',
    border: `1px solid ${active ? C.accent : 'transparent'}`,
    background: active ? C.accentBg : 'transparent',
    color: active ? C.text : C.textMuted,
    borderRadius: R.default, cursor: 'pointer', fontSize: FS.body,
    fontWeight: active ? 600 : 500, whiteSpace: 'nowrap',
  }),
  railMeta: { fontSize: FS.small, color: C.accentLime, fontWeight: 600 },
  // 顶栏横向导航(用户 2026-06-14: 放进已有 brand 顶栏, 平时只 icon, 悬浮某按钮才展开文字带动画)
  topNav: { display: 'flex', alignItems: 'center', gap: 4, minWidth: 0 },
  topNavBtn: (active: boolean): React.CSSProperties => ({
    height: 38, display: 'inline-flex', alignItems: 'center', gap: 7, padding: '0 10px',
    border: `1px solid ${active ? C.accent : 'transparent'}`,
    background: active ? C.accentBg : 'transparent',
    color: active ? C.text : C.textMuted,
    borderRadius: R.default, cursor: 'pointer', fontSize: FS.body, fontWeight: active ? 600 : 500,
    whiteSpace: 'nowrap' as const, flexShrink: 0, transition: 'background .15s, border-color .15s',
  }),
  // 顶栏大块导航(取代原大标题)
  navBar: { display: 'flex', alignItems: 'center', gap: 6, minWidth: 0, overflowX: 'auto' as const },
  navBtn: (active: boolean): React.CSSProperties => ({
    height: 34, display: 'inline-flex', alignItems: 'center', gap: 6, padding: '0 11px',
    border: `1px solid ${active ? '#2f81f7' : '#263443'}`, background: active ? '#10233a' : '#0d1217',
    color: active ? '#dbeafe' : '#b8c7d9', borderRadius: 6, cursor: 'pointer', fontSize: 14,
    whiteSpace: 'nowrap' as const, flexShrink: 0, fontWeight: active ? 700 : 500,
  }),
  navMeta: { fontSize: 14, color: '#f0d47c', marginLeft: 1 },
  // 左栏顶边的小切换(工作板 / 消息队列)
  sideToggle: { display: 'flex', gap: 4, padding: '0 4px 6px' },
  sideToggleBtn: (active: boolean): React.CSSProperties => ({
    flex: 1, height: 24, border: `1px solid ${active ? '#2f81f7' : '#263443'}`, background: active ? '#10233a' : 'transparent',
    color: active ? '#79c0ff' : '#8b97a4', borderRadius: 5, cursor: 'pointer', fontSize: 14, fontWeight: active ? 700 : 500,
  }),
  mqRow: { display: 'block', width: '100%', textAlign: 'left' as const, border: '1px solid #21303f', background: '#0d141b', borderRadius: 6, padding: '6px 7px', margin: '0 4px 4px', cursor: 'pointer' },
  mqTitle: { color: '#d7dee7', fontSize: 14, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' as const },
  mqMeta: { color: '#8b949e', fontSize: 14, marginTop: 2, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' as const },
  main: { minWidth: 0, minHeight: 0, display: 'flex', flexDirection: 'column', overflow: 'hidden' },
  editor: { flex: 1, minHeight: 0, position: 'relative' as const },
  inspector: { borderLeft: '1px solid #202a35', background: '#0c1116', overflow: 'auto', padding: 12 },
  floatingInspector: { position: 'absolute' as const, top: 49, right: 0, bottom: 0, width: 'min(88vw, 320px)', zIndex: 20, boxShadow: '-18px 0 40px rgba(0,0,0,.45)' },
  inspectorTitle: { color: '#9fd0ff', fontSize: 15, fontWeight: 700, marginBottom: 10 },
  metricGrid: { display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, marginBottom: 12 },
  metric: { borderTop: '1px solid #263443', paddingTop: 7, minHeight: 48 },
  metricValue: { fontSize: 20, fontWeight: 700, color: '#e6edf3', letterSpacing: 0 },
  metricLabel: { fontSize: 14, color: '#8b949e', marginTop: 2 },
  section: { borderTop: '1px solid #202a35', paddingTop: 10, marginTop: 10 },
  sectionTitle: { fontSize: 14, color: '#d7dee7', fontWeight: 700, marginBottom: 8 },
  row: { display: 'grid', gap: 3, padding: '7px 0', borderBottom: '1px solid #141b22', minWidth: 0 },
  rowButton: { width: '100%', background: 'transparent', border: 0, cursor: 'pointer', textAlign: 'left' as const },
  rowTitle: { fontSize: 14, color: '#d7dee7', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' },
  rowMeta: { fontSize: 14, color: '#8b949e', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' },
  reviewLink: { display: 'grid', gap: 2, padding: '6px 0', color: '#d7dee7', textDecoration: 'none', borderBottom: '1px solid #141b22' },
  statusPill: (tone: string): React.CSSProperties => ({
    border: `1px solid ${tone === 'critical' ? '#8e2c2c' : tone === 'attention' ? '#735c20' : '#27553a'}`,
    background: tone === 'critical' ? '#2a1214' : tone === 'attention' ? '#221b0b' : '#0d2116',
    color: tone === 'critical' ? '#ff9b9b' : tone === 'attention' ? '#f0d47c' : '#8ee6a8',
    borderRadius: 5,
    padding: '3px 7px',
    fontSize: 14,
    whiteSpace: 'nowrap' as const,
  }),
  bottom: (h: number): React.CSSProperties => ({ height: h, minHeight: 90, maxHeight: '65vh', borderTop: '1px solid #202a35' }),
  error: { color: '#ff8a80', fontSize: 14 },
  captureBanner: { position: 'fixed' as const, zIndex: 80, top: 58, left: '50%', transform: 'translateX(-50%)', display: 'inline-flex', alignItems: 'center', gap: 8, border: '1px solid #2f81f7', background: '#0b1d33', color: '#dbeafe', borderRadius: 6, padding: '8px 10px', boxShadow: '0 12px 30px rgba(0,0,0,.38)', fontSize: 14 },
  captureOutline: (rect: ElementTarget['rect']): React.CSSProperties => ({ position: 'fixed', zIndex: 79, left: rect.x, top: rect.y, width: Math.max(1, rect.width), height: Math.max(1, rect.height), border: '2px solid #79c0ff', outline: '9999px solid rgba(47,129,247,.08)', pointerEvents: 'none', boxSizing: 'border-box' }),
  modalBackdrop: { position: 'fixed' as const, zIndex: 90, inset: 0, background: 'rgba(0,0,0,.42)', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 16 },
  modal: { width: 'min(560px, 100%)', border: '1px solid #263443', borderRadius: 6, background: '#0c1116', color: '#d7dee7', boxShadow: '0 24px 70px rgba(0,0,0,.52)', padding: 14 },
  modalHeader: { display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12, marginBottom: 10 },
  modalTitle: { color: '#9fd0ff', fontSize: 15, fontWeight: 700 },
  modalMeta: { color: '#8b949e', fontSize: 14, marginBottom: 10, overflowWrap: 'anywhere' as const },
  textArea: { width: '100%', minHeight: 110, resize: 'vertical' as const, boxSizing: 'border-box' as const, border: '1px solid #263443', background: '#080b0e', color: '#d7dee7', borderRadius: 5, padding: 10, fontSize: 14, lineHeight: 1.45 },
  modalActions: { display: 'flex', justifyContent: 'flex-end', gap: 8, marginTop: 12 },
  primaryAction: { border: '1px solid #2f81f7', background: '#1f6feb', color: '#fff', borderRadius: 5, padding: '7px 10px', fontSize: 14, cursor: 'pointer', display: 'inline-flex', alignItems: 'center', gap: 6 },
  toast: { position: 'fixed' as const, zIndex: 95, right: 14, top: 58, border: '1px solid #27553a', background: '#0d2116', color: '#8ee6a8', borderRadius: 6, padding: '8px 10px', fontSize: 14, boxShadow: '0 12px 30px rgba(0,0,0,.38)' },
  pathMenu: (x: number, y: number): React.CSSProperties => ({ position: 'fixed', zIndex: 96, left: Math.min(x, (typeof window !== 'undefined' ? window.innerWidth : 1200) - 280), top: Math.min(y, (typeof window !== 'undefined' ? window.innerHeight : 800) - 200), width: 264, border: '1px solid #263443', borderRadius: 6, background: '#0c1116', boxShadow: '0 18px 40px rgba(0,0,0,.5)', padding: 6 }),
  pathMenuPath: { color: '#9fd0ff', fontSize: 14, padding: '4px 6px 6px', overflowWrap: 'anywhere' as const, borderBottom: '1px solid #1a2330', marginBottom: 4 },
  pathMenuItem: { display: 'block', width: '100%', textAlign: 'left' as const, border: 0, background: 'transparent', color: '#d7dee7', borderRadius: 5, padding: '7px 8px', fontSize: 14, cursor: 'pointer', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' as const },
  moreMenu: { position: 'fixed' as const, zIndex: 40, top: 50, right: 12, minWidth: 200, border: '1px solid #263443', borderRadius: 6, background: '#0c1116', boxShadow: '0 18px 40px rgba(0,0,0,.5)', padding: 6, display: 'flex', flexDirection: 'column' as const, gap: 2 },
  moreItem: { display: 'flex', alignItems: 'center', gap: 8, width: '100%', textAlign: 'left' as const, border: 0, background: 'transparent', color: '#d7dee7', borderRadius: 5, padding: '8px 9px', fontSize: 14, cursor: 'pointer', whiteSpace: 'nowrap' as const },
}

// 左侧 rail 的目的地: 每个点下去 = 切到一个主区视图(统一语义, 不再有的开页签有的掀面板)。
const SPINE: Array<{ key: SpineKey; label: string; Icon: LucideIcon }> = [
  { key: 'home', label: '项目', Icon: FolderKanban },
  { key: 'authored', label: '草稿箱', Icon: NotebookPen },
  { key: 'review', label: '审阅', Icon: ClipboardList },
  { key: 'controller', label: '总控', Icon: MessageSquare },
  { key: 'settings', label: '设置', Icon: Settings },
]

// 顶栏导航(放进 brand 那条已有顶栏)。独立 memo 组件: 悬浮态只重渲它自己, 不带动整个 CockpitShell 重渲(修帧率)。
const CockpitTopNav = React.memo(function CockpitTopNav(
  { activeKey, reviewPending, onPick }: { activeKey: SpineKey; reviewPending: number; onPick: (k: SpineKey) => void },
) {
  const [hover, setHover] = React.useState<SpineKey | null>(null)
  return (
    <nav style={S.topNav} data-testid="cockpit-rail">
      {SPINE.map(({ key, label, Icon }) => {
        const meta = key === 'review' ? reviewPending : 0
        const hot = hover === key
        return (
          <button
            key={key}
            type="button"
            style={S.topNavBtn(activeKey === key)}
            onClick={() => onPick(key)}
            onMouseEnter={() => setHover(key)}
            onMouseLeave={() => setHover((h) => (h === key ? null : h))}
            data-testid={`cockpit-nav-${key}`}
            title={label}
          >
            <Icon size={18} />
            <span style={{ display: 'inline-block', maxWidth: hot ? 90 : 0, opacity: hot ? 1 : 0, overflow: 'hidden', whiteSpace: 'nowrap', transition: 'max-width .2s ease, opacity .18s ease' }}>{label}</span>
            {meta ? <span style={S.railMeta}>{meta}</span> : null}
          </button>
        )
      })}
    </nav>
  )
})

function tone(status: string): string {
  if (status === 'blocked' || status === 'critical') return 'critical'
  if (status === 'attention' || status === 'action_failed' || status === 'todo_open') return 'attention'
  return 'calm'
}

function clipText(text: string, limit: number): string {
  if (text.length <= limit) return text
  return `${text.slice(0, limit)}\n\n[truncated: ${text.length - limit} chars omitted]`
}

// #3f 右键把聊天里的文件路径当审阅材料: 先判断选中的文字像不像一条文件路径。
// 去掉包裹的引号/反引号; 绝对路径(盘符 / UNC / 斜杠开头)直接算; 相对路径要有分隔符 + 扩展名。
function stripPathSelection(raw: string): string {
  return raw.trim().replace(/^[`"']+/, '').replace(/[`"']+$/, '').trim()
}
function looksLikeFilePath(value: string): boolean {
  const t = stripPathSelection(value)
  if (!t || t.length > 1000 || /[\n\r]/.test(t)) return false
  if (/^[a-z][a-z0-9+.-]*:\/\//i.test(t) || t.startsWith('mailto:') || t.startsWith('data:')) return false
  if (/^[A-Za-z]:[\\/]/.test(t) || t.startsWith('\\\\') || t.startsWith('/')) return true
  return /[\\/]/.test(t) && /\.[A-Za-z0-9]{1,8}(?::\d+){0,2}$/.test(t)
}

function cssEscape(value: string): string {
  const css = (window as any).CSS
  if (css?.escape) return css.escape(value)
  return value.replace(/["\\#.:()[\] >+~]/g, '\\$&')
}

function compactText(value: string | null | undefined, limit = 220): string {
  return clipText(String(value || '').replace(/\s+/g, ' ').trim(), limit)
}

// 边栏收起状态持久化(localStorage), 刷新后保持。'1'=展开, '0'=收起。
function readPref(key: string, fallback: boolean): boolean {
  if (typeof window === 'undefined') return fallback
  try {
    const v = window.localStorage.getItem(key)
    return v === null ? fallback : v === '1'
  } catch {
    return fallback
  }
}
function writePref(key: string, value: boolean): void {
  if (typeof window === 'undefined') return
  try { window.localStorage.setItem(key, value ? '1' : '0') } catch { /* ignore */ }
}

// 复制到剪贴板: 全站唯一抽象在 lib/copyText (含 VSCode webview 宿主桥第三级降级)。
const copyToClipboard = copyText

function selectorForElement(el: Element): string {
  const testid = el.getAttribute('data-testid')
  if (testid) return `[data-testid="${cssEscape(testid)}"]`
  if (el.id) return `#${cssEscape(el.id)}`
  const parts: string[] = []
  let cur: Element | null = el
  while (cur && cur.nodeType === 1 && cur !== document.documentElement) {
    const tag = cur.tagName.toLowerCase()
    const parent: Element | null = cur.parentElement
    if (!parent) {
      parts.unshift(tag)
      break
    }
    const siblings = Array.from(parent.children) as Element[]
    const curTag = cur.tagName
    const sameTag = siblings.filter((child: Element) => child.tagName === curTag)
    const index = sameTag.indexOf(cur) + 1
    parts.unshift(sameTag.length > 1 ? `${tag}:nth-of-type(${index})` : tag)
    if (parts.length >= 6 || cur.getAttribute('data-testid') || cur.id) break
    cur = parent
  }
  return parts.join(' > ') || el.tagName.toLowerCase()
}

function isCaptureIgnored(target: EventTarget | null): boolean {
  return target instanceof Element && Boolean(target.closest('[data-omni-capture-ignore="true"]'))
}

// 纯文本叶子标签: 这些里若没有交互后代, 圈选时选它本身, 不上吸到最近的 [data-testid] 整块。
const TEXT_LEAF_TAGS = new Set(['span', 'small', 'strong', 'em', 'b', 'i', 'p', 'label', 'code'])

function captureElementFromTarget(el: Element): Element {
  // 交互件(按钮/链接/表单/带 role)内 → 上吸到该交互件(选整个按钮更有用, 维持原行为)。
  const interactive = el.closest('button, a, input, textarea, select, [role]')
  if (interactive) return interactive
  // 非交互件内的纯文本叶子 → 选它本身, 不再上吸到 [data-testid] 整块。
  // 这样能圈中"重要 · 待审"这类细粒度文字(2026-06-14 用户上报: 被上吸成整块 material-detail)。
  if (TEXT_LEAF_TAGS.has(el.tagName.toLowerCase())) return el
  return el.closest('[data-testid]') || el
}

function describeFormValues(el: Element): ElementTarget['form_values'] {
  const controls = [
    ...(el.matches('input, textarea, select') ? [el] : []),
    ...Array.from(el.querySelectorAll('input, textarea, select')),
  ].slice(0, 20) as Array<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>
  return controls.map((control) => {
    const item: NonNullable<ElementTarget['form_values']>[number] = {
      selector: selectorForElement(control),
      tag: control.tagName.toLowerCase(),
      id: control.id || undefined,
      name: control.getAttribute('name') || undefined,
      label: compactText(
        control.getAttribute('aria-label') ||
        control.getAttribute('title') ||
        control.getAttribute('placeholder') ||
        control.getAttribute('name') ||
        control.id ||
        control.tagName.toLowerCase(),
        160,
      ),
      value: clipText(control.value || '', 8000),
    }
    if (control.tagName.toLowerCase() === 'input' && (control.type === 'checkbox' || control.type === 'radio')) {
      item.checked = (control as HTMLInputElement).checked
    }
    return item
  })
}

function describeElement(el: Element): ElementTarget {
  const rect = el.getBoundingClientRect()
  const text = compactText((el as HTMLElement).innerText || el.textContent || '', 500)
  const label = compactText(
    el.getAttribute('aria-label') ||
    el.getAttribute('title') ||
    el.getAttribute('data-testid') ||
    text ||
    el.tagName.toLowerCase(),
    160,
  )
  return {
    selector: selectorForElement(el),
    label,
    tag: el.tagName.toLowerCase(),
    id: el.id || undefined,
    testid: el.getAttribute('data-testid') || undefined,
    role: el.getAttribute('role') || undefined,
    text,
    form_values: describeFormValues(el),
    rect: { x: rect.x, y: rect.y, width: rect.width, height: rect.height },
    page_rect: { x: rect.x + window.scrollX, y: rect.y + window.scrollY, width: rect.width, height: rect.height },
    outer_html: clipText(el.outerHTML || '', 3000),
  }
}

function activeTabPayload(tab: OpenedTab | null): Record<string, unknown> {
  return {
    tab_id: tab?.id || CONTROLLER_TAB_ID,
    type: tab?.ref.type || 'controller',
    id: tab?.ref.id || 'main',
    facet: tab?.facet || null,
    title: tab?.title || 'BOSS SIGHT',
  }
}

function pageStatePayload(tab: OpenedTab | null): Record<string, unknown> {
  const doc = document.documentElement
  const body = document.body
  return {
    title: document.title,
    active_tab: activeTabPayload(tab),
    viewport: { width: window.innerWidth, height: window.innerHeight },
    scroll: { x: window.scrollX, y: window.scrollY },
    document: {
      width: Math.max(doc.scrollWidth, body?.scrollWidth || 0),
      height: Math.max(doc.scrollHeight, body?.scrollHeight || 0),
    },
  }
}

function openCockpitRef(openTab: OpenTab, ref?: any, fallbackTitle = '打开', placement?: DockPlacement) {
  if (!ref) return false
  if (ref.type === 'review_material' && ref.id) {
    // 2026-06-14: 材料链接直接开正文页签(B 区), 不再绕道已退役的 review_queue 两栏台。
    openTab({ type: 'review_material', id: String(ref.id) }, fallbackTitle, undefined, placement)
    return true
  }
  if (ref.url) {
    window.location.href = String(ref.url)
    return true
  }
  if (!ref.type || !ref.id) return false
  openTab({ type: ref.type as EntityType, id: String(ref.id) }, fallbackTitle, ref.facet, placement)
  return true
}

function searchKey(item: SearchItem): string {
  const ref = item.open_ref || {}
  return `${ref.type || 'url'}:${ref.id || ref.url || item.id}:${ref.facet || ''}`
}

function dedupeSearchItems(items: SearchItem[]): SearchItem[] {
  const seen = new Set<string>()
  const out: SearchItem[] = []
  for (const item of items) {
    const key = searchKey(item)
    if (seen.has(key)) continue
    seen.add(key)
    out.push(item)
  }
  return out
}

function materialToSearchItem(item: MaterialRegistryItem): SearchItem {
  return {
    id: item.uri || item.id,
    title: item.title || item.id,
    subtitle: `${item.kind} / ${item.role || item.layer || 'material'}${item.status ? ` / ${item.status}` : ''}`,
    open_ref: item.open_ref,
  }
}

// Phase 2「看什么用什么打开」: 全局搜索补齐材料登记后端未索引的两类查看器 —— 工作节点(worker)、KB 关系图谱(graph)。
// 走统一 open_ref 路径(openCockpitRef → openTab), 不新增模块脊柱。
function workerToSearchItem(w: { id: string; title?: string; package?: string }): SearchItem {
  return {
    id: `worker:${w.id}`,
    title: w.title || w.id,
    subtitle: `工作节点 / ${w.package || 'worker'}`,
    open_ref: { type: 'worker', id: w.id },
  }
}

// graph 是单例(整个 KB 关系图谱), 命中"图/graph/关系/kb/链接"类查询时给出。
const GRAPH_SEARCH_ITEM: SearchItem = {
  id: 'graph:main',
  title: 'KB 关系图谱',
  subtitle: '知识库 / 关系图(从笔记/链接进入)',
  open_ref: { type: 'graph', id: 'main' },
}
const GRAPH_QUERY_RE = /图|graph|关系|kb|链接|link|知识库/i

function useNarrowViewport(breakpoint = 980) {
  const read = () => (typeof window === 'undefined' ? false : window.innerWidth < breakpoint)
  const [narrow, setNarrow] = useState(read)
  useEffect(() => {
    const onResize = () => setNarrow(read())
    window.addEventListener('resize', onResize)
    onResize()
    return () => window.removeEventListener('resize', onResize)
  }, [breakpoint])
  return narrow
}

function SearchPanel({ items, loading, onOpen, onOpenSplit }: {
  items: SearchItem[]
  loading: boolean
  onOpen: (item: SearchItem) => void
  onOpenSplit?: (item: SearchItem) => void
}) {
  return (
    <div style={S.searchPanel} data-testid="cockpit-search-panel">
      {loading && <div style={S.rowMeta}>搜索中...</div>}
      {!loading && items.length === 0 && <div style={S.rowMeta}>没有结果</div>}
      {!loading && items.map((item, index) => (
        <div key={`${searchKey(item)}-${index}`} style={S.resultLine}>
          <button
            type="button"
            style={S.resultButton}
            data-testid={`cockpit-search-result-${index}`}
            onMouseDown={(e) => e.preventDefault()}
            onClick={() => onOpen(item)}
          >
            <span style={S.rowTitle}>{item.title}</span>
            <span style={S.rowMeta}>{item.subtitle}</span>
          </button>
          <button
            type="button"
            style={S.splitButton}
            title="右侧打开"
            aria-label="右侧打开"
            data-testid={`cockpit-search-split-${index}`}
            onMouseDown={(e) => e.preventDefault()}
            onClick={() => onOpenSplit?.(item)}
          >
            <PanelRightOpen size={14} />
          </button>
        </div>
      ))}
    </div>
  )
}

function NotificationPanel({ workflow, onOpenRef, onOpenRefBg }: {
  workflow: BossSightWorkflowCtxSummary | null
  onOpenRef: (ref: any, title: string) => void
  onOpenRefBg: (ref: any, title: string) => void
}) {
  const items = workflow?.unresolved || []
  const recent = workflow?.action_history?.recent || []
  return (
    <div style={S.popover} data-testid="cockpit-notification-panel">
      <div style={S.panelTitle}>通知</div>
      {items.length === 0 && recent.length === 0 && <div style={S.rowMeta}>没有待处理通知</div>}
      {items.map((item: any, index: number) => {
        const ref = item.open_ref || item.target?.open_ref
        return (
          <button
            key={`${item.id || item.reason}-${index}`}
            type="button"
            style={S.resultButton}
            data-testid={`cockpit-notification-item-${index}`}
            {...openProps(
              () => ref && onOpenRef(ref, item.title || item.reason || '通知'),
              () => ref && onOpenRefBg(ref, item.title || item.reason || '通知'),
            )}
          >
            <span style={S.rowTitle}>{item.title || item.reason || item.kind}</span>
            <span style={S.rowMeta}>{item.priority || 'info'} · {item.reason || item.kind}</span>
          </button>
        )
      })}
      {recent.slice(0, 5).map((event: any, index: number) => (
        <div key={`${event.id || event.kind}-${index}`} style={S.row}>
          <div style={S.rowTitle}>{event.kind}</div>
          <div style={S.rowMeta}>{event.status || 'event'} · {event.error || event.note || ''}</div>
        </div>
      ))}
    </div>
  )
}

// 2026-06-05 用户明示: 右侧"检视/工作流"面板与控制台+通知铃严重重复, 整块删除。
// 原 SelectedObjectPanel / WorkflowInspector / Metric 已移除; 待处理/工作流数据走通知铃+控制台。

// 左栏"审阅材料队列"已收敛为唯一一份共享 ReviewQueueSidebar(entities/review), 不再在此自实现
// mini 列表(2026-06-14 用户: 列表只一份, 别和审阅台页面内 sidebar 重复)。
// 原"某区在VSCode打开"小图标(focus-native-view)已撤(用户: 意义不明)—— "在 VSCode 打开"改为
// 落到具体条目(计划/文件真打开、对话开 claude 插件/codex 终端), 不再做区级切换按钮。

function CaptureDialog({ state, comment, busy, error, onComment, onSubmit, onCopy, onCancel }: {
  state: CaptureDialogState
  comment: string
  busy: boolean
  error: string | null
  onComment: (value: string) => void
  onSubmit: () => void
  onCopy: () => void
  onCancel: () => void
}) {
  // 提交 = 保存到文件(攒着给总控整批读); 复制 = 纯剪贴板。都不进审阅队列。
  const submitLabel = '提交(存文件)'
  const copyLabel = state.kind === 'debug_start' ? '复制 + 标记调试起点' : '复制内容'
  const placeholder = state.kind === 'page_snapshot'
    ? '给这张页面快照写点备注(提交存文件 / 复制都会带上, 可选)'
    : state.kind === 'debug_start'
      ? '想让 Codex 看什么、指出什么?(提交存文件 / 复制都会带上)'
      : '给这个元素写备注(提交存文件 / 复制都会带上, 可选)'
  return (
    <div style={S.modalBackdrop} data-omni-capture-ignore="true" data-testid="cockpit-capture-modal">
      <div style={S.modal}>
        <div style={S.modalHeader}>
          <div style={S.modalTitle}>{state.title}</div>
          <button type="button" style={S.iconButton} onClick={onCancel} aria-label="关闭捕获对话框">
            <X size={15} />
          </button>
        </div>
        {state.target && (
          <div style={S.modalMeta} data-testid="cockpit-capture-target">
            {state.target.selector} / {state.target.label}
          </div>
        )}
        <textarea
          style={S.textArea}
          value={comment}
          placeholder={placeholder}
          onChange={(e) => onComment(e.target.value)}
          data-testid="cockpit-capture-comment"
          autoFocus
        />
        {error && <div style={{ ...S.error, marginTop: 8 }}>{error}</div>}
        <div style={S.modalActions}>
          <button type="button" style={S.smallAction} onClick={onCancel} disabled={busy}>取消</button>
          <button type="button" style={S.smallAction} onClick={onCopy} disabled={busy} data-testid="cockpit-capture-copy">
            <Copy size={13} style={{ verticalAlign: -2, marginRight: 4 }} />{copyLabel}
          </button>
          <button type="button" style={S.primaryAction} onClick={onSubmit} disabled={busy} data-testid="cockpit-capture-submit">
            <Send size={14} /> {busy ? '处理中…' : submitLabel}
          </button>
        </div>
      </div>
    </div>
  )
}

// R4: standalone 审阅台退役后, 其"总控推送 toast"上移到驾驶舱壳 (吃 streamStore 的
// pushed 事件)。锚点 data-testid="push-toast" 沿用 standalone 的, 8s 自动消失。
function ReviewPushToast({ material, onOpen, onClose }: {
  material: Material
  onOpen: () => void
  onClose: () => void
}) {
  useEffect(() => {
    const t = window.setTimeout(onClose, 8000)
    return () => window.clearTimeout(t)
  }, [material.id, onClose])
  return (
    <div
      data-testid="push-toast"
      style={{
        position: 'fixed', bottom: 24, right: 24, padding: 16,
        background: '#161b22', border: '2px solid #d29922',
        borderRadius: 8, minWidth: 300, maxWidth: 480,
        boxShadow: '0 4px 24px rgba(0,0,0,0.4)', zIndex: 1000, color: '#e6edf3',
      }}
    >
      <div style={{ fontSize: 14, color: '#d29922', fontWeight: 600 }}>📌 总控推送</div>
      <div style={{ fontSize: 15, fontWeight: 600, margin: '6px 0' }}>{material.title}</div>
      <div style={{ fontSize: 14, color: '#8b949e' }}>{material.pushed_reason}</div>
      <div style={{ marginTop: 8, display: 'flex', gap: 8 }}>
        <button type="button" onClick={onOpen} data-testid="push-toast-open" style={{
          padding: '4px 10px', background: '#10233a', color: '#79c0ff',
          border: '1px solid #2f81f7', borderRadius: 4, cursor: 'pointer',
        }}>查看</button>
        <button type="button" onClick={onClose} style={{
          padding: '4px 10px', background: 'transparent',
          color: '#e6edf3', border: '1px solid #30363d', borderRadius: 4, cursor: 'pointer',
        }}>关闭</button>
      </div>
    </div>
  )
}

export default function CockpitShell() {
  useBossSightObservability('cockpit-shell')
  const narrow = useNarrowViewport()
  const [briefing, setBriefing] = useState<BossSightBriefing | null>(null)
  const [workflow, setWorkflow] = useState<BossSightWorkflowCtxSummary | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [bottomVisible, setBottomVisible] = useState(false)
  const [bottomH, setBottomH] = useState(250)
  const [notificationsOpen, setNotificationsOpen] = useState(false)
  // 顶栏"更多(⋯)"溢出菜单: 收纳次级/新加动作(网页审阅、停靠、底部事件), 给顶栏减负 + 兜溢出。
  const [moreOpen, setMoreOpen] = useState(false)
  const [searchOpen, setSearchOpen] = useState(false)
  const [searchQuery, setSearchQuery] = useState('')
  const [searchResults, setSearchResults] = useState<SearchItem[]>([])
  const [searchLoading, setSearchLoading] = useState(false)
  const [activeSpine, setActiveSpine] = useState<SpineKey>('controller')
  const [captureMode, setCaptureMode] = useState<CaptureMode>(null)
  const [hoverTarget, setHoverTarget] = useState<ElementTarget | null>(null)
  const [captureDialog, setCaptureDialog] = useState<CaptureDialogState | null>(null)
  const [captureComment, setCaptureComment] = useState('')
  const [captureBusy, setCaptureBusy] = useState(false)
  const [captureError, setCaptureError] = useState<string | null>(null)
  const [captureToast, setCaptureToast] = useState('')
  // 左栏可收起, 状态持久化。
  const [spineOpen, setSpineOpen] = useState(() => readPref('omni.cockpit.spineOpen', true))
  // 全屏审阅: 最大化某个页签时收起左栏/底栏/页签条, 只留顶栏(含退出键)。
  const isReviewMaximized = useReviewMaximize((s) => s.maximizedTabId !== null)
  const exitReviewMaximize = useReviewMaximize((s) => s.exit)
  const enterReviewMaximize = useReviewMaximize((s) => s.maximizeActive)
  const showSpine = spineOpen && !isReviewMaximized
  // 总控停靠位置: false=随中央页签, true=靠右(像 VSCode AI 插件那样独占右侧 dock 组)。
  const [controllerRight, setControllerRight] = useState(() => readPref('omni.cockpit.controllerRight', false))
  // 左栏内容二选一: 工作板 / 消息队列(顶边小按钮切换)。
  const [sideView, setSideView] = useState<'workboard' | 'queue'>(() => (readPref('omni.cockpit.sideQueue', false) ? 'queue' : 'workboard'))
  // #3f 右键文件路径 → 审阅材料: 菜单位置/路径 + 匹配不上时的候选列表。
  const [pathMenu, setPathMenu] = useState<{ x: number; y: number; path: string } | null>(null)
  const [pathCandidates, setPathCandidates] = useState<{ items: Array<{ path: string; rel: string; name: string }>; query: string } | null>(null)
  const [pathBusy, setPathBusy] = useState(false)
  const [debugHandoff, setDebugHandoff] = useState<Record<string, unknown> | null>(() => {
    if (typeof window === 'undefined') return null
    try {
      const raw = window.localStorage.getItem('omni.codex.debugHandoff')
      return raw ? JSON.parse(raw) : null
    } catch {
      return null
    }
  })
  const openTab = usePanels((s) => s.openTab)
  const openTabBg = usePanels((s) => s.openTabBackground)
  const tabs = usePanels((s) => s.tabs)
  const activeTabId = usePanels((s) => s.activeId)
  const setTabs = usePanels((s) => s.setTabs)
  const setControllerView = useControllerView((s) => s.setView)

  // 重开恢复页签: 进来时捕获上次快照(在 save effect 覆盖前)。用户 2026-06-14: 默认直接恢复(像 VSCode 不问), 不再弹提示。
  const restoreSnapshotRef = useRef<OpenedTab[]>(loadTabSnapshot())
  const [showTabRestore, setShowTabRestore] = useState(false)  // 不再弹提示条; 保留 state 仅防旧 JSX 引用报错
  // 挂载即恢复上次页签(只跑一次, 声明在 save effect 之前 → 先塞快照, save effect 靠 tabSnapFirstRef 跳首帧不覆盖)。
  useEffect(() => {
    if (restoreSnapshotRef.current.length > 0) setTabs(restoreSnapshotRef.current)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])
  const tabSnapFirstRef = useRef(true)
  useEffect(() => {
    // 跳过首帧(此时 tabs 只有总控, 别用空快照覆盖上次的); 之后用户开/关页签才记。
    if (tabSnapFirstRef.current) { tabSnapFirstRef.current = false; return }
    saveTabSnapshot(tabs)
  }, [tabs])

  // selectedTab 仍给截图/调试交接的 active_tab/page 载荷用(activeTabPayload/pageStatePayload)。
  const selectedTab = useMemo(() => tabs.find((t) => t.id === activeTabId) || null, [tabs, activeTabId])

  // C 区(评论)联动: 焦点落在某材料页签 → 把"激活材料"写进共享 store, 右栏评论跟着切。
  const setActiveMaterial = useReviewActive((s) => s.setActiveMaterial)
  const [commentsWidth, setCommentsWidth] = useState(() => {
    try { return Number(window.localStorage.getItem('omni.cockpit.commentsWidth')) || 380 } catch { return 380 }
  })
  useEffect(() => { try { window.localStorage.setItem('omni.cockpit.commentsWidth', String(commentsWidth)) } catch { /* */ } }, [commentsWidth])
  useEffect(() => {
    if (selectedTab?.ref.type === 'review_material') setActiveMaterial(String(selectedTab.ref.id), 'local')
  }, [selectedTab, setActiveMaterial])
  // 评论右栏只在"正在看某条材料"时出现(随激活材料联动, 不占非审阅页签的横向空间)。
  const showComments = !isReviewMaximized && selectedTab?.ref.type === 'review_material'
  const statusTone = tone(workflow?.status || briefing?.severity || 'calm')
  const defaultSearchItems = useMemo(() => {
    const items: SearchItem[] = []
    for (const p of (briefing?.plans?.active || []).slice(0, 5) as any[]) {
      items.push({
        id: `plan:${p.plan_id || p.id || p.title}`,
        title: p.title || p.plan_id || p.id || 'active plan',
        subtitle: `plan${p.status ? ` / ${p.status}` : ''}`,
        open_ref: p.open_ref,
      })
    }
    for (const m of (briefing?.review?.recent || []).slice(0, 5) as any[]) {
      const reviewSource = { type: 'controller', id: 'main', title: 'BOSS SIGHT' }
      items.push({
        id: `review:${m.id}`,
        title: m.title || m.id,
        subtitle: `review / ${m.tier || 'material'} / ${m.status || ''}`,
        open_ref: m.open_ref ? { ...m.open_ref, source: m.open_ref.source || reviewSource } : { type: 'review_material', id: m.id, source: reviewSource },
      })
    }
    return dedupeSearchItems(items).slice(0, 8)
  }, [briefing])

  const load = () => {
    setError(null)
    // 顶栏刷新同时广播给项目工作板/侧栏等数据面板强刷(2026-06-12 用户: 首页换成项目板后点刷新无感)
    useRefreshBus.getState().bump()
    Promise.all([
      bossSightApi.briefing(),
      bossSightApi.workflowSummary(),
    ]).then(([b, w]) => {
      setBriefing(b)
      setWorkflow(w.ctx_summary)
    }).catch((e) => {
      setError(String(e?.message || e))
    })
  }

  useEffect(() => {
    load()
  }, [])

  useEffect(() => { writePref('omni.cockpit.spineOpen', spineOpen) }, [spineOpen])
  useEffect(() => { writePref('omni.cockpit.controllerRight', controllerRight) }, [controllerRight])
  // 把总控 dock 到中央页签的右侧(或挪回左侧)。复用搜索"右侧打开"同一 placement 机制。
  const toggleControllerRight = useCallback(() => {
    const next = !controllerRight
    setControllerRight(next)
    const st = usePanels.getState()
    const ref = st.tabs.find((t) => t.id !== CONTROLLER_TAB_ID)
    if (ref) st.requestDockPlacement(CONTROLLER_TAB_ID, { direction: next ? 'right' : 'left', referenceTabId: ref.id })
    openTab({ type: 'controller', id: 'main' }, '总控')
  }, [controllerRight, openTab])
  useEffect(() => { writePref('omni.cockpit.sideQueue', sideView === 'queue') }, [sideView])

  // #3f 右键: 仅在聊天面板内、且选中文字像文件路径时, 接管右键菜单。
  useEffect(() => {
    const onContextMenu = (event: MouseEvent) => {
      const sel = (window.getSelection?.()?.toString() || '').trim()
      if (!sel) return
      if (!(event.target instanceof Element) || !event.target.closest('[data-cc-chat-panel]')) return
      if (!looksLikeFilePath(sel)) return
      event.preventDefault()
      setPathCandidates(null)
      setPathMenu({ x: event.clientX, y: event.clientY, path: stripPathSelection(sel) })
    }
    document.addEventListener('contextmenu', onContextMenu, true)
    return () => document.removeEventListener('contextmenu', onContextMenu, true)
  }, [])

  // 路径菜单开着时: 点别处 / Esc 关闭。
  useEffect(() => {
    if (!pathMenu) return
    const onDown = (e: MouseEvent) => {
      if (e.target instanceof Element && e.target.closest('[data-testid="cockpit-path-menu"]')) return
      setPathMenu(null); setPathCandidates(null)
    }
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') { setPathMenu(null); setPathCandidates(null) } }
    document.addEventListener('mousedown', onDown, true)
    document.addEventListener('keydown', onKey, true)
    return () => {
      document.removeEventListener('mousedown', onDown, true)
      document.removeEventListener('keydown', onKey, true)
    }
  }, [pathMenu])

  useEffect(() => {
    const params = new URLSearchParams(window.location.search)
    const type = params.get('open_type') as EntityType | null
    const id = params.get('open_id')
    if (!type || !id) return
    const facet = params.get('open_facet') || undefined
    const title = params.get('open_title') || id.split('/').pop() || id
    openTab({ type, id }, title, facet)
  }, [openTab])

  // R4: standalone 审阅台退役 — 浏览器标签 urgent 角标 + 总控推送 toast 上移到驾驶舱壳。
  // 同一条审阅 WS(streamStore, 引用计数), 事件驱动重拉 stats; urgent = 推送未读 + 必验收待审。
  const reviewStreamVersion = useReviewStream((s) => s.version)
  const pushedMaterial = useReviewStream((s) => s.pushed)
  const pushedNonce = useReviewStream((s) => s.pushedNonce)
  const [reviewStats, setReviewStats] = useState<MaterialStats | null>(null)
  const [pushToast, setPushToast] = useState<Material | null>(null)
  const baseTitleRef = useRef(typeof document !== 'undefined' ? document.title : '')
  useEffect(() => useReviewStream.getState().acquire(), [])
  useEffect(() => {
    let alive = true
    reviewstageApi.stats().then((s) => { if (alive) setReviewStats(s) }).catch(() => {})
    return () => { alive = false }
  }, [reviewStreamVersion])
  useEffect(() => {
    const urgent = (reviewStats?.pushed_unread || 0) + (reviewStats?.mandatory_unaccepted || 0)
    // 不覆盖驾驶舱原标题(index.html 静态标题), 只在有 urgent 时加 (N) 前缀。
    document.title = urgent > 0 ? `(${urgent}) ${baseTitleRef.current}` : baseTitleRef.current
  }, [reviewStats])
  useEffect(() => {
    if (pushedNonce > 0 && pushedMaterial) setPushToast(pushedMaterial)
  }, [pushedNonce, pushedMaterial])

  useEffect(() => {
    if (!captureToast) return
    const timer = window.setTimeout(() => setCaptureToast(''), 2600)
    return () => window.clearTimeout(timer)
  }, [captureToast])

  useEffect(() => {
    if (!captureMode) {
      setHoverTarget(null)
      return
    }
    // 偏移: iframe 内元素的 rect 相对其自身视口, 叠加 iframe 在宿主里的位置, 高亮框才对齐。
    const describeAt = (el: Element, offset: { x: number; y: number }): ElementTarget => {
      const t = describeElement(el)
      return offset.x || offset.y
        ? { ...t, rect: { ...t.rect, x: t.rect.x + offset.x, y: t.rect.y + offset.y } }
        : t
    }
    // 跨 realm 元素判定: iframe 内元素是该 iframe 自己的 Element 构造器实例, 父窗口的
    // `instanceof Element` 对它为 false —— 这正是之前圈选进不到 iframe 的根因。改用 nodeType 鸭子判定。
    const asElement = (t: EventTarget | null): Element | null =>
      t && typeof t === 'object' && (t as Node).nodeType === 1 ? (t as Element) : null
    // rawTarget: iframe(被审网页)里选"所点的确切元素"(文字/方框都能选), 不向上吸附到最近的
    // button/[data-testid]; 顶层 dashboard 仍吸附到语义组件(选整块更顺手)。
    const resolve = (el: Element, rawTarget: boolean): Element => (rawTarget ? el : captureElementFromTarget(el))
    const makeHandlers = (offset: { x: number; y: number }, rawTarget: boolean) => ({
      onMove: (event: MouseEvent) => {
        if (isCaptureIgnored(event.target)) return
        const el = asElement(event.target)
        if (el) setHoverTarget(describeAt(resolve(el, rawTarget), offset))
      },
      onClick: (event: MouseEvent) => {
        if (isCaptureIgnored(event.target)) return
        const el = asElement(event.target)
        if (!el) return
        event.preventDefault()
        event.stopPropagation()
        const target = describeAt(resolve(el, rawTarget), offset)
        setCaptureDialog({
          kind: captureMode,
          title: captureMode === 'debug_start' ? 'Codex 调试交接' : '圈选元素评论',
          target,
          debugAllowed: captureMode === 'debug_start',
        })
        setCaptureComment('')
        setCaptureError(null)
        setCaptureMode(null)
        setHoverTarget(null)
      },
      onKeyDown: (event: KeyboardEvent) => {
        if (event.key !== 'Escape') return
        event.preventDefault()
        setCaptureMode(null)
        setHoverTarget(null)
      },
    })
    const cleanups: Array<() => void> = []
    const attach = (doc: Document, offset: { x: number; y: number }, rawTarget: boolean) => {
      const h = makeHandlers(offset, rawTarget)
      doc.addEventListener('mousemove', h.onMove, true)
      doc.addEventListener('click', h.onClick, true)
      doc.addEventListener('keydown', h.onKeyDown, true)
      cleanups.push(() => {
        try {
          doc.removeEventListener('mousemove', h.onMove, true)
          doc.removeEventListener('click', h.onClick, true)
          doc.removeEventListener('keydown', h.onKeyDown, true)
        } catch { /* doc gone (iframe unmounted) */ }
      })
    }
    attach(document, { x: 0, y: 0 }, false)
    // 让同一个顶栏圈选/捕获也能进到同源 iframe(如 walker-game 审阅页签)里, 不另做一套按钮。
    for (const iframe of Array.from(document.querySelectorAll('iframe'))) {
      let doc: Document | null = null
      try { doc = iframe.contentDocument } catch { doc = null }
      if (!doc) continue // 跨域 iframe 读不到, 跳过
      const r = iframe.getBoundingClientRect()
      attach(doc, { x: r.x, y: r.y }, true)
    }
    return () => cleanups.forEach((c) => c())
  }, [captureMode])

  useEffect(() => {
    if (!searchOpen) return
    const q = searchQuery.trim()
    if (!q) {
      setSearchLoading(false)
      setSearchResults(defaultSearchItems)
      return
    }

    let alive = true
    const qLower = q.toLowerCase()
    const localNow = defaultSearchItems.filter((item) =>
      `${item.title} ${item.subtitle}`.toLowerCase().includes(qLower),
    )
    setSearchResults(localNow)
    setSearchLoading(localNow.length === 0)
    const timer = window.setTimeout(() => {
      // Phase 2 parity: 材料登记(plan/note/material/team/project/guard/standard/template/...)
      // + worker(节点设计器)+ graph(KB 关系图谱) 一并并入全局搜索, 统一经 open_ref 打开。
      Promise.allSettled([
        bossSightApi.getMaterialRegistry({ q, limit: 8 }),
        workerResolver.search ? workerResolver.search(q) : Promise.resolve([]),
      ])
        .then(([mr, wk]) => {
          if (!alive) return
          const merged: SearchItem[] = [...localNow]
          if (mr.status === 'fulfilled') merged.push(...(mr.value.items || []).map(materialToSearchItem))
          if (wk.status === 'fulfilled') merged.push(...wk.value.slice(0, 6).map(workerToSearchItem))
          if (GRAPH_QUERY_RE.test(q)) merged.push(GRAPH_SEARCH_ITEM)
          if (merged.length === 0 && mr.status === 'rejected' && wk.status === 'rejected') {
            setSearchResults(defaultSearchItems)
          } else {
            setSearchResults(dedupeSearchItems(merged).slice(0, 12))
          }
        })
        .finally(() => {
          if (alive) setSearchLoading(false)
        })
    }, 180)
    return () => {
      alive = false
      window.clearTimeout(timer)
    }
  }, [searchOpen, searchQuery, defaultSearchItems])

  // 统一语义: 每个 rail 目的地 = 切到一个主区视图(已存在的固定页签直接激活, 否则开)。
  const handleSpine = (key: SpineKey) => {
    setActiveSpine(key)
    if (key === 'home') openTab({ type: 'project_board', id: 'main' }, '项目')
    else if (key === 'authored') openTab({ type: 'authored', id: 'main' }, '草稿箱')
    else if (key === 'review') openTab({ type: 'review_queue', id: 'main' }, '审阅')
    else if (key === 'controller') openTab({ type: 'controller', id: 'main' }, '总控')
    else if (key === 'settings') openTab({ type: 'settings', id: 'main' }, '设置')
  }

  // rail 高亮跟随真实激活页签(修旧 activeSpine 本地自记与所见对不上的问题)。
  const railActiveKey: SpineKey = (() => {
    const t = selectedTab?.ref.type
    if (t === 'project_board' || t === 'project') return 'home'
    if (t === 'authored') return 'authored'
    if (t === 'review_queue' || t === 'review_material') return 'review'
    if (t === 'controller') return 'controller'
    if (t === 'settings') return 'settings'
    return activeSpine
  })()

  const openSearchItem = (item: SearchItem) => {
    if (openCockpitRef(openTab, item.open_ref, item.title)) {
      setSearchOpen(false)
      setSearchQuery('')
    }
  }

  const openSearchItemSplit = (item: SearchItem) => {
    if (openCockpitRef(openTab, item.open_ref, item.title, { direction: 'right', referenceTabId: activeTabId || CONTROLLER_TAB_ID })) {
      setSearchOpen(false)
      setSearchQuery('')
    }
  }

  const openWorkflowRef = (ref: any, title: string) => {
    openCockpitRef(openTab, ref, title)
    setNotificationsOpen(false)
  }
  const openWorkflowRefBg = (ref: any, title: string) => {
    openCockpitRef(openTabBg, ref, title) // 中键: 后台打开, 不切焦点/不收面板
  }

  const openPageSnapshotDialog = () => {
    setCaptureDialog({ kind: 'page_snapshot', title: '页面快照' })
    setCaptureComment('')
    setCaptureError(null)
  }

  // 快照要"抓到我当前所见的全部内容"——含同源内嵌 iframe(walker 审阅页 / webgame-spec 演示, 都经 8210
  // 同源反代), 并**递归进嵌套 iframe**(演示是 iframe 套 iframe)。这跟顶栏圈选进 iframe 同理(见 captureMode
  // effect 里对 document.querySelectorAll('iframe') 的遍历), 只是改成把每层文字拼起来。跨域读不到的标注后跳过;
  // 不可见(0×0, 例如未激活的 tab)的不抓, 贴近"所见"。
  const collectVisibleText = (): string => {
    const walk = (doc: Document, label: string, depth: number): string => {
      if (depth > 6) return '' // 递归深度护栏
      let out = ''
      const body = doc.body
      const text = (body?.innerText || body?.textContent || '').trim()
      if (text) out += (label ? `\n\n──[ ${label} ]──\n` : '') + text
      let frames: HTMLIFrameElement[] = []
      try { frames = Array.from(doc.querySelectorAll('iframe')) as HTMLIFrameElement[] } catch { frames = [] }
      for (const ifr of frames) {
        let rect: DOMRect | null = null
        try { rect = ifr.getBoundingClientRect() } catch { rect = null }
        if (rect && (rect.width === 0 || rect.height === 0)) continue // 不可见, 跳过
        const name = ifr.getAttribute('src') || ifr.getAttribute('title') || 'iframe'
        let cdoc: Document | null = null
        try { cdoc = ifr.contentDocument } catch { cdoc = null }
        if (!cdoc) { out += `\n\n──[ 内嵌页面(跨域, 未抓取): ${name} ]──`; continue }
        out += walk(cdoc, `内嵌页面: ${name}`, depth + 1)
      }
      return out
    }
    return walk(document, '', 0)
  }

  // 2026-06-03 用户明示捕获两个动作分离, 都**不进审阅队列**(审阅队列只给用户看 subagent 产出):
  //   复制 = 纯剪贴板(纯客户端, 不调后端, 见下);
  //   提交 = 保存到文件(data/boss_sight/captures/pending/, 见 submitCaptureToFile), 攒着;
  //   评论完一键「让总控读取(N)」(dispatchCaptures)整批交给唯一总控读处理。
  const copyCapture = async () => {
    if (!captureDialog) return
    setCaptureBusy(true)
    setCaptureError(null)
    const url = window.location.href
    const route = `${window.location.pathname}${window.location.search}${window.location.hash}`
    const bodyText = collectVisibleText()
    const html = document.documentElement?.outerHTML || ''
    try {
      // 调试交接: 仍设置 codex 调试交接对象(window + localStorage + pill), 这是给 Codex 的线索, 不进审阅。
      if (captureDialog.kind === 'debug_start') {
        const handoff = {
          id: `dh-${new Date().toISOString()}`,
          created_at: new Date().toISOString(),
          url,
          route,
          active_tab: activeTabPayload(selectedTab),
          target: captureDialog.target || null,
          page: pageStatePayload(selectedTab),
        }
        ;(window as any).__OMNI_CODEX_DEBUG_HANDOFF__ = handoff
        try { window.localStorage.setItem('omni.codex.debugHandoff', JSON.stringify(handoff)) } catch { /* ignore */ }
        setDebugHandoff(handoff)
      }
      // 用户明示 2026-06-04: 还是太长, 剪贴板就留一个文件路径。完整内容(含 HTML/页面文本)写到 clips 文件,
      // enqueue:false → 不进 dispatch 批次、不计入待处理数。剪贴板 = 仅文件路径一行(无链接则退化为选择器)。
      let savedPath = ''
      try {
        const res = await capturesApi.save({
          capture_kind: captureDialog.kind,
          title: captureDialog.title,
          comment: captureComment.trim(),
          url,
          route,
          target: captureDialog.target,
          text_snapshot: clipText(bodyText, 60000),
          dom_snapshot: clipText(html, 120000),
          enqueue: false,
        })
        savedPath = res.saved_path
      } catch { /* 写文件失败也别挡复制: 退化为复制选择器 */ }
      const text = savedPath || (captureDialog.target?.selector ? `选择器: ${captureDialog.target.selector}` : '(捕获)')
      const copied = await copyToClipboard(text)
      setCaptureToast(
        copied
          ? (savedPath ? '已复制文件路径' : '已复制选择器')
          : '复制失败(剪贴板不可用)',
      )
      setCaptureDialog(null)
      setCaptureComment('')
    } catch (e) {
      setCaptureError(`复制失败: ${(e instanceof Error ? e.message : String(e)).trim()}`)
    } finally {
      setCaptureBusy(false)
    }
  }

  // 提交 = 保存到文件(captures/pending), 不进审阅队列。攒着, 之后整批交总控。
  const submitCaptureToFile = async () => {
    if (!captureDialog) return
    setCaptureBusy(true)
    setCaptureError(null)
    const url = window.location.href
    const route = `${window.location.pathname}${window.location.search}${window.location.hash}`
    const bodyText = collectVisibleText()
    const html = document.documentElement?.outerHTML || ''
    try {
      if (captureDialog.kind === 'debug_start') {
        const handoff = {
          id: `dh-${new Date().toISOString()}`,
          created_at: new Date().toISOString(),
          url, route,
          active_tab: activeTabPayload(selectedTab),
          target: captureDialog.target || null,
          page: pageStatePayload(selectedTab),
        }
        ;(window as any).__OMNI_CODEX_DEBUG_HANDOFF__ = handoff
        try { window.localStorage.setItem('omni.codex.debugHandoff', JSON.stringify(handoff)) } catch { /* ignore */ }
        setDebugHandoff(handoff)
      }
      const res = await capturesApi.save({
        capture_kind: captureDialog.kind,
        title: captureDialog.title,
        comment: captureComment.trim(),
        url,
        route,
        target: captureDialog.target,
        text_snapshot: clipText(bodyText, 60000),
        dom_snapshot: clipText(html, 120000),
        enqueue: false,
      })
      setCaptureToast(res.saved_path ? `已保存捕获文件: ${res.saved_path}` : '已保存捕获文件')
      setCaptureDialog(null)
      setCaptureComment('')
    } catch (e) {
      const msg = (e instanceof Error ? e.message : String(e)).trim()
      if (/\b(404|405)\b/.test(msg)) {
        setCaptureError(`保存失败: 捕获路由未就绪 (${msg})。请重启 dashboard 后端 — 已捕获内容保留在本对话框。`)
      } else {
        setCaptureError(`保存失败: ${msg}`)
      }
    } finally {
      setCaptureBusy(false)
    }
  }

  // (捕获→总控的整批派发已按用户要求关停 2026-06-12: 捕获只落盘, 不再塞给总控/不再提示。)

  // #3f 把一条文件路径变成审阅材料。严格匹配 → 直接建材料并跳审阅台; 匹配不上 → 列出候选让用户挑。
  const addPathAsMaterial = async (path: string) => {
    setPathBusy(true)
    try {
      const sendPath = path.replace(/(:\d+){1,2}$/, '') // 去掉 file.ts:42:3 这种行列号
      const res = await reviewstageApi.fromPath(sendPath)
      if (res.matched && res.material) {
        setCaptureToast(`已加入审阅: ${res.material.title}`)
        setPathMenu(null)
        setPathCandidates(null)
        openTab({ type: 'review_queue', id: 'main' }, '审阅队列', res.material.id)
      } else {
        setPathCandidates({ items: res.candidates || [], query: res.query || sendPath })
      }
    } catch (e) {
      setCaptureToast(`加入审阅失败: ${(e instanceof Error ? e.message : String(e)).trim()}`)
      setPathMenu(null)
    } finally {
      setPathBusy(false)
    }
  }


  return (
    <div style={S.root} data-testid="cockpit-shell">
      {showTabRestore && (
        <div
          data-testid="tab-restore-bar"
          style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '6px 14px', background: '#10233a', borderBottom: '1px solid #1f3b5c', color: '#cdd9e5', fontSize: 14 }}
        >
          <span>上次关闭时还开着 <b style={{ color: '#9fd0ff' }}>{restoreSnapshotRef.current.length}</b> 个页签,要恢复吗?</span>
          <button
            type="button"
            data-testid="tab-restore-yes"
            style={{ border: '1px solid #2f81f7', background: '#10233a', color: '#79c0ff', borderRadius: 4, padding: '2px 12px', cursor: 'pointer', fontSize: 14 }}
            onClick={() => { setTabs(restoreSnapshotRef.current); setShowTabRestore(false) }}
          >恢复页签</button>
          <button
            type="button"
            data-testid="tab-restore-no"
            style={{ border: '1px solid #2b3a49', background: 'transparent', color: '#8b949e', borderRadius: 4, padding: '2px 12px', cursor: 'pointer', fontSize: 14 }}
            onClick={() => setShowTabRestore(false)}
          >不用</button>
        </div>
      )}
      <header style={narrow ? { ...S.top, gridTemplateColumns: 'minmax(0, 1fr) auto', gap: 8 } : S.top} data-testid="cockpit-topbar">
        <div style={{ display: 'flex', alignItems: 'center', gap: 14, minWidth: 0 }}>
          {!isReviewMaximized && (
            <CockpitTopNav activeKey={railActiveKey} reviewPending={briefing?.summary.review_pending || 0} onPick={handleSpine} />
          )}
        </div>
        {!narrow && (
          <div style={S.searchWrap}>
            <input
              style={{ ...S.search, width: '100%', boxSizing: 'border-box' }}
              aria-label="全局搜索"
              data-testid="cockpit-global-search"
              placeholder="搜索 计划 / 材料 / 执行者 / 规则"
              value={searchQuery}
              onFocus={() => {
                setSearchOpen(true)
                setSearchResults(defaultSearchItems)
              }}
              onBlur={() => window.setTimeout(() => setSearchOpen(false), 120)}
              onChange={(e) => {
                setSearchQuery(e.target.value)
                setSearchOpen(true)
              }}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && searchResults[0]) openSearchItem(searchResults[0])
              }}
            />
            {searchOpen && <SearchPanel items={searchResults} loading={searchLoading} onOpen={openSearchItem} onOpenSplit={openSearchItemSplit} />}
          </div>
        )}
        <div style={S.topActions}>
          {!isReviewMaximized && selectedTab?.ref.type === 'web_review' && (
            <button
              type="button"
              style={S.dispatchButton}
              title="全屏审阅当前网页 (也可右键页签 → 最大化)"
              aria-label="全屏审阅"
              data-testid="cockpit-enter-maximize"
              onClick={() => enterReviewMaximize()}
            >
              <Maximize2 size={13} style={{ verticalAlign: -2, marginRight: 4 }} />
              全屏
            </button>
          )}
          {isReviewMaximized && (
            <button
              type="button"
              style={S.dispatchButton}
              title="退出全屏审阅 (Esc)"
              aria-label="退出全屏审阅"
              data-testid="cockpit-exit-maximize"
              onClick={() => exitReviewMaximize()}
            >
              <Minimize2 size={13} style={{ verticalAlign: -2, marginRight: 4 }} />
              退出最大化
            </button>
          )}
          <button
            type="button"
            style={spineOpen ? S.activeIconButton : S.iconButton}
            title={spineOpen ? '收起导航' : '展开导航'}
            aria-label={spineOpen ? '收起导航' : '展开导航'}
            data-testid="cockpit-toggle-spine"
            onClick={() => setSpineOpen((v) => !v)}
          >
            <PanelLeft size={15} />
          </button>
          {statusTone !== 'calm' && (
            <span style={S.statusPill(statusTone)} data-testid="cockpit-status">{workflow?.status || briefing?.severity || 'loading'}</span>
          )}
          {debugHandoff && <span style={S.debugPill} data-testid="cockpit-debug-handoff-pill">调试就绪</span>}
          <button
            type="button"
            style={captureMode === 'element_comment' ? S.activeIconButton : S.iconButton}
            title="圈选元素评论"
            aria-label="圈选元素评论"
            data-testid="cockpit-element-comment"
            data-omni-capture-ignore="true"
            onClick={() => setCaptureMode((v) => v === 'element_comment' ? null : 'element_comment')}
          >
            <MousePointer2 size={15} />
          </button>
          <button
            type="button"
            style={S.iconButton}
            title="页面快照"
            aria-label="页面快照"
            data-testid="cockpit-page-snapshot"
            data-omni-capture-ignore="true"
            onClick={openPageSnapshotDialog}
          >
            <Camera size={15} />
          </button>
          <button type="button" style={S.iconButton} title="刷新" aria-label="刷新" onClick={load}><RefreshCw size={15} /></button>
          <button
            type="button"
            style={S.iconButton}
            title="通知"
            aria-label="通知"
            data-testid="cockpit-notifications-toggle"
            onClick={() => setNotificationsOpen((v) => !v)}
          >
            <Bell size={15} />
          </button>
          <button
            type="button"
            style={moreOpen ? S.activeIconButton : S.iconButton}
            title="更多"
            aria-label="更多"
            data-testid="cockpit-more"
            onClick={() => setMoreOpen((v) => !v)}
          >
            <MoreHorizontal size={15} />
          </button>
          {moreOpen && (
            <>
              <div style={{ position: 'fixed', inset: 0, zIndex: 39 }} onClick={() => setMoreOpen(false)} data-omni-capture-ignore="true" />
              <div style={S.moreMenu} data-testid="cockpit-more-menu" data-omni-capture-ignore="true">
                <button
                  type="button"
                  style={S.moreItem}
                  data-testid="cockpit-more-controller-right"
                  onClick={() => { setMoreOpen(false); toggleControllerRight() }}
                >
                  <PanelRightOpen size={15} /><span>{controllerRight ? '总控移回中央' : '总控停靠右侧'}</span>
                </button>
                <button
                  type="button"
                  style={S.moreItem}
                  data-testid="cockpit-more-bottom"
                  onClick={() => { setMoreOpen(false); setBottomVisible((v) => !v) }}
                >
                  <PanelBottom size={15} /><span>底部事件</span>
                </button>
                <button
                  type="button"
                  style={S.moreItem}
                  data-testid="cockpit-more-team-board"
                  onClick={() => { setMoreOpen(false); openTab({ type: 'team_board', id: 'main' }, '管线') }}
                >
                  <Network size={15} /><span>管线 (team · 按项目)</span>
                </button>
              </div>
            </>
          )}
          {notificationsOpen && <NotificationPanel workflow={workflow} onOpenRef={openWorkflowRef} onOpenRefBg={openWorkflowRefBg} />}
        </div>
      </header>
      {error && <div style={{ ...S.error, padding: '4px 12px', borderBottom: '1px solid #202a35', background: '#160d0d' }} data-testid="cockpit-load-error">加载失败: {error}</div>}
      {captureToast && <div style={S.toast} data-omni-capture-ignore="true" data-testid="cockpit-capture-toast">{captureToast}</div>}
      {pushToast && (
        <ReviewPushToast
          material={pushToast}
          onOpen={() => {
            openTab({ type: 'review_material', id: pushToast.id }, materialTabTitle(pushToast.title))
            setPushToast(null)
          }}
          onClose={() => setPushToast(null)}
        />
      )}
      {pathMenu && (
        <div style={S.pathMenu(pathMenu.x, pathMenu.y)} data-testid="cockpit-path-menu" data-omni-capture-ignore="true">
          {!pathCandidates ? (
            <>
              <div style={S.pathMenuPath} title={pathMenu.path}>{pathMenu.path}</div>
              <button type="button" style={S.pathMenuItem} disabled={pathBusy} data-testid="cockpit-path-menu-review" onClick={() => { void addPathAsMaterial(pathMenu.path) }}>
                {pathBusy ? '处理中…' : '作为审阅材料'}
              </button>
              <button type="button" style={S.pathMenuItem} onClick={async () => { await copyToClipboard(pathMenu.path); setCaptureToast('已复制路径'); setPathMenu(null) }}>复制路径</button>
              <button type="button" style={S.pathMenuItem} onClick={() => setPathMenu(null)}>取消</button>
            </>
          ) : (
            <>
              <div style={S.pathMenuPath}>没有精确匹配 · 候选 {pathCandidates.items.length}</div>
              {pathCandidates.items.length === 0 && <div style={{ ...S.rowMeta, padding: '4px 8px' }}>没找到 “{pathCandidates.query}”</div>}
              {pathCandidates.items.map((c, i) => (
                <button key={c.path} type="button" style={S.pathMenuItem} disabled={pathBusy} title={c.path} data-testid={`cockpit-path-candidate-${i}`} onClick={() => { void addPathAsMaterial(c.path) }}>
                  {c.rel}
                </button>
              ))}
              <button type="button" style={S.pathMenuItem} onClick={() => { setPathMenu(null); setPathCandidates(null) }}>取消</button>
            </>
          )}
        </div>
      )}
      {captureMode && (
        <div style={S.captureBanner} data-omni-capture-ignore="true" data-testid="cockpit-capture-banner">
          <Crosshair size={14} />
          {captureMode === 'debug_start' ? '点击页面上的调试起点' : '点击要评论的元素'}
        </div>
      )}
      {captureMode && hoverTarget && <div style={S.captureOutline(hoverTarget.rect)} data-omni-capture-ignore="true" data-testid="cockpit-capture-outline" />}
      {captureDialog && (
        <CaptureDialog
          state={captureDialog}
          comment={captureComment}
          busy={captureBusy}
          error={captureError}
          onComment={setCaptureComment}
          onSubmit={() => { void submitCaptureToFile() }}
          onCopy={() => { void copyCapture() }}
          onCancel={() => {
            setCaptureDialog(null)
            setCaptureComment('')
            setCaptureError(null)
          }}
        />
      )}
      <div style={{ flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
        {/* 主区(dockview) + 评论(看审阅材料时联动)。导航已搬进上方 brand 顶栏(CockpitTopNav)。 */}
        <div style={{ flex: 1, minHeight: 0, display: 'grid', gridTemplateColumns: `minmax(0, 1fr)${showComments ? ` 4px ${commentsWidth}px` : ''}`, overflow: 'hidden' }}>
          <main style={S.main}>
            <div style={S.editor}>
              <EditorArea />
            </div>
            {bottomVisible && !isReviewMaximized && (
              <>
                <HSplitter onResize={(d) => setBottomH((h) => Math.max(90, h + d))} side="top" />
                <div style={S.bottom(bottomH)}>
                  <BottomPanel onClose={() => setBottomVisible(false)} />
                </div>
              </>
            )}
          </main>
          {showComments && (
            <>
              <VSplitter side="left" onResize={(d) => setCommentsWidth((w) => Math.max(260, Math.min(760, w + d)))} />
              <aside style={{ minWidth: 0, minHeight: 0, display: 'flex', flexDirection: 'column', borderLeft: '1px solid #1f2937', overflow: 'hidden', background: '#0d1117' }} data-testid="cockpit-comments-rail">
                <CommentsPanel />
              </aside>
            </>
          )}
        </div>
      </div>
    </div>
  )
}
