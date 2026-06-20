/**
 * shell/SurfaceShell — 单区渲染壳。
 *
 * ?surface=<queue|material|comments|project|plan|threads|authored> 时, 整页只渲染那一个区,
 * 供挂进 VSCode 原生表面: 主侧栏的 项目/计划/对话/审阅材料/札记 各 section, 编辑区材料页, 次级侧栏评论。
 * surface=full/缺省 走 App(完整驾驶舱), 不经这里。
 *
 * section 列表(项目/计划/对话/札记)复用驾驶舱里现成的面板, 只把 openTab 改成"在 omnidashboard 编辑区
 * 打开该条目"(发宿主消息) —— 侧栏只管导航, 条目去编辑区开。审阅材料/材料/评论沿用三区原有联动。
 */
import React, { useEffect, useRef } from 'react'
// @ts-ignore — jsx 文件没 .d.ts
import { ThemeProvider } from '../contexts/ThemeContext'
import { ReviewQueueSidebar, CommentsPanel } from '../entities/review'
import { ReviewMaterialPanel } from '../entities/review_material'
import ProjectsPanel from './ProjectsPanel'
import PlanSidebar from '../entities/plan-folder/PlanSidebar'
import ThreadMonitorPanel from '../entities/controller/ThreadMonitorPanel'
import { authoredRegistration } from '../entities/authored'
import { usePanels } from '../stores/panelsStore'
import { useReviewActive } from '../stores/reviewActiveStore'
import { postHostMessage, openInOmnidashboard, type Surface } from '../lib/surface'

const backBtn: React.CSSProperties = {
  border: '1px solid #2b3a49', background: '#101820', color: '#9fd0ff',
  borderRadius: 4, padding: '2px 8px', cursor: 'pointer', fontSize: 12,
}

function BackToOmnichat({ region }: { region: Surface }) {
  return (
    <button type="button" style={backBtn} data-testid="surface-back-to-omnichat"
      title="切回 omnichat 完整界面"
      onClick={() => postHostMessage({ type: 'restore-region-internal', region })}>
      ↩ 回 omnichat
    </button>
  )
}

// section 列表里点条目 → 不在本侧栏开(没有 dockview), 改请宿主在 omnidashboard 编辑区开。
const surfaceOpenTab = (ref: any, title?: string, facet?: string): string => {
  if (ref && ref.type && ref.id != null) openInOmnidashboard(String(ref.type), String(ref.id), facet, title)
  return ref ? `${ref.type}:${ref.id}` : ''
}
/** 把全局 panelsStore 的 openTab/openTabBackground 改成"在 omnidashboard 编辑区开"。
 * 这样内部用 usePanels 的面板(项目/对话/札记)在 surface 下点条目即去编辑区, 无需改各面板。 */
function usePatchedPanelsForSurface() {
  const patched = useRef(false)
  if (!patched.current) {
    patched.current = true
    usePanels.setState({ openTab: surfaceOpenTab as any, openTabBackground: surfaceOpenTab as any })
  }
}

function ProjectSurface() {
  usePatchedPanelsForSurface()
  return <div style={{ height: '100vh', overflow: 'auto' }} data-testid="surface-project"><ProjectsPanel /></div>
}

function PlanSurface() {
  usePatchedPanelsForSurface()
  return (
    <div style={{ height: '100vh', display: 'flex', flexDirection: 'column' }} data-testid="surface-plan">
      <PlanSidebar filter={''} activeId={null} openTab={surfaceOpenTab as any} />
    </div>
  )
}

function ThreadsSurface() {
  usePatchedPanelsForSurface()
  return <div style={{ height: '100vh', display: 'flex', flexDirection: 'column' }} data-testid="surface-threads"><ThreadMonitorPanel /></div>
}

function AuthoredSurface() {
  usePatchedPanelsForSurface()
  const Editor = authoredRegistration.renderer.Editor
  return (
    <div style={{ height: '100vh', display: 'flex', flexDirection: 'column' }} data-testid="surface-authored">
      <Editor entity={{ type: 'authored', id: 'main', title: '札记', tags: [] } as any} />
    </div>
  )
}

function QueueSurface() {
  const setActiveMaterial = useReviewActive((s) => s.setActiveMaterial)
  return (
    <div style={{ height: '100vh', display: 'flex', flexDirection: 'column', background: '#161b22' }} data-testid="surface-queue">
      <ReviewQueueSidebar
        headerActions={<BackToOmnichat region="queue" />}
        onOpenMaterial={(m) => {
          setActiveMaterial(m.id, 'local')
          postHostMessage({ type: 'open-material-native', materialId: m.id, title: m.title })
        }} />
    </div>
  )
}

function MaterialSurface({ id }: { id: string | null }) {
  const setActiveMaterial = useReviewActive((s) => s.setActiveMaterial)
  useEffect(() => { if (id) setActiveMaterial(id, 'local') }, [id, setActiveMaterial])
  if (!id) return <div style={{ padding: 18, color: '#8b949e' }}>缺少材料 id(?surface=material&id=…)。</div>
  return (
    <div style={{ height: '100vh', display: 'flex', flexDirection: 'column' }} data-testid="surface-material">
      <ReviewMaterialPanel id={id} embedded />
    </div>
  )
}

function CommentsSurface() {
  return (
    <div style={{ height: '100vh', display: 'flex', flexDirection: 'column', background: '#0d1117' }} data-testid="surface-comments">
      <CommentsPanel headerActions={<BackToOmnichat region="comments" />} />
    </div>
  )
}

export default function SurfaceShell({ surface, id }: { surface: Surface; id: string | null }) {
  let body: React.ReactNode
  if (surface === 'queue') body = <QueueSurface />
  else if (surface === 'material') body = <MaterialSurface id={id} />
  else if (surface === 'comments') body = <CommentsSurface />
  else if (surface === 'project') body = <ProjectSurface />
  else if (surface === 'plan') body = <PlanSurface />
  else if (surface === 'threads') body = <ThreadsSurface />
  else if (surface === 'authored') body = <AuthoredSurface />
  else body = null
  return <ThemeProvider>{body}</ThemeProvider>
}
