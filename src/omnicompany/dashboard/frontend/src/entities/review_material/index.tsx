/**
 * entities/review_material — 驾驶舱内"单条审阅材料"页签 (R3).
 *
 * 多实例: 每条材料一个页签 (tab id = review_material:<材料id>, 与 cc_session 同模式,
 * 走 panelsStore.openTab 默认分支, 无 review_queue 那种单例特判)。
 * 面板复用 entities/review 的 MaterialDetail 全链路 (富渲染 5 类 + 圈选/文本定位 +
 * 批注评论(@mention/反馈状态) + verdict 三键带理由 + 4 级调级), 数据走 reviewstageApi;
 * 实时刷新订阅 entities/review/streamStore (WS 单连接)。
 * "Return source" 在驾驶舱语义 = 激活 review_queue 单例页签并聚焦本材料。
 */

import React, { useCallback, useEffect, useState } from 'react'
import {
  reviewstageApi,
  type Material,
  type MaterialStatus,
  type MaterialTier,
  type CommentFeedbackStatus,
} from '../../api/reviewstageClient'
import type { Entity } from '../types'
import type { EntityRegistration, EntityResolver } from '../registry'
import { usePanels } from '../../stores/panelsStore'
import { COLORS, MaterialDetail } from '../review'
import { useReviewStream } from '../review/streamStore'
import { postHostMessage, isInWebview } from '../../lib/surface'
import { VscodeIcon } from '../../components/VscodeIcon'

export interface ReviewMaterialEntity extends Entity {
  type: 'review_material'
}

/** 页签标题 = 材料标题截断 (dockview 页签条空间有限)。 */
export function materialTabTitle(title: string, max = 24): string {
  const t = (title || '').trim() || '(untitled)'
  return t.length > max ? `${t.slice(0, max - 1)}…` : t
}

function toEntity(m: Material): ReviewMaterialEntity {
  return { type: 'review_material', id: m.id, title: m.title, tags: [m.tier, m.status] }
}

const resolver: EntityResolver<ReviewMaterialEntity> = {
  type: 'review_material',
  async fetch(id) {
    // 后端已有 GET /api/boss-sight/reviewstage/{id} (reviewstageApi.get), 不走 list 过滤。
    return toEntity(await reviewstageApi.get(id))
  },
  async list() {
    const r = await reviewstageApi.list()
    return r.items.map(toEntity)
  },
}

function errText(e: unknown): string {
  return String(e instanceof Error ? e.message : e)
}

export function ReviewMaterialPanel({ id, embedded = false }: { id: string; embedded?: boolean }) {
  const [material, setMaterial] = useState<Material | null>(null)
  const [error, setError] = useState<string | null>(null)
  const openTab = usePanels((s) => s.openTab)
  const streamMaterial = useReviewStream((s) => s.materials[id])

  // WS 实时流: 引用计数订阅 (连接生命周期在 streamStore, 不挂本面板, 详见该文件头注释)。
  useEffect(() => useReviewStream.getState().acquire(), [])

  useEffect(() => {
    let alive = true
    setMaterial(null)
    setError(null)
    reviewstageApi.get(id)
      .then((m) => { if (alive) setMaterial(m) })
      .catch((e) => { if (alive) setError(errText(e)) })
    return () => { alive = false }
  }, [id])

  // 流事件携带完整材料 → 热更新本面板 (AI/别处加的评论、verdict 变化即时可见)。
  useEffect(() => {
    if (streamMaterial) setMaterial(streamMaterial)
  }, [streamMaterial])

  const onVerdict = useCallback(async (verdict: MaterialStatus, reason: string) => {
    try {
      setMaterial(await reviewstageApi.setVerdict(id, verdict, reason))
      setError(null)
    } catch (e) {
      setError(`verdict 失败: ${errText(e)}`)
    }
  }, [id])

  const onCommentSubmit = useCallback(async (content: string, target?: Record<string, unknown>) => {
    try {
      await reviewstageApi.addComment(id, content, target)
      setMaterial(await reviewstageApi.get(id))
      setError(null)
    } catch (e) {
      setError(`评论失败: ${errText(e)}`)
    }
  }, [id])

  const onFeedbackChange = useCallback(async (commentId: string, status: CommentFeedbackStatus) => {
    try {
      await reviewstageApi.setCommentFeedback(id, commentId, status)
      setMaterial(await reviewstageApi.get(id))
      setError(null)
    } catch (e) {
      setError(`反馈状态失败: ${errText(e)}`)
    }
  }, [id])

  const onTierChange = useCallback(async (tier: MaterialTier) => {
    try {
      setMaterial(await reviewstageApi.setTier(id, tier))
      setError(null)
    } catch (e) {
      setError(`调级失败: ${errText(e)}`)
    }
  }, [id])

  // "Return source": 激活 review_queue 单例页签并聚焦本材料 (facet 经 panelsStore 转聚焦 store)。
  const onReturnToSource = useCallback(() => {
    openTab({ type: 'review_queue', id: 'main' }, 'Review Queue', id)
  }, [openTab, id])

  return (
    <div
      style={{ height: '100%', display: 'flex', flexDirection: 'column', minHeight: 0, background: COLORS.bg }}
      data-testid="review-material-panel"
    >
      {error && (
        <div style={{ padding: '8px 12px', background: '#3d1f1f', color: COLORS.rejected, fontSize: 14 }} data-testid="review-material-error">
          {error}
        </div>
      )}
      {!material && !error && <div style={{ padding: 16, color: COLORS.textDim }}>加载材料中…</div>}
      {material && (
        <MaterialDetail
          material={material}
          onVerdict={onVerdict}
          onCommentSubmit={onCommentSubmit}
          onFeedbackChange={onFeedbackChange}
          onTierChange={onTierChange}
          source={embedded ? null : { type: 'review_queue', id: 'main', title: 'Review Queue' }}
          onReturnToSource={onReturnToSource}
          headerActions={embedded || !isInWebview() ? undefined : (
            <button
              type="button"
              data-testid="material-open-vscode"
              title="在 VSCode 编辑页签打开(仅正文+操作, 无外壳)"
              onClick={() => postHostMessage({ type: 'open-material-native', materialId: id, title: material.title })}
              style={{ display: 'inline-flex', alignItems: 'center', padding: '5px 8px', background: '#101820', color: '#dbe7f3', border: '1px solid #2b3a49', borderRadius: 4, cursor: 'pointer' }}
            >
              <VscodeIcon size={15} />
            </button>
          )}
        />
      )}
    </div>
  )
}

const Editor: React.FC<{ entity: ReviewMaterialEntity; facet?: string }> = ({ entity }) => (
  <ReviewMaterialPanel id={entity.id} />
)

export const reviewMaterialRegistration: EntityRegistration<ReviewMaterialEntity> = {
  resolver,
  renderer: { type: 'review_material', Editor },
  label: '审阅材料',
  icon: '🔍',
}
