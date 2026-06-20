/**
 * entities/review/CommentsPanel — C 区(评论/批注)独立面板。
 *
 * 评论自成一区, 与材料正文(B 区)同屏共存(用户 2026-06-14: "肯定要能够共存", 不是切走才能看)。
 * 读共享 store 的"激活材料 id"决定看哪条材料的评论, 随激活材料联动; 锚点也走共享 store,
 * B 区正文圈一段文字 → 这里追加框接住。内部默认形态挂在驾驶舱右栏; VSCode 原生形态
 * (surface=comments)整块挂进次级侧栏 —— 同一份组件, 只是挂载位置不同。
 */
import React, { useEffect, useState } from 'react'
import { reviewstageApi, type Material } from '../../api/reviewstageClient'
import { useReviewStream } from './streamStore'
import { useReviewActive } from '../../stores/reviewActiveStore'
import { CommentsFileView } from './CommentsFileView'
import { COLORS } from './shared'

export function CommentsPanel({ headerActions }: { headerActions?: React.ReactNode }) {
  const activeId = useReviewActive((s) => s.activeMaterialId)
  const pendingAnchor = useReviewActive((s) => s.pendingAnchor)
  const clearPendingAnchor = useReviewActive((s) => s.clearPendingAnchor)
  const streamMaterial = useReviewStream((s) => (activeId ? s.materials[activeId] : undefined))
  const [material, setMaterial] = useState<Material | null>(null)

  // WS 流引用计数(评论文件本身走 REST, 但材料元数据热更新靠流)。
  useEffect(() => useReviewStream.getState().acquire(), [])

  // 激活材料变了 → 先用流里的快照, 没有就拉一次。
  useEffect(() => {
    if (!activeId) { setMaterial(null); return }
    if (streamMaterial) { setMaterial(streamMaterial); return }
    let alive = true
    reviewstageApi.get(activeId).then((m) => { if (alive) setMaterial(m) }).catch(() => { /* 静默 */ })
    return () => { alive = false }
  }, [activeId, streamMaterial])

  // 只一层头(在 CommentsFileView 里), 调用方塞的动作(回 omnichat / 在 VSCode 打开)并进那一层。
  return (
    <div data-testid="comments-panel" style={{ height: '100%', minHeight: 0, display: 'flex', flexDirection: 'column', background: COLORS.bg, color: COLORS.text }}>
      {material
        ? <CommentsFileView material={material} title={material.title} headerActions={headerActions} pendingAnchor={pendingAnchor} clearPendingAnchor={clearPendingAnchor} />
        : (
          <>
            <div style={{ padding: '5px 10px', borderBottom: `1px solid ${COLORS.border}`, display: 'flex', alignItems: 'center', fontSize: 13, flexShrink: 0 }}>
              <span style={{ fontWeight: 600 }}>评论</span>
              <span style={{ marginLeft: 'auto', display: 'inline-flex', gap: 6 }}>{headerActions}</span>
            </div>
            <div style={{ padding: 18, color: COLORS.textDim, fontSize: 14 }}>选中一条审阅材料后, 这里显示它的评论。</div>
          </>
        )}
    </div>
  )
}
