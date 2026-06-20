import { beforeEach, describe, expect, it } from 'vitest';

import type { ChatMessage } from '../types/types';
import { getClaudePermissionSuggestion, isClaudeToolPermissionError } from './chatPermissions';

function toolError(toolName: string, content: string, toolInput: unknown = {}): ChatMessage {
  return {
    type: 'assistant',
    timestamp: new Date(),
    isToolUse: true,
    toolName,
    toolInput,
    toolResult: {
      content,
      isError: true,
    },
  };
}

describe('chat permission suggestions', () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it('does not treat missing files as permission errors', () => {
    const message = toolError(
      'Read',
      'File does not exist. Note: your current working directory is E:\\workspace\\omnicompany.',
    );

    expect(isClaudeToolPermissionError(message)).toBe(false);
    expect(getClaudePermissionSuggestion(message, 'claude')).toBeNull();
  });

  it('does not treat OmniChat planned scope blocks as grantable Claude permissions', () => {
    const message = toolError(
      'Write',
      'OmniChat blocked Write: `file_path` resolves outside the planned write scope.',
    );

    expect(isClaudeToolPermissionError(message)).toBe(false);
    expect(getClaudePermissionSuggestion(message, 'claude')).toBeNull();
  });

  it('suggests a permission rule for explicit Claude permission denials', () => {
    const message = toolError(
      'Bash',
      'User denied tool use',
      JSON.stringify({ command: 'git status --short' }),
    );

    expect(isClaudeToolPermissionError(message)).toBe(true);
    expect(getClaudePermissionSuggestion(message, 'claude')).toMatchObject({
      toolName: 'Bash',
      entry: 'Bash(git status:*)',
      isAllowed: false,
    });
  });
});
