/**
 * WebgameSpecView — webgame-spec 材料的"三位一体"复合视图: 一份材料里整合 文档 / 引导演示 / 文件树,
 * 而非三条独立队列项。演示与文件树作为子材料(extra.demo / extra.filetree_diff)按 id 取来内嵌。
 * 点文件树里的文件 → 开一个"文件页签"看预览(图片/html/diff)。
 */
import React, { useEffect, useMemo, useState } from 'react'
import { reviewstageApi, type Material } from '../../api/reviewstageClient'
import { createRenderer, stripFrontmatter } from '@wiki-core/render'
import '@wiki-core/ui.css'
import { COLORS } from './shared'
import { FileTreeDiffView, FilePreview, type FileEntry } from './FileTreeDiffView'

const md = createRenderer()

interface FileTab { key: string; file: FileEntry }

export function WebgameSpecView({ m }: { m: Material }) {
  const extra = (m.extra || {}) as Record<string, unknown>
  const demoRef = typeof extra.demo === 'string' ? extra.demo : null
  const demoId = demoRef && demoRef.startsWith('mat_') ? demoRef : null
  const demoUrlDirect = demoRef && !demoRef.startsWith('mat_') ? demoRef : null
  const filetreeId = typeof extra.filetree_diff === 'string' ? extra.filetree_diff : null

  const [demo, setDemo] = useState<Material | null>(null)
  const [filetree, setFiletree] = useState<Material | null>(null)
  const [tab, setTab] = useState<string>('doc')
  const [fileTabs, setFileTabs] = useState<FileTab[]>([])

  useEffect(() => { if (demoId) reviewstageApi.get(demoId).then(setDemo).catch(() => setDemo(null)) }, [demoId])
  useEffect(() => { if (filetreeId) reviewstageApi.get(filetreeId).then(setFiletree).catch(() => setFiletree(null)) }, [filetreeId])

  const docHtml = useMemo(() => (m.inline_content ? md.render(stripFrontmatter(m.inline_content)) : ''), [m.inline_content])
  const filetreeData = useMemo(() => {
    try { return filetree?.inline_content ? JSON.parse(filetree.inline_content) : null } catch { return null }
  }, [filetree])
  const demoLiveUrl = ((demo?.extra as Record<string, unknown> | undefined)?.live_url as string | undefined) ?? demoUrlDirect ?? undefined

  const openFileTab = (f: FileEntry) => {
    setFileTabs((prev) => (prev.some((t) => t.key === f.path) ? prev : [...prev, { key: f.path, file: f }]))
    setTab(`file:${f.path}`)
  }
  const closeFileTab = (key: string) => {
    setFileTabs((prev) => prev.filter((t) => t.key !== key))
    setTab('tree')
  }

  const TabBtn = ({ k, label, onClose }: { k: string; label: string; onClose?: () => void }) => (
    <div style={{ display: 'flex', alignItems: 'center', flexShrink: 0 }}>
      <button
        onClick={() => setTab(k)}
        style={{
          padding: '6px 12px', background: tab === k ? '#161b22' : 'transparent',
          color: tab === k ? COLORS.borderActive : COLORS.textDim, border: 0,
          borderBottom: tab === k ? `2px solid ${COLORS.borderActive}` : '2px solid transparent',
          cursor: 'pointer', fontSize: 14, whiteSpace: 'nowrap',
        }}
      >{label}</button>
      {onClose && <button onClick={onClose} title="关闭" style={{ background: 'transparent', border: 0, color: '#586069', cursor: 'pointer', marginLeft: -8, marginRight: 4, fontSize: 12 }}>✕</button>}
    </div>
  )

  const activeFile = tab.startsWith('file:') ? fileTabs.find((t) => `file:${t.key}` === tab)?.file : null

  return (
    <div data-testid="material-webgame-spec" style={{ display: 'flex', flexDirection: 'column', flex: 1, minHeight: 0, height: '100%', background: '#0a0d12', color: COLORS.text }}>
      <div style={{ display: 'flex', alignItems: 'center', borderBottom: `1px solid ${COLORS.border}`, overflowX: 'auto' }}>
        <TabBtn k="doc" label="文档" />
        <TabBtn k="demo" label="引导演示" />
        <TabBtn k="tree" label="文件树" />
        {fileTabs.map((t) => <TabBtn key={t.key} k={`file:${t.key}`} label={`文件: ${t.key.split('/').pop()}`} onClose={() => closeFileTab(t.key)} />)}
      </div>
      <div style={{ flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column' }}>
        {tab === 'doc' && (
          <div className="wiki-prose" style={{ flex: 1, minHeight: 0, overflow: 'auto', padding: 24, fontFamily: '"Segoe UI", -apple-system, sans-serif' }} dangerouslySetInnerHTML={{ __html: docHtml }} />
        )}
        {tab === 'demo' && (
          <div style={{ flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column' }}>
            <div style={{ padding: '4px 10px', borderBottom: `1px solid ${COLORS.border}`, display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap', flexShrink: 0 }}>
              {demoLiveUrl && (
                <button onClick={() => window.open(demoLiveUrl, '_blank', 'noopener')} style={{ padding: '3px 10px', background: COLORS.borderActive, color: '#fff', border: 0, borderRadius: 4, cursor: 'pointer', fontWeight: 600, fontSize: 13 }}>打开网页本体（新页全屏）</button>
              )}
              <span style={{ fontSize: 13, color: COLORS.textDim }}>嵌入框小, 点"打开网页本体"全屏体验; 每步评论在演示卡上{demo || demoUrlDirect ? '' : demoId ? '（加载中…）' : '（未配置）'}</span>
            </div>
            {demoLiveUrl
              ? <iframe src={demoLiveUrl} sandbox="allow-same-origin allow-scripts" style={{ flex: 1, minHeight: 0, border: 'none', background: '#fff', width: '100%' }} title="引导演示" />
              : <div style={{ padding: 16, color: COLORS.textDim }}>未配置引导演示。</div>}
          </div>
        )}
        {tab === 'tree' && (
          <div style={{ flex: 1, minHeight: 0, overflow: 'auto' }}>
            {filetreeData
              ? <FileTreeDiffView data={filetreeData} material={filetree ?? undefined} onOpenFile={openFileTab} />
              : <div style={{ padding: 16, color: COLORS.textDim }}>{filetreeId ? '文件树 diff 加载中…' : '未配置文件树 diff。'}</div>}
          </div>
        )}
        {activeFile && <div style={{ flex: 1, minHeight: 0, overflow: 'auto', padding: 8 }}><FilePreview file={activeFile} /></div>}
      </div>
    </div>
  )
}
