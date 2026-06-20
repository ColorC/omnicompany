import { act, renderHook } from '@testing-library/react';
import { useRef, useState } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { entitiesApi } from '../../../api/entitiesClient';
import { useFileMentions, type MentionableFile } from './useFileMentions';

vi.mock('../../../api/entitiesClient', () => ({
  entitiesApi: {
    suggest: vi.fn(),
  },
}));

function useHarness(initialInput: string) {
  const [input, setInput] = useState(initialInput);
  const textareaRef = useRef<HTMLTextAreaElement>(
    {
      matches: vi.fn(() => true),
      focus: vi.fn(),
      setSelectionRange: vi.fn(),
    } as unknown as HTMLTextAreaElement,
  );
  const mentions = useFileMentions({
    selectedProject: null,
    input,
    setInput,
    textareaRef,
  });
  return { input, setInput, mentions };
}

describe('useFileMentions entity mentions', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.mocked(entitiesApi.suggest).mockReset();
  });

  it('loads entity suggestions and inserts display text instead of full paths', async () => {
    vi.mocked(entitiesApi.suggest).mockResolvedValue([
      {
        uri: 'omni://plan/dashboard%2FROADMAP',
        kind: 'plan',
        id: 'dashboard/ROADMAP',
        display: '@plan:Roadmap',
        short_name: 'Roadmap',
        title: 'Roadmap',
        snippet: 'status=active',
        source: 'docs/plans',
        open_ref: { type: 'plan', id: 'dashboard/ROADMAP' },
      },
    ]);

    const { result } = renderHook(() => useHarness('@ro'));

    act(() => {
      result.current.mentions.setCursorPosition(3);
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(130);
    });

    expect(entitiesApi.suggest).toHaveBeenCalledWith('ro', 10);
    expect(result.current.mentions.filteredFiles).toEqual([
      { name: 'Roadmap', path: '@plan:Roadmap', relativePath: 'omni://plan/dashboard%2FROADMAP' },
    ]);

    const suggestion: MentionableFile = result.current.mentions.filteredFiles[0];
    act(() => {
      result.current.mentions.selectFile(suggestion);
    });

    expect(result.current.input).toBe('@plan:Roadmap ');
    expect(result.current.input).not.toContain('dashboard/ROADMAP');
  });
});
