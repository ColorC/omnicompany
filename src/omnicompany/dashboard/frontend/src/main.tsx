import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './shell/App'
import SurfaceShell from './shell/SurfaceShell'
import ChatStandalone from './standalone/ChatStandalone'
import { applyEntryRoute, type EntryRoot } from './routes/entryRoute'
import { readSurface } from './lib/surface'
import { startDevReloadWatch } from './lib/devReload'
import './index.css'
import './i18n/config.js'

startDevReloadWatch()

// 子 iframe(如 vilo demo 网页审阅)发的 __omnichat 消息(在 VSCode 打开 / 复制等)——本窗口不是
// webview 外壳, 需把它继续往上转发, 直到外壳 relay 收到转给扩展。来自上层(下行)的不再上抛, 防回环。
window.addEventListener('message', (ev) => {
  const d = ev.data as { __omnichat?: boolean } | null
  if (!d || d.__omnichat !== true) return
  if (ev.source === window.parent) return
  try { window.parent?.postMessage(d, '*') } catch { /* 顶层就是自己时忽略 */ }
  try { if (window.top && window.top !== window.parent) window.top.postMessage(d, '*') } catch { /* */ }
})

function pickRoot(root: EntryRoot) {
  switch (root) {
    case 'chat': return ChatStandalone
    case 'app':
    default: return App
  }
}

const root = applyEntryRoute(window)
// ?surface=queue|material|comments → 单区渲染(挂进 VSCode 原生表面); 否则走完整驾驶舱/聊天。
const { surface, id } = readSurface()

const tree = surface !== 'full'
  ? <SurfaceShell surface={surface} id={id} />
  : React.createElement(pickRoot(root))

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>{tree}</React.StrictMode>,
)
