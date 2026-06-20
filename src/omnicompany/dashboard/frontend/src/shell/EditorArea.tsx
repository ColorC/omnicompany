import React, { useEffect, useRef, useState } from 'react'
import {
  DockviewReact,
  DockviewDefaultTab,
  type DockviewApi,
  type DockviewReadyEvent,
  type IDockviewPanelProps,
  type IDockviewPanelHeaderProps,
} from 'dockview'
import { usePanels, type DockDirection, type OpenedTab } from '../stores/panelsStore'
import { useReviewMaximize } from '../stores/reviewMaximizeStore'
import { registry } from '../entities/registry'
import { openInVscode } from '../lib/openInVscode'
import { VscodeIcon } from '../components/VscodeIcon'
import Welcome from './Welcome'

// 从页签背后的实体里挑一个可在 VSCode 打开的本地路径(不同实体字段不同; 无文件的页签返回 null)。
function pickVscodePath(entity: unknown): string | null {
  if (!entity || typeof entity !== 'object') return null
  const e = entity as Record<string, unknown>
  const p = e.json_path || e.folder_path || e.file_path || e.source_path || e.abs_path || e.path
  return typeof p === 'string' && p ? p : null
}

// 右键页签 → 打开"最大化审阅"菜单。包一层默认页签, 把 onContextMenu 接到页签根元素上;
// props.api 即该面板的句柄(id / setActive / maximize)。
const ReviewTab: React.FC<IDockviewPanelHeaderProps> = (props) => {
  const onContextMenu = (e: React.MouseEvent) => {
    e.preventDefault()
    useReviewMaximize.getState().openTabMenu({
      x: e.clientX,
      y: e.clientY,
      tabId: props.api.id,
      title: props.api.title ?? props.api.id,
    })
  }
  return <DockviewDefaultTab {...props} onContextMenu={onContextMenu} />
}

const menuStyles = {
  backdrop: { position: 'fixed' as const, inset: 0, zIndex: 1000 },
  menu: {
    position: 'fixed' as const,
    minWidth: 168,
    border: '1px solid #263443',
    borderRadius: 6,
    background: '#0c1116',
    boxShadow: '0 18px 40px rgba(0,0,0,.5)',
    padding: 6,
  },
  item: {
    display: 'flex',
    alignItems: 'center',
    gap: 8,
    width: '100%',
    textAlign: 'left' as const,
    border: 0,
    background: 'transparent',
    color: '#d7dee7',
    borderRadius: 5,
    padding: '7px 9px',
    fontSize: 14,
    cursor: 'pointer',
    whiteSpace: 'nowrap' as const,
  },
}

const TabContextMenu: React.FC = () => {
  const tabMenu = useReviewMaximize((s) => s.tabMenu)
  const maximizedTabId = useReviewMaximize((s) => s.maximizedTabId)
  const maximize = useReviewMaximize((s) => s.maximize)
  const exit = useReviewMaximize((s) => s.exit)
  const close = useReviewMaximize((s) => s.closeTabMenu)
  // 菜单打开时解析该页签对应的本地文件路径; 解析到才显示「在 VSCode 打开」(无文件的页签不显示, 免得点了没反应)。
  const [vscPath, setVscPath] = useState<string | null>(null)
  useEffect(() => {
    setVscPath(null)
    if (!tabMenu) return
    const tab = usePanels.getState().tabs.find((t) => t.id === tabMenu.tabId)
    const reg = tab && registry.get(tab.ref.type)
    if (!tab || !reg) return
    let alive = true
    reg.resolver.fetch(tab.ref.id).then((e) => { if (alive) setVscPath(pickVscodePath(e)) }).catch(() => { /* 解析失败就当无文件 */ })
    return () => { alive = false }
  }, [tabMenu])
  if (!tabMenu) return null
  const isThisMaximized = maximizedTabId === tabMenu.tabId
  const left = Math.min(tabMenu.x, (typeof window !== 'undefined' ? window.innerWidth : 1200) - 184)
  const top = Math.min(tabMenu.y, (typeof window !== 'undefined' ? window.innerHeight : 800) - 80)
  return (
    <div
      style={menuStyles.backdrop}
      onClick={close}
      onContextMenu={(e) => {
        e.preventDefault()
        close()
      }}
    >
      <div style={{ ...menuStyles.menu, left, top }} onClick={(e) => e.stopPropagation()}>
        <button
          type="button"
          style={menuStyles.item}
          data-testid="tab-menu-toggle-maximize"
          onClick={() => {
            if (isThisMaximized) exit()
            else maximize(tabMenu.tabId)
            close()
          }}
          onMouseEnter={(e) => (e.currentTarget.style.background = '#16202b')}
          onMouseLeave={(e) => (e.currentTarget.style.background = 'transparent')}
        >
          {isThisMaximized ? '退出最大化' : '最大化审阅（全屏）'}
        </button>
        {vscPath && (
          <button
            type="button"
            style={menuStyles.item}
            data-testid="tab-menu-open-vscode"
            title={vscPath}
            onClick={() => {
              openInVscode(vscPath)
              close()
            }}
            onMouseEnter={(e) => (e.currentTarget.style.background = '#16202b')}
            onMouseLeave={(e) => (e.currentTarget.style.background = 'transparent')}
          >
            <VscodeIcon size={14} /> 在 VSCode 打开
          </button>
        )}
      </div>
    </div>
  )
}

const EntityPanel: React.FC<IDockviewPanelProps<{ tab: OpenedTab }>> = (props) => {
  const tab = props.params.tab
  const reg = registry.get(tab.ref.type)
  if (!reg) {
    return <div style={{ padding: 16, color: '#ef5350' }}>未注册的实体类型: {tab.ref.type}</div>
  }
  const Editor = reg.renderer.Editor as React.ComponentType<{ entity: any; facet?: string }>
  const [entity, setEntity] = React.useState<any>(null)
  const [error, setError] = React.useState<string | null>(null)
  React.useEffect(() => {
    setError(null)
    setEntity(null)
    reg.resolver.fetch(tab.ref.id).then(setEntity).catch((e) => setError(String(e)))
  }, [tab.ref.id, tab.ref.type])

  if (error) return <div style={{ padding: 16, color: '#ef5350' }}>{error}</div>
  if (!entity) return <div style={{ padding: 16, color: '#666' }}>loading...</div>
  // Suspense 兜住懒加载的 Editor(切到该 tab 才下载对应 chunk); 非懒加载 Editor 同步渲染不受影响。
  return (
    <React.Suspense fallback={<div style={{ padding: 16, color: '#666' }}>加载视图…</div>}>
      <Editor entity={entity} facet={tab.facet} />
    </React.Suspense>
  )
}

const components = { entity: EntityPanel }
type DockPanel = NonNullable<ReturnType<DockviewApi['getPanel']>>

function placementSignature(tab: OpenedTab): string {
  if (!tab.placement) return ''
  return `${tab.placement.direction}:${tab.placement.referenceTabId || ''}`
}

function toDockPosition(direction: DockDirection): 'left' | 'right' | 'top' | 'bottom' {
  if (direction === 'above') return 'top'
  if (direction === 'below') return 'bottom'
  return direction
}

function findPlacementReference(api: DockviewApi, tab: OpenedTab, fallbackActiveId: string | null): DockPanel | undefined {
  const explicit = tab.placement?.referenceTabId
  if (explicit && explicit !== tab.id) {
    const panel = api.getPanel(explicit)
    if (panel) return panel
  }
  if (fallbackActiveId && fallbackActiveId !== tab.id) {
    const panel = api.getPanel(fallbackActiveId)
    if (panel) return panel
  }
  return api.panels.find((p) => p.id !== tab.id)
}

function EditorArea() {
  const apiRef = useRef<DockviewApi | null>(null)
  const tabs = usePanels((s) => s.tabs)
  const activeId = usePanels((s) => s.activeId)
  const closeTab = usePanels((s) => s.closeTab)
  const activate = usePanels((s) => s.activate)
  const lastSyncedTabsRef = useRef<string>('')
  const [readyVersion, setReadyVersion] = useState(0)

  const syncPanels = (api: DockviewApi, nextTabs: OpenedTab[], nextActiveId: string | null) => {
    const sig = nextTabs.map((t) => `${t.id}:${placementSignature(t)}`).join('|') + '#' + nextActiveId
    if (sig === lastSyncedTabsRef.current) return
    lastSyncedTabsRef.current = sig

    const existing = new Set(api.panels.map((p) => p.id))
    const tabsWithPlacement: OpenedTab[] = []
    for (const tab of nextTabs) {
      if (tab.placement) tabsWithPlacement.push(tab)
      if (!existing.has(tab.id)) {
        const referencePanel = tab.placement ? findPlacementReference(api, tab, nextActiveId) : undefined
        api.addPanel({
          id: tab.id,
          component: 'entity',
          title: tab.title,
          params: { tab },
          // 性能(2026-06-06): 只有总控对话用 'always'(切走也保留 WS/滚动/运行态, 修之前的丢状态 bug);
          // 其余 tab 用 'onlyWhenVisible' —— 切走即卸载, 不再让所有打开过的页(审阅/材料/plan/会话)常驻
          // 后台渲染/轮询/连 WS, 这是"切页很卡 + 做啥都卡"的主因。
          renderer: tab.ref.type === 'controller' ? 'always' : 'onlyWhenVisible',
          // 中键后台打开: 新增的非活跃 tab 用 inactive 挂载, 不抢焦点(activeId 未变)。
          inactive: tab.id !== nextActiveId,
          ...(referencePanel ? { position: { referencePanel, direction: tab.placement?.direction } } : {}),
        })
      }
    }
    for (const tab of tabsWithPlacement) {
      const panel = api.getPanel(tab.id)
      const referencePanel = findPlacementReference(api, tab, nextActiveId)
      if (panel && referencePanel && tab.placement && panel.group === referencePanel.group) {
        panel.api.moveTo({ group: referencePanel.group, position: toDockPosition(tab.placement.direction) })
      }
    }
    for (const tab of tabsWithPlacement) {
      usePanels.getState().clearDockPlacement(tab.id)
    }
    for (const p of api.panels) {
      if (!nextTabs.some((t) => t.id === p.id)) p.api.close()
    }
    if (nextActiveId) {
      const p = api.getPanel(nextActiveId)
      if (p && !p.api.isActive) p.api.setActive()
    }
  }

  const onReady = (event: DockviewReadyEvent) => {
    apiRef.current = event.api
    lastSyncedTabsRef.current = ''
    setReadyVersion((v) => v + 1)
    useReviewMaximize.getState().registerApi(event.api)
    event.api.onDidActivePanelChange((p) => {
      if (p) activate(p.id)
    })
    event.api.onDidRemovePanel((p) => {
      const tab = usePanels.getState().tabs.find((t) => t.id === p.id)
      if (tab) closeTab(tab.id)
    })
    // dockview 自身退出最大化(关页/拖拽)时回收外壳状态。
    event.api.onDidMaximizedGroupChange(() => useReviewMaximize.getState().syncFromDockview())
    const state = usePanels.getState()
    syncPanels(event.api, state.tabs, state.activeId)
  }

  useEffect(() => {
    const api = apiRef.current
    if (!api) return
    syncPanels(api, tabs, activeId)
  }, [tabs, activeId, readyVersion])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && useReviewMaximize.getState().maximizedTabId) {
        useReviewMaximize.getState().exit()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => {
      window.removeEventListener('keydown', onKey)
      useReviewMaximize.getState().registerApi(null)
    }
  }, [])

  const maximized = useReviewMaximize((s) => s.maximizedTabId !== null)

  return (
    // data-review-maximized 驱动 index.css 隐藏 dockview 页签条(只在全屏审阅时)。
    <div style={{ position: 'absolute', inset: 0 }} data-review-maximized={maximized ? 'true' : undefined}>
      <DockviewReact
        components={components}
        onReady={onReady}
        defaultTabComponent={ReviewTab}
        watermarkComponent={Welcome as any}
        // 默认 'onlyWhenVisible'(切走即卸载, 省后台开销); 仅总控 tab 在 addPanel 里单独设 'always'
        // 以保留其 WS/滚动/运行态。详见 addPanel 处注释。
        className="dockview-theme-abyss"
      />
      <TabContextMenu />
    </div>
  )
}

// 性能(2026-06-06): 用 React.memo 包出口。本组件无 props, 父级(CockpitShell)的高频 state
// (简报/工作流轮询/toast/通知)变更不再级联重渲整个 dockview 编辑区子树; 它对 tabs/activeId
// 的 store 订阅仍会按需重渲, 不受影响。这是 §6.3「避免整树重渲」的低风险落地之一。
export default React.memo(EditorArea)
