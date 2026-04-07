'use client'

import { ExternalLink, CheckCircle2, XCircle, AlertCircle, HelpCircle, GitBranch } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import type { AuditClaim, AuditClaimStatus, AuditResult, AuditVerdict } from '@/lib/types'
import MarkdownContent from '@/components/MarkdownContent'

const VERDICT_CONFIG: Record<AuditVerdict, { label: string; className: string }> = {
  matches:        { label: 'Claims Match',    className: 'bg-emerald-900/40 text-emerald-300 border-emerald-700' },
  partial_match:  { label: 'Partial Match',   className: 'bg-amber-900/40  text-amber-300  border-amber-700'    },
  mismatch:       { label: 'Mismatch',        className: 'bg-red-900/40    text-red-300    border-red-700'      },
  no_repo_found:  { label: 'No Repo Found',   className: 'bg-slate-700/40  text-slate-400  border-slate-600'   },
}

const CLAIM_CONFIG: Record<AuditClaimStatus, { label: string; Icon: React.ElementType; className: string }> = {
  verified:           { label: 'Verified',           Icon: CheckCircle2, className: 'text-emerald-400' },
  partially_verified: { label: 'Partial',            Icon: AlertCircle,  className: 'text-amber-400'  },
  unverified:         { label: 'Unverified',         Icon: HelpCircle,   className: 'text-slate-400'  },
  contradicted:       { label: 'Contradicted',       Icon: XCircle,      className: 'text-red-400'    },
}

function ClaimRow({ claim }: { claim: AuditClaim }) {
  const cfg = CLAIM_CONFIG[claim.status]
  const Icon = cfg.Icon
  return (
    <div className="rounded-lg border border-slate-800 bg-slate-900/40 p-4 space-y-2">
      <div className="flex items-start gap-2">
        <Icon className={`mt-0.5 h-4 w-4 flex-shrink-0 ${cfg.className}`} />
        <p className="text-sm text-slate-200 leading-snug flex-1">{claim.claim}</p>
        <span className={`text-[10px] font-semibold ${cfg.className} flex-shrink-0`}>{cfg.label}</span>
      </div>
      {claim.evidence && (
        <p className="text-xs text-slate-400 pl-6 leading-relaxed">{claim.evidence}</p>
      )}
      {claim.evidence_url && (
        <a
          href={claim.evidence_url}
          target="_blank"
          rel="noopener noreferrer"
          className="flex items-center gap-1 text-[11px] text-indigo-400 hover:text-indigo-300 pl-6"
        >
          <ExternalLink className="h-3 w-3" />
          View evidence
        </a>
      )}
    </div>
  )
}

export default function AuditReport({ result }: { result: AuditResult }) {
  const verdictCfg = VERDICT_CONFIG[result.verdict]
  const verified   = result.claims.filter(c => c.status === 'verified').length
  const partial    = result.claims.filter(c => c.status === 'partially_verified').length
  const unverified = result.claims.filter(c => c.status === 'unverified').length
  const contradicted = result.claims.filter(c => c.status === 'contradicted').length

  return (
    <div className="space-y-6">
      {/* Header */}
      <Card className="border-slate-800 bg-slate-900/50">
        <CardHeader className="pb-3">
          <div className="flex items-start justify-between gap-4">
            <div className="space-y-1">
              <CardTitle className="text-lg text-slate-100">{result.paper_title || 'Audit Result'}</CardTitle>
              {result.paper_url && (
                <a href={result.paper_url} target="_blank" rel="noopener noreferrer"
                   className="flex items-center gap-1 text-xs text-indigo-400 hover:text-indigo-300">
                  <ExternalLink className="h-3 w-3" /> Paper
                </a>
              )}
            </div>
            <span className={`rounded border px-2.5 py-1 text-xs font-semibold ${verdictCfg.className}`}>
              {verdictCfg.label}
            </span>
          </div>
        </CardHeader>
        <CardContent className="space-y-3">
          {result.repo_url ? (
            <a href={result.repo_url} target="_blank" rel="noopener noreferrer"
               className="flex items-center gap-2 text-sm text-slate-300 hover:text-slate-100">
              <GitBranch className="h-4 w-4 text-slate-500" />
              {result.repo_url}
            </a>
          ) : (
            <p className="text-sm text-slate-500">No public repository found.</p>
          )}

          {/* Claim summary stats */}
          <div className="flex flex-wrap gap-3 pt-1">
            <span className="flex items-center gap-1.5 text-xs text-emerald-400">
              <CheckCircle2 className="h-3.5 w-3.5" /> {verified} verified
            </span>
            <span className="flex items-center gap-1.5 text-xs text-amber-400">
              <AlertCircle className="h-3.5 w-3.5" /> {partial} partial
            </span>
            <span className="flex items-center gap-1.5 text-xs text-slate-400">
              <HelpCircle className="h-3.5 w-3.5" /> {unverified} unverified
            </span>
            {contradicted > 0 && (
              <span className="flex items-center gap-1.5 text-xs text-red-400">
                <XCircle className="h-3.5 w-3.5" /> {contradicted} contradicted
              </span>
            )}
            <span className="ml-auto text-xs text-slate-500 font-mono">
              confidence {Math.round(result.confidence * 100)}%
            </span>
          </div>

          {result.audit_notes && (
            <div className="border-t border-slate-800 pt-3">
              <MarkdownContent className="[&_p]:text-slate-400">{result.audit_notes}</MarkdownContent>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Claims */}
      {result.claims.length > 0 && (
        <div className="space-y-3">
          <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-500">
            Claims ({result.claims.length})
          </h3>
          {result.claims.map((claim, i) => (
            <ClaimRow key={i} claim={claim} />
          ))}
        </div>
      )}
    </div>
  )
}
