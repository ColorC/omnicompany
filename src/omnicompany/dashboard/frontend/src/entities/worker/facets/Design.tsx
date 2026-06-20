import React, { useEffect, useState } from 'react'
import { fetchWorkerDetail, type WorkerDetail, type WorkerEntity } from '../resolver'
import CodeFileEditor from '../../../shell/CodeFileEditor'
import EmptyState from '../../../shell/EmptyState'

export default function WorkerDesignFacet({ entity }: { entity: WorkerEntity }) {
  const [detail, setDetail] = useState<WorkerDetail | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    setDetail(null); setError(null)
    fetchWorkerDetail(entity.id).then(setDetail).catch((e) => setError(String(e)))
  }, [entity.id])

  if (error) return <EmptyState text={`加载失败: ${error}`} />
  if (!detail) return <EmptyState text="加载中..." />

  return <CodeFileEditor defaultView="source" detail={{
    id: detail.id,
    name: detail.title,
    package: detail.package,
    file_path: detail.file_path,
    design_md: detail.design_md,
    source: detail.source,
  }} />
}
