// 在 VSCode 里打开本地文件/目录 — 全站唯一抽象(与 copyText 同款分层思路)。两条路:
// 1) 页面嵌在 VSCode webview iframe 里: postMessage {__omnichat, type:'open-file'} →
//    webview 外壳转发给扩展 impl 的 openLocalFile, 在当前窗口直接开(无弹窗确认)。
// 2) 普通浏览器: 跳官方协议 vscode://file/<绝对路径>[:行[:列]], 由系统协议处理器唤起
//    VSCode(目录会开成新窗口的文件夹)。不依赖任何扩展。
// 注意 webview iframe 里直接导航 vscode:// 多半被沙箱拦, 所以嵌入态必须走消息桥。

/** 把本地绝对路径拼成 vscode://file 官方链接(Windows 反斜杠归一, 段内编码保留 : 和 /)。 */
export function vscodeFileUrl(path: string, line?: number | null, column?: number | null): string {
  let p = path.trim().replace(/\\/g, '/')
  if (!p.startsWith('/')) p = '/' + p
  let url = 'vscode://file' + encodeURI(p)
  if (line && line > 0) {
    url += `:${line}`
    if (column && column > 0) url += `:${column}`
  }
  return url
}

/** 打开文件/目录。返回是否已发起(嵌入态为乐观成功 — 消息已交宿主)。 */
export function openInVscode(path: string, line?: number | null): boolean {
  const p = (path || '').trim()
  if (!p) return false
  try {
    if (window.parent && window.parent !== window) {
      window.parent.postMessage({ __omnichat: true, type: 'open-file', path: p, line: line ?? null }, '*')
      return true
    }
  } catch { /* 降级到协议链接 */ }
  try {
    window.location.href = vscodeFileUrl(p, line)
    return true
  } catch {
    return false
  }
}
