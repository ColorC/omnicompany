import { useCallback, useEffect, useMemo, useState } from 'react';
import type { Dispatch, KeyboardEvent, RefObject, SetStateAction } from 'react';
import { entitiesApi } from '../../../api/entitiesClient';
import { escapeRegExp } from '../utils/chatFormatting';
import type { Project } from '../../../types/app';

export interface MentionableFile {
  name: string;
  path: string;
  relativePath?: string;
}

interface UseFileMentionsOptions {
  selectedProject: Project | null;
  input: string;
  setInput: Dispatch<SetStateAction<string>>;
  textareaRef: RefObject<HTMLTextAreaElement>;
}

export function useFileMentions({ selectedProject: _selectedProject, input, setInput, textareaRef }: UseFileMentionsOptions) {
  const [entityMentions, setEntityMentions] = useState<string[]>([]);
  const [filteredFiles, setFilteredFiles] = useState<MentionableFile[]>([]);
  const [showFileDropdown, setShowFileDropdown] = useState(false);
  const [selectedFileIndex, setSelectedFileIndex] = useState(-1);
  const [cursorPosition, setCursorPosition] = useState(0);
  const [atSymbolPosition, setAtSymbolPosition] = useState(-1);

  useEffect(() => {
    const textBeforeCursor = input.slice(0, cursorPosition);
    const lastAtIndex = textBeforeCursor.lastIndexOf('@');

    if (lastAtIndex === -1) {
      setShowFileDropdown(false);
      setAtSymbolPosition(-1);
      return;
    }

    const textAfterAt = textBeforeCursor.slice(lastAtIndex + 1);
    if (/\s/.test(textAfterAt) || textAfterAt.length > 80) {
      setShowFileDropdown(false);
      setAtSymbolPosition(-1);
      return;
    }

    setAtSymbolPosition(lastAtIndex);
    setShowFileDropdown(true);
    setSelectedFileIndex(-1);

    let cancelled = false;
    const handle = window.setTimeout(() => {
      entitiesApi.suggest(textAfterAt, 10)
        .then((items) => {
          if (cancelled) return;
          setFilteredFiles(items.map((item) => ({
            name: item.title,
            path: item.display,
            relativePath: item.uri,
          })));
        })
        .catch(() => {
          if (!cancelled) setFilteredFiles([]);
        });
    }, 120);

    return () => {
      cancelled = true;
      window.clearTimeout(handle);
    };
  }, [input, cursorPosition]);

  const activeEntityMentions = useMemo(() => {
    if (!input || entityMentions.length === 0) {
      return [];
    }
    return entityMentions.filter((display) => input.includes(display));
  }, [entityMentions, input]);

  const sortedEntityMentions = useMemo(() => {
    if (activeEntityMentions.length === 0) {
      return [];
    }
    const uniqueMentions = Array.from(new Set(activeEntityMentions));
    return uniqueMentions.sort((mentionA, mentionB) => mentionB.length - mentionA.length);
  }, [activeEntityMentions]);

  const entityMentionRegex = useMemo(() => {
    if (sortedEntityMentions.length === 0) {
      return null;
    }
    const pattern = sortedEntityMentions.map(escapeRegExp).join('|');
    return new RegExp(`(${pattern})`, 'g');
  }, [sortedEntityMentions]);

  const entityMentionSet = useMemo(() => new Set(sortedEntityMentions), [sortedEntityMentions]);

  const renderInputWithMentions = useCallback(
    (text: string) => {
      if (!text) {
        return '';
      }
      if (!entityMentionRegex) {
        return text;
      }

      const parts = text.split(entityMentionRegex);
      return parts.map((part, index) =>
        entityMentionSet.has(part) ? (
          <span
            key={`mention-${index}`}
            className="-ml-0.5 rounded-md bg-blue-200/70 box-decoration-clone px-0.5 text-transparent dark:bg-blue-300/40"
          >
            {part}
          </span>
        ) : (
          <span key={`text-${index}`}>{part}</span>
        ),
      );
    },
    [entityMentionRegex, entityMentionSet],
  );

  const selectFile = useCallback(
    (file: MentionableFile) => {
      const textBeforeAt = input.slice(0, atSymbolPosition);
      const textAfterAtQuery = input.slice(atSymbolPosition);
      const spaceIndex = textAfterAtQuery.indexOf(' ');
      const textAfterQuery = spaceIndex !== -1 ? textAfterAtQuery.slice(spaceIndex) : '';

      const display = file.path;
      const newInput = `${textBeforeAt}${display} ${textAfterQuery}`;
      const newCursorPosition = textBeforeAt.length + display.length + 1;

      if (textareaRef.current && !textareaRef.current.matches(':focus')) {
        textareaRef.current.focus();
      }

      setInput(newInput);
      setCursorPosition(newCursorPosition);
      setEntityMentions((previousMentions) =>
        previousMentions.includes(display) ? previousMentions : [...previousMentions, display],
      );

      setShowFileDropdown(false);
      setAtSymbolPosition(-1);

      if (!textareaRef.current) {
        return;
      }

      requestAnimationFrame(() => {
        if (!textareaRef.current) {
          return;
        }
        textareaRef.current.setSelectionRange(newCursorPosition, newCursorPosition);
        if (!textareaRef.current.matches(':focus')) {
          textareaRef.current.focus();
        }
      });
    },
    [input, atSymbolPosition, textareaRef, setInput],
  );

  const handleFileMentionsKeyDown = useCallback(
    (event: KeyboardEvent<HTMLTextAreaElement>): boolean => {
      if (!showFileDropdown || filteredFiles.length === 0) {
        return false;
      }

      if (event.key === 'ArrowDown') {
        event.preventDefault();
        setSelectedFileIndex((previousIndex) =>
          previousIndex < filteredFiles.length - 1 ? previousIndex + 1 : 0,
        );
        return true;
      }

      if (event.key === 'ArrowUp') {
        event.preventDefault();
        setSelectedFileIndex((previousIndex) =>
          previousIndex > 0 ? previousIndex - 1 : filteredFiles.length - 1,
        );
        return true;
      }

      if (event.key === 'Tab' || event.key === 'Enter') {
        event.preventDefault();
        if (selectedFileIndex >= 0) {
          selectFile(filteredFiles[selectedFileIndex]);
        } else if (filteredFiles.length > 0) {
          selectFile(filteredFiles[0]);
        }
        return true;
      }

      if (event.key === 'Escape') {
        event.preventDefault();
        setShowFileDropdown(false);
        return true;
      }

      return false;
    },
    [showFileDropdown, filteredFiles, selectedFileIndex, selectFile],
  );

  return {
    showFileDropdown,
    filteredFiles,
    selectedFileIndex,
    renderInputWithMentions,
    selectFile,
    setCursorPosition,
    handleFileMentionsKeyDown,
  };
}
