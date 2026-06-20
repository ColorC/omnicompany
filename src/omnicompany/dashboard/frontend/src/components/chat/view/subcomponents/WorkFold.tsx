import React, { useState } from 'react';
import type { ChatMessage } from '../../types/types';

/**
 * 精简视图里被折叠的"中间工作记录"节点 —— 默认收起, 点一下展开看里面的工具调用 / 思考 / 中间文本。
 * 不重写消息渲染: 展开后用上层传进来的 renderMessage 复用 MessageComponent。
 */
interface WorkFoldProps {
  messages: ChatMessage[];
  renderMessage: (message: ChatMessage, prev: ChatMessage | null) => React.ReactNode;
}

export default function WorkFold({ messages, renderMessage }: WorkFoldProps) {
  const [open, setOpen] = useState(false);

  const toolNames = Array.from(
    new Set(messages.filter((m) => m.isToolUse && m.toolName).map((m) => String(m.toolName))),
  );
  const thinkingCount = messages.filter((m) => m.isThinking).length;
  const parts: string[] = [];
  if (toolNames.length) parts.push(toolNames.slice(0, 4).join('、') + (toolNames.length > 4 ? '…' : ''));
  if (thinkingCount) parts.push(`思考×${thinkingCount}`);
  const label = `工作记录 · ${messages.length} 步${parts.length ? ' · ' + parts.join(' · ') : ''}`;

  return (
    <div className="chat-message px-3 sm:px-0" data-testid="chat-work-fold">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        data-testid="chat-work-fold-toggle"
        className="flex w-full items-center gap-2 rounded-md border border-dashed border-gray-300 bg-gray-50 px-3 py-1.5 text-left text-sm text-gray-500 transition-colors hover:bg-gray-100 dark:border-gray-700 dark:bg-gray-800/40 dark:text-gray-400 dark:hover:bg-gray-800"
      >
        <span className={`inline-block transition-transform ${open ? 'rotate-90' : ''}`}>▸</span>
        <span className="flex-1 truncate">{label}</span>
        <span className="text-[14px] uppercase tracking-wide opacity-70">{open ? '收起' : '展开'}</span>
      </button>
      {open && (
        <div className="mt-2 space-y-3 border-l-2 border-gray-200 pl-2 dark:border-gray-700" data-testid="chat-work-fold-body">
          {messages.map((m, idx) => (
            <React.Fragment key={String(m.id ?? idx)}>
              {renderMessage(m, idx > 0 ? messages[idx - 1] : null)}
            </React.Fragment>
          ))}
        </div>
      )}
    </div>
  );
}
