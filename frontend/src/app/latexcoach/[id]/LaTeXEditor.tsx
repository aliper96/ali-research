'use client'

import React, { useCallback } from 'react'
import CodeMirror from '@uiw/react-codemirror'
import { githubLight } from '@uiw/codemirror-theme-github'
import { StreamLanguage } from '@codemirror/language'
import { stex } from '@codemirror/legacy-modes/mode/stex'
import { lineNumbers, highlightActiveLineGutter, highlightActiveLine } from '@codemirror/view'
import { EditorView } from '@codemirror/view'

const latexExtensions = [
  StreamLanguage.define(stex),
  lineNumbers(),
  highlightActiveLineGutter(),
  highlightActiveLine(),
  EditorView.theme({
    '&': { fontSize: '12px', height: '100%' },
    '.cm-scroller': { fontFamily: "'JetBrains Mono', 'Fira Code', 'Cascadia Code', monospace", overflow: 'auto', lineHeight: '1.6' },
    '.cm-gutters': { backgroundColor: '#f6f8fa', borderRight: '1px solid #d0d7de', color: '#8b949e', minWidth: '3rem' },
    '.cm-lineNumbers .cm-gutterElement': { paddingRight: '12px', textAlign: 'right' },
    '.cm-activeLineGutter': { backgroundColor: '#fff8c5' },
    '.cm-activeLine': { backgroundColor: '#fffbdd' },
    '.cm-content': { padding: '0' },
  }),
]

interface LaTeXEditorProps {
  value: string
  onChange: (val: string) => void
}

export default function LaTeXEditor({ value, onChange }: LaTeXEditorProps) {
  const handleChange = useCallback((val: string) => onChange(val), [onChange])

  return (
    <CodeMirror
      value={value}
      height="100%"
      theme={githubLight}
      extensions={latexExtensions}
      onChange={handleChange}
      basicSetup={{
        lineNumbers: false,        // handled manually above for custom styling
        foldGutter: true,
        dropCursor: true,
        allowMultipleSelections: true,
        indentOnInput: true,
        bracketMatching: true,
        closeBrackets: true,
        autocompletion: false,
        highlightActiveLine: false, // handled manually
        highlightSelectionMatches: true,
      }}
      style={{ height: '100%' }}
    />
  )
}
