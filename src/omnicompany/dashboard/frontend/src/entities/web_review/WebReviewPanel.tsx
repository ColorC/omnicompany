import React from 'react'

// 网页审阅面板 = 纯 iframe, 不放任何按钮。
// 圈选元素 / 页面快照 用驾驶舱顶栏那一套(已扩展到能进同源 iframe); 全屏用右键页签 → 最大化。
// 不再在面板内重复造控件(那正是之前"第二条顶栏 / 两套按钮"的来源)。
// 同源(经 dashboard /walker-game 代理到游戏 dev 服务)是顶栏圈选能读到游戏内容的前提。

export interface WebReviewTarget {
  title: string
  url: string
  route?: string
}

const WebReviewPanel: React.FC<{ target: WebReviewTarget }> = ({ target }) => {
  // 每次挂载追加一次性时间戳, 强制重新拉 index.html(绕开 webview 把旧页面缓存死)。
  // 配合 /vilo-demo 代理的 no-store + 引擎 ?v= 注入, 让"改了 demo 立刻能看见"。
  const src = React.useMemo(() => {
    const u = target.url || ''
    if (!u) return u
    return `${u}${u.includes('?') ? '&' : '?'}_cb=${Date.now()}`
  }, [target.url])
  return (
    <iframe
      data-testid="web-review-iframe"
      src={src}
      style={{ display: 'block', width: '100%', height: '100%', border: 'none', background: '#fff' }}
      title={target.title}
    />
  )
}

export default WebReviewPanel
