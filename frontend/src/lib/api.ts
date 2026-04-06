import type { Depth, GraphData, ResearchSession, SSEEvent } from '@/lib/types'

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'

async function fetchJSON<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE_URL}${path}`, {
    headers: {
      'Content-Type': 'application/json',
      ...options?.headers,
    },
    ...options,
  })

  if (!res.ok) {
    const text = await res.text().catch(() => 'Unknown error')
    throw new Error(`API error ${res.status}: ${text}`)
  }

  return res.json() as Promise<T>
}

export async function startResearch(
  input: string,
  depth: Depth
): Promise<{ session_id: string }> {
  return fetchJSON<{ session_id: string }>('/api/research', {
    method: 'POST',
    body: JSON.stringify({ input, depth }),
  })
}

export async function getSession(sessionId: string): Promise<ResearchSession> {
  return fetchJSON<ResearchSession>(`/api/research/${sessionId}`)
}

export async function getGraph(sessionId: string): Promise<GraphData> {
  return fetchJSON<GraphData>(`/api/research/${sessionId}/graph`)
}

export async function getGlobalGraph(): Promise<GraphData & { total_papers: number }> {
  return fetchJSON<GraphData & { total_papers: number }>('/api/graph/global')
}

export interface SessionSummary {
  session_id: string
  input: string
  status: 'running' | 'completed' | 'error'
  created_at: string
  has_result: boolean
}

export async function listSessions(limit = 20): Promise<SessionSummary[]> {
  return fetchJSON<SessionSummary[]>(`/api/sessions?limit=${limit}`)
}

// ---------------------------------------------------------------------------
// Review API
// ---------------------------------------------------------------------------

export interface ReviewerReport {
  reviewer_id: number
  persona: string
  status: 'pending' | 'running' | 'done' | 'error'
  novelty_score: number
  technical_score: number
  clarity_score: number
  contribution_score: number
  overall_score: number
  recommendation: 'accept' | 'minor_revision' | 'major_revision' | 'reject'
  strengths: string[]
  major_issues: string[]
  minor_issues: string[]
  missing_citations: string[]
  related_papers_found: string[]
  summary: string
  error?: string
}

export interface EditorReport {
  final_recommendation: 'accept' | 'minor_revision' | 'major_revision' | 'reject'
  novelty_score: number
  technical_score: number
  clarity_score: number
  contribution_score: number
  overall_score: number
  novelty_verdict: string
  publishability: string
  consensus_summary: string
  major_issues: string[]
  minor_issues: string[]
  strengths: string[]
  action_items: string[]
  reviewer_agreement: number
}

export interface ReviewSession {
  session_id: string
  status: 'running' | 'completed' | 'error'
  paper_title: string
  paper_abstract: string
  filename: string
  num_reviewers: number
  reviewer_reports: ReviewerReport[]
  editor_report: EditorReport | null
  created_at: string
  progress: { percentage: number; logs: Array<{ timestamp: string; message: string; level: string }> }
}

export async function startReview(
  paperFile: File,
  numReviewers: number,
  bibFile?: File,
): Promise<{ session_id: string; paper_title: string }> {
  const form = new FormData()
  form.append('paper_file', paperFile)
  form.append('num_reviewers', String(numReviewers))
  if (bibFile) form.append('bib_file', bibFile)

  const res = await fetch(`${API_BASE_URL}/api/review`, { method: 'POST', body: form })
  if (!res.ok) {
    const text = await res.text().catch(() => 'Unknown error')
    throw new Error(`API error ${res.status}: ${text}`)
  }
  return res.json()
}

export async function getReviewSession(sessionId: string): Promise<ReviewSession> {
  return fetchJSON<ReviewSession>(`/api/review/${sessionId}`)
}

export function streamReview(
  sessionId: string,
  onEvent: (event: SSEEvent & { reviewer_id?: number; status?: string; recommendation?: string; overall_score?: number }) => void,
): () => void {
  const url = `${API_BASE_URL}/api/review/${sessionId}/stream`
  const es = new EventSource(url)

  es.addEventListener('progress', (e: MessageEvent) => {
    try { onEvent(JSON.parse(e.data as string)) } catch {}
  })
  es.addEventListener('complete', (e: MessageEvent) => {
    try { onEvent({ ...JSON.parse(e.data as string), type: 'complete' }) } catch { onEvent({ type: 'complete' }) }
    es.close()
  })
  es.onerror = () => { onEvent({ type: 'error', message: 'Stream error' }); es.close() }
  return () => es.close()
}

export function streamSession(
  sessionId: string,
  onEvent: (event: SSEEvent) => void
): () => void {
  const url = `${API_BASE_URL}/api/research/${sessionId}/stream`
  const eventSource = new EventSource(url)

  eventSource.addEventListener('progress', (e: MessageEvent) => {
    try {
      const data = JSON.parse(e.data as string) as SSEEvent
      onEvent(data)
    } catch {
      // ignore parse errors
    }
  })

  eventSource.addEventListener('complete', (e: MessageEvent) => {
    try {
      const data = JSON.parse(e.data as string) as SSEEvent
      onEvent(data)
    } catch {
      onEvent({ type: 'complete' })
    }
    eventSource.close()
  })

  eventSource.addEventListener('error', (e: MessageEvent) => {
    try {
      const data = JSON.parse(e.data as string) as SSEEvent
      onEvent(data)
    } catch {
      onEvent({ type: 'error', message: 'Stream connection error' })
    }
    eventSource.close()
  })

  eventSource.onerror = () => {
    onEvent({ type: 'error', message: 'Failed to connect to stream' })
    eventSource.close()
  }

  return () => {
    eventSource.close()
  }
}
