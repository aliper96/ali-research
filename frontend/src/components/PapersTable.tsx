'use client'

import React, { useState, useMemo } from 'react'
import {
  useReactTable,
  getCoreRowModel,
  getSortedRowModel,
  getFilteredRowModel,
  getPaginationRowModel,
  flexRender,
  createColumnHelper,
  type SortingState,
  type ExpandedState,
} from '@tanstack/react-table'
import {
  ChevronUp,
  ChevronDown,
  ChevronsUpDown,
  ExternalLink,
  ChevronRight,
  Search,
  FileText,
  BookOpen,
  ScanText,
  Sparkles,
  CheckCircle2,
  XCircle,
} from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { cn, formatAuthors, formatCitationCount, getRelevanceColor, truncateText } from '@/lib/utils'
import type { Paper, PaperSource, ReadStatus } from '@/lib/types'

const columnHelper = createColumnHelper<Paper>()

interface PapersTableProps {
  papers: Paper[]
}

function RelevanceBar({ score }: { score: number }) {
  const pct = Math.round(score * 100)
  const color = getRelevanceColor(score)

  return (
    <div className="flex items-center gap-2">
      <div className="h-1.5 w-16 overflow-hidden rounded-full bg-slate-800">
        <div
          className="h-full rounded-full transition-all"
          style={{ width: `${pct}%`, backgroundColor: color }}
        />
      </div>
      <span
        className="text-xs font-mono font-semibold tabular-nums"
        style={{ color }}
      >
        {pct}%
      </span>
    </div>
  )
}

const SOURCE_CONFIG: Record<PaperSource, { label: string; className: string }> = {
  arxiv:            { label: 'arXiv',    className: 'bg-violet-900/40 text-violet-300 border-violet-700/50' },
  semantic_scholar: { label: 'S2',       className: 'bg-blue-900/40  text-blue-300  border-blue-700/50'    },
  web:              { label: 'Web',      className: 'bg-slate-700/40 text-slate-400 border-slate-600/50'   },
  crossref:         { label: 'CrossRef', className: 'bg-green-900/40 text-green-300 border-green-700/50'   },
}

function SourceBadge({ source }: { source: PaperSource | null }) {
  if (!source) return null
  const cfg = SOURCE_CONFIG[source]
  return (
    <span className={cn('inline-block rounded border px-1.5 py-px text-[10px] font-mono font-semibold leading-none', cfg.className)}>
      {cfg.label}
    </span>
  )
}

const READ_STATUS_CONFIG: Record<ReadStatus, { label: string; Icon: React.ElementType; className: string }> = {
  full_text:      { label: 'Full text',  Icon: BookOpen,  className: 'text-emerald-400' },
  abstract_only:  { label: 'Abstract',   Icon: ScanText,  className: 'text-amber-400'   },
  inferred:       { label: 'Inferred',   Icon: Sparkles,  className: 'text-slate-500'   },
}

function ReadStatusBadge({ status }: { status: ReadStatus | null }) {
  if (!status) return null
  const cfg = READ_STATUS_CONFIG[status]
  const Icon = cfg.Icon
  return (
    <span className={cn('flex items-center gap-1 text-[10px] font-medium', cfg.className)} title={cfg.label}>
      <Icon className="h-3 w-3 flex-shrink-0" />
      <span className="hidden sm:inline">{cfg.label}</span>
    </span>
  )
}

function ExpandedRow({ paper }: { paper: Paper }) {
  return (
    <div className="px-4 py-4 space-y-4 bg-slate-950/50 border-t border-slate-800">
      <div>
        <h4 className="text-xs font-semibold uppercase tracking-wider text-slate-500 mb-2">
          Abstract
        </h4>
        <p className="text-sm text-slate-300 leading-relaxed">{paper.abstract}</p>
      </div>
      <div>
        <h4 className="text-xs font-semibold uppercase tracking-wider text-slate-500 mb-2">
          Relevance Reason
        </h4>
        <p className="text-sm text-indigo-300 leading-relaxed">{paper.relevance_reason}</p>
      </div>
      {paper.venue && (
        <div>
          <h4 className="text-xs font-semibold uppercase tracking-wider text-slate-500 mb-1">
            Venue
          </h4>
          <p className="text-sm text-slate-300">{paper.venue}</p>
        </div>
      )}
      <div className="flex flex-wrap items-center gap-4 text-xs text-slate-500 font-mono">
        {paper.arxiv_id && (
          <span>arXiv: {paper.arxiv_id}</span>
        )}
        {paper.doi && (
          <span>DOI: {paper.doi}</span>
        )}
      </div>
    </div>
  )
}

export default function PapersTable({ papers }: PapersTableProps) {
  const [sorting, setSorting] = useState<SortingState>([
    { id: 'relevance_score', desc: true },
  ])
  const [globalFilter, setGlobalFilter] = useState('')
  const [expanded, setExpanded] = useState<ExpandedState>({})

  const columns = useMemo(
    () => [
      // Expand toggle
      columnHelper.display({
        id: 'expand',
        size: 40,
        cell: ({ row }) => (
          <button
            onClick={row.getToggleExpandedHandler()}
            className="flex items-center justify-center rounded p-1 text-slate-500 transition-colors hover:bg-slate-800 hover:text-slate-300"
          >
            <ChevronRight
              className={cn(
                'h-4 w-4 transition-transform duration-200',
                row.getIsExpanded() && 'rotate-90'
              )}
            />
          </button>
        ),
      }),
      // Relevance
      columnHelper.accessor('relevance_score', {
        header: 'Relevance',
        size: 120,
        cell: ({ getValue }) => <RelevanceBar score={getValue()} />,
        sortDescFirst: true,
      }),
      // Title
      columnHelper.accessor('title', {
        header: 'Title',
        cell: ({ getValue, row }) => {
          const paper = row.original
          return (
            <div className="space-y-1">
              <a
                href={paper.url}
                target="_blank"
                rel="noopener noreferrer"
                className="group flex items-start gap-1.5 text-sm font-medium text-slate-200 hover:text-indigo-300 transition-colors leading-snug"
                onClick={(e) => e.stopPropagation()}
              >
                <span className="line-clamp-2">{getValue()}</span>
                <ExternalLink className="mt-0.5 h-3 w-3 flex-shrink-0 opacity-0 group-hover:opacity-100 transition-opacity" />
              </a>
              <div className="flex items-center gap-1.5 flex-wrap">
                <SourceBadge source={paper.source} />
                {paper.url_verified === true && (
                  <span title="URL verified" className="flex items-center gap-0.5 text-[10px] text-emerald-500">
                    <CheckCircle2 className="h-3 w-3" />
                  </span>
                )}
                {paper.url_verified === false && (
                  <span title="URL unreachable" className="flex items-center gap-0.5 text-[10px] text-red-500">
                    <XCircle className="h-3 w-3" />
                  </span>
                )}
              </div>
            </div>
          )
        },
        enableSorting: false,
      }),
      // Authors
      columnHelper.accessor('authors', {
        header: 'Authors',
        size: 150,
        cell: ({ getValue }) => (
          <span className="text-xs text-slate-400">{formatAuthors(getValue())}</span>
        ),
        enableSorting: false,
      }),
      // Year
      columnHelper.accessor('year', {
        header: 'Year',
        size: 70,
        cell: ({ getValue }) => {
          const year = getValue()
          return (
            <span className="font-mono text-xs text-slate-400">
              {year ?? '—'}
            </span>
          )
        },
      }),
      // Citations
      columnHelper.accessor('citation_count', {
        header: 'Citations',
        size: 90,
        cell: ({ getValue }) => (
          <span className="font-mono text-xs font-medium text-slate-300">
            {formatCitationCount(getValue())}
          </span>
        ),
        sortDescFirst: true,
      }),
      // Read status
      columnHelper.accessor('read_status', {
        header: 'Read',
        size: 100,
        cell: ({ getValue }) => <ReadStatusBadge status={getValue()} />,
        enableSorting: false,
      }),
      // Tags
      columnHelper.accessor('tags', {
        header: 'Tags',
        size: 200,
        cell: ({ getValue }) => {
          const tags = getValue()
          return (
            <div className="flex flex-wrap gap-1">
              {tags.slice(0, 3).map((tag) => (
                <Badge key={tag} variant="secondary" className="text-[10px] py-0 px-1.5">
                  {truncateText(tag, 15)}
                </Badge>
              ))}
              {tags.length > 3 && (
                <Badge variant="outline" className="text-[10px] py-0 px-1.5">
                  +{tags.length - 3}
                </Badge>
              )}
            </div>
          )
        },
        enableSorting: false,
      }),
    ],
    []
  )

  const table = useReactTable({
    data: papers,
    columns,
    state: {
      sorting,
      globalFilter,
      expanded,
    },
    onSortingChange: setSorting,
    onGlobalFilterChange: setGlobalFilter,
    onExpandedChange: setExpanded,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
    getRowCanExpand: () => true,
    initialState: {
      pagination: { pageSize: 10 },
    },
  })

  if (papers.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-16 text-slate-500">
        <FileText className="h-12 w-12 mb-3 opacity-30" />
        <p className="text-sm">No papers found</p>
      </div>
    )
  }

  return (
    <div className="space-y-4">
      {/* Search */}
      <div className="relative">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-500" />
        <Input
          placeholder="Search papers, authors, tags..."
          value={globalFilter}
          onChange={(e) => setGlobalFilter(e.target.value)}
          className="pl-9"
        />
      </div>

      {/* Table */}
      <div className="overflow-hidden rounded-lg border border-slate-800">
        <div className="overflow-x-auto">
          <table className="research-table w-full">
            <thead>
              {table.getHeaderGroups().map((headerGroup) => (
                <tr key={headerGroup.id} className="border-b border-slate-800 bg-slate-900">
                  {headerGroup.headers.map((header) => (
                    <th
                      key={header.id}
                      className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-slate-500"
                      style={{ width: header.getSize() !== 150 ? header.getSize() : undefined }}
                    >
                      {header.isPlaceholder ? null : (
                        <div
                          className={cn(
                            'flex items-center gap-1.5',
                            header.column.getCanSort() && 'cursor-pointer select-none hover:text-slate-300 transition-colors'
                          )}
                          onClick={header.column.getToggleSortingHandler()}
                        >
                          {flexRender(header.column.columnDef.header, header.getContext())}
                          {header.column.getCanSort() && (
                            <span className="text-slate-600">
                              {header.column.getIsSorted() === 'asc' ? (
                                <ChevronUp className="h-3 w-3 text-indigo-400" />
                              ) : header.column.getIsSorted() === 'desc' ? (
                                <ChevronDown className="h-3 w-3 text-indigo-400" />
                              ) : (
                                <ChevronsUpDown className="h-3 w-3" />
                              )}
                            </span>
                          )}
                        </div>
                      )}
                    </th>
                  ))}
                </tr>
              ))}
            </thead>
            <tbody>
              {table.getRowModel().rows.map((row, idx) => (
                <React.Fragment key={row.id}>
                  <tr
                    className={cn(
                      'border-b border-slate-800/50 transition-colors duration-100',
                      'hover:bg-slate-800/30 cursor-pointer',
                      idx % 2 === 0 ? 'bg-slate-900/30' : 'bg-slate-900/10',
                      row.getIsExpanded() && 'bg-slate-800/40'
                    )}
                    onClick={() => row.toggleExpanded()}
                  >
                    {row.getVisibleCells().map((cell) => (
                      <td key={cell.id} className="px-4 py-3 align-top">
                        {flexRender(cell.column.columnDef.cell, cell.getContext())}
                      </td>
                    ))}
                  </tr>
                  {row.getIsExpanded() && (
                    <tr>
                      <td colSpan={columns.length}>
                        <ExpandedRow paper={row.original} />
                      </td>
                    </tr>
                  )}
                </React.Fragment>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Pagination */}
      <div className="flex items-center justify-between text-sm">
        <span className="text-slate-500">
          {table.getFilteredRowModel().rows.length} papers
          {globalFilter && ` matching "${globalFilter}"`}
        </span>
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => table.previousPage()}
            disabled={!table.getCanPreviousPage()}
          >
            Previous
          </Button>
          <span className="text-slate-400 tabular-nums">
            {table.getState().pagination.pageIndex + 1} / {table.getPageCount()}
          </span>
          <Button
            variant="outline"
            size="sm"
            onClick={() => table.nextPage()}
            disabled={!table.getCanNextPage()}
          >
            Next
          </Button>
        </div>
      </div>
    </div>
  )
}
