'use client'

import { useState, useEffect, useRef } from 'react'
import { FileText, Upload, Trash2, Send, Loader2, BookOpen, X, ChevronDown, ChevronUp } from 'lucide-react'
import Link from 'next/link'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Card, CardContent, CardHeader } from '@/components/ui/card'
import { uploadDocument, listDocuments, deleteDocument, askDocuments } from '@/lib/api'
import type { DocRecord, DocsQAResult, DocChunkRef } from '@/lib/types'

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

function DocCard({ doc, onDelete }: { doc: DocRecord; onDelete: (id: string) => void }) {
  const [deleting, setDeleting] = useState(false)

  async function handleDelete() {
    if (!confirm(`Delete "${doc.title}"?`)) return
    setDeleting(true)
    try {
      await deleteDocument(doc.doc_id)
      onDelete(doc.doc_id)
    } catch {
      setDeleting(false)
    }
  }

  return (
    <div className="flex items-center justify-between gap-3 rounded-lg border border-slate-700 bg-slate-800/50 px-4 py-3">
      <div className="flex items-center gap-3 min-w-0">
        <FileText className="h-4 w-4 flex-shrink-0 text-violet-400" />
        <div className="min-w-0">
          <p className="text-sm font-medium text-slate-200 truncate">{doc.title}</p>
          <p className="text-xs text-slate-500">
            {doc.chunk_count} chunks · {doc.page_count} pages · {formatBytes(doc.size_bytes)}
          </p>
        </div>
      </div>
      <button
        onClick={handleDelete}
        disabled={deleting}
        className="flex-shrink-0 p-1.5 rounded-md text-slate-600 hover:text-red-400 hover:bg-red-900/20 transition-colors disabled:opacity-40"
      >
        {deleting ? <Loader2 className="h-4 w-4 animate-spin" /> : <Trash2 className="h-4 w-4" />}
      </button>
    </div>
  )
}

function SourceCard({ source }: { source: DocChunkRef }) {
  const [expanded, setExpanded] = useState(false)
  return (
    <div className="rounded-lg border border-slate-700 bg-slate-800/30 p-3 text-xs">
      <button
        className="flex w-full items-center justify-between gap-2 text-left"
        onClick={() => setExpanded(v => !v)}
      >
        <span className="font-medium text-slate-300">
          {source.doc_title} · chunk {source.chunk_index + 1}
        </span>
        {expanded ? <ChevronUp className="h-3.5 w-3.5 text-slate-500" /> : <ChevronDown className="h-3.5 w-3.5 text-slate-500" />}
      </button>
      {expanded && (
        <p className="mt-2 text-slate-400 leading-relaxed whitespace-pre-wrap">{source.content}</p>
      )}
    </div>
  )
}

interface ChatMessage {
  role: 'user' | 'assistant'
  text: string
  sources?: DocChunkRef[]
}

export default function DocsPage() {
  const [docs, setDocs]               = useState<DocRecord[]>([])
  const [loadingDocs, setLoadingDocs] = useState(true)
  const [uploading, setUploading]     = useState(false)
  const [uploadError, setUploadError] = useState<string | null>(null)
  const [question, setQuestion]       = useState('')
  const [asking, setAsking]           = useState(false)
  const [messages, setMessages]       = useState<ChatMessage[]>([])
  const [askError, setAskError]       = useState<string | null>(null)
  const fileInputRef                  = useRef<HTMLInputElement>(null)
  const chatBottomRef                 = useRef<HTMLDivElement>(null)

  useEffect(() => {
    listDocuments()
      .then(setDocs)
      .catch(() => {})
      .finally(() => setLoadingDocs(false))
  }, [])

  useEffect(() => {
    chatBottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  async function handleUpload(files: FileList | null) {
    if (!files || files.length === 0) return
    setUploading(true)
    setUploadError(null)
    const errors: string[] = []
    const newDocs: DocRecord[] = []
    for (const file of Array.from(files)) {
      try {
        const doc = await uploadDocument(file)
        newDocs.push(doc)
      } catch (err) {
        errors.push(`${file.name}: ${err instanceof Error ? err.message : 'Upload failed'}`)
      }
    }
    setDocs(prev => [...newDocs, ...prev])
    if (errors.length > 0) setUploadError(errors.join('\n'))
    setUploading(false)
    if (fileInputRef.current) fileInputRef.current.value = ''
  }

  async function handleAsk(e: React.FormEvent) {
    e.preventDefault()
    if (!question.trim() || asking) return
    const q = question.trim()
    setQuestion('')
    setAsking(true)
    setAskError(null)
    setMessages(prev => [...prev, { role: 'user', text: q }])
    try {
      const result = await askDocuments(q)
      setMessages(prev => [...prev, {
        role: 'assistant',
        text: result.answer,
        sources: result.sources,
      }])
    } catch (err) {
      setAskError(err instanceof Error ? err.message : 'Request failed')
    } finally {
      setAsking(false)
    }
  }

  function handleDrop(e: React.DragEvent) {
    e.preventDefault()
    handleUpload(e.dataTransfer.files)
  }

  return (
    <main className="min-h-screen bg-[#0a0f1e] text-slate-100">
      <div className="mx-auto max-w-5xl px-4 py-12 space-y-8">

        {/* Header */}
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2 text-violet-400">
              <BookOpen className="h-5 w-5" />
              <span className="text-sm font-semibold uppercase tracking-wider">Document Q&A</span>
            </div>
            <Link href="/" className="text-xs text-slate-500 hover:text-slate-300 transition-colors">← Home</Link>
          </div>
          <h1 className="text-3xl font-bold text-slate-100">Chat with your Documents</h1>
          <p className="text-slate-400">
            Upload PDFs, text files, or markdown — then ask questions answered from your own documents.
          </p>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-5 gap-6">

          {/* Left column: upload + document list */}
          <div className="lg:col-span-2 space-y-4">

            {/* Upload area */}
            <Card className="border-slate-800 bg-slate-900/50">
              <CardHeader className="pb-2 pt-4 px-4">
                <span className="text-xs font-semibold uppercase tracking-wider text-slate-500">Upload</span>
              </CardHeader>
              <CardContent className="px-4 pb-4 space-y-3">
                <div
                  className="flex flex-col items-center justify-center gap-2 rounded-lg border-2 border-dashed border-slate-700 bg-slate-800/30 py-8 cursor-pointer hover:border-violet-700/60 hover:bg-violet-900/10 transition-all"
                  onClick={() => fileInputRef.current?.click()}
                  onDrop={handleDrop}
                  onDragOver={e => e.preventDefault()}
                >
                  {uploading
                    ? <Loader2 className="h-6 w-6 text-violet-400 animate-spin" />
                    : <Upload className="h-6 w-6 text-slate-500" />
                  }
                  <p className="text-sm text-slate-400">
                    {uploading ? 'Processing…' : 'Drop files or click to upload'}
                  </p>
                  <p className="text-xs text-slate-600">PDF · TXT · MD · TEX · max 50 MB</p>
                </div>
                <input
                  ref={fileInputRef}
                  type="file"
                  multiple
                  accept=".pdf,.txt,.md,.tex"
                  className="hidden"
                  onChange={e => handleUpload(e.target.files)}
                />
                {uploadError && (
                  <div className="rounded-md border border-red-800 bg-red-900/20 px-3 py-2 text-xs text-red-300 whitespace-pre-wrap">
                    {uploadError}
                    <button onClick={() => setUploadError(null)} className="ml-2 text-red-500 hover:text-red-300">
                      <X className="h-3 w-3 inline" />
                    </button>
                  </div>
                )}
              </CardContent>
            </Card>

            {/* Document list */}
            <Card className="border-slate-800 bg-slate-900/50">
              <CardHeader className="pb-2 pt-4 px-4">
                <span className="text-xs font-semibold uppercase tracking-wider text-slate-500">
                  Documents ({docs.length})
                </span>
              </CardHeader>
              <CardContent className="px-4 pb-4 space-y-2">
                {loadingDocs && (
                  <p className="text-xs text-slate-600 py-4 text-center">Loading…</p>
                )}
                {!loadingDocs && docs.length === 0 && (
                  <p className="text-xs text-slate-600 py-4 text-center">No documents yet — upload one above.</p>
                )}
                {docs.map(doc => (
                  <DocCard
                    key={doc.doc_id}
                    doc={doc}
                    onDelete={id => setDocs(prev => prev.filter(d => d.doc_id !== id))}
                  />
                ))}
              </CardContent>
            </Card>
          </div>

          {/* Right column: chat */}
          <div className="lg:col-span-3 flex flex-col">
            <Card className="border-slate-800 bg-slate-900/50 flex flex-col flex-1 min-h-[600px]">
              <CardHeader className="pb-2 pt-4 px-4 border-b border-slate-800">
                <span className="text-xs font-semibold uppercase tracking-wider text-slate-500">
                  Ask your documents
                </span>
              </CardHeader>

              {/* Messages */}
              <CardContent className="flex-1 overflow-y-auto px-4 py-4 space-y-4">
                {messages.length === 0 && (
                  <div className="flex h-full items-center justify-center text-center">
                    <div className="space-y-2">
                      <BookOpen className="h-8 w-8 text-slate-700 mx-auto" />
                      <p className="text-sm text-slate-600">
                        Upload documents on the left, then ask anything about them.
                      </p>
                    </div>
                  </div>
                )}

                {messages.map((msg, i) => (
                  <div key={i} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                    <div className={`max-w-[85%] space-y-2 ${msg.role === 'user' ? 'items-end' : 'items-start'} flex flex-col`}>
                      <div className={`rounded-2xl px-4 py-2.5 text-sm leading-relaxed ${
                        msg.role === 'user'
                          ? 'bg-violet-700 text-white rounded-br-sm'
                          : 'bg-slate-800 text-slate-200 rounded-bl-sm border border-slate-700'
                      }`}>
                        <p className="whitespace-pre-wrap">{msg.text}</p>
                      </div>
                      {msg.sources && msg.sources.length > 0 && (
                        <div className="w-full space-y-1">
                          <p className="text-[10px] uppercase tracking-wider text-slate-600 px-1">Sources</p>
                          {msg.sources.map((s, j) => (
                            <SourceCard key={j} source={s} />
                          ))}
                        </div>
                      )}
                    </div>
                  </div>
                ))}

                {asking && (
                  <div className="flex justify-start">
                    <div className="rounded-2xl rounded-bl-sm bg-slate-800 border border-slate-700 px-4 py-3">
                      <Loader2 className="h-4 w-4 animate-spin text-violet-400" />
                    </div>
                  </div>
                )}

                {askError && (
                  <div className="rounded-md border border-red-800 bg-red-900/20 px-3 py-2 text-xs text-red-300">
                    {askError}
                  </div>
                )}

                <div ref={chatBottomRef} />
              </CardContent>

              {/* Input */}
              <div className="border-t border-slate-800 px-4 py-3">
                <form onSubmit={handleAsk} className="flex gap-2">
                  <Input
                    value={question}
                    onChange={e => setQuestion(e.target.value)}
                    placeholder={docs.length === 0 ? 'Upload a document first…' : 'Ask anything about your documents…'}
                    disabled={asking || docs.length === 0}
                    className="flex-1"
                    onKeyDown={e => {
                      if (e.key === 'Enter' && !e.shiftKey) {
                        e.preventDefault()
                        if (question.trim() && !asking) handleAsk(e as any)
                      }
                    }}
                  />
                  <Button
                    type="submit"
                    disabled={!question.trim() || asking || docs.length === 0}
                    className="bg-violet-700 hover:bg-violet-600 px-3"
                  >
                    {asking
                      ? <Loader2 className="h-4 w-4 animate-spin" />
                      : <Send className="h-4 w-4" />
                    }
                  </Button>
                </form>
              </div>
            </Card>
          </div>
        </div>
      </div>
    </main>
  )
}
