// 被 cc_session/index.tsx 用 React.lazy 动态引入。PTY 路线的 ./Editor 依赖 xterm(~291KB),
// 拆到这里后 xterm 只在真正打开一个 cc_session tab 时才下载, 不再常驻首屏 bundle。
// (chat 路线的 CcChatPanel 仍由总控 surface 直接静态引用, 属首屏必要件, 不在此拆分。)
import React from 'react'
import Editor from './Editor'
import CcChatPanel from './CcChatPanel'
import type { CcSessionEntity } from './index'

const EditorRouter: React.FC<{ entity: CcSessionEntity; facet?: string }> = ({ entity }) => {
  if (entity.kind === 'chat') return <CcChatPanel entity={entity} />
  return <Editor entity={entity} />
}

export default EditorRouter
