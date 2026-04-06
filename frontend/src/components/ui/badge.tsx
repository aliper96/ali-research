import * as React from 'react'
import { cva, type VariantProps } from 'class-variance-authority'
import { cn } from '@/lib/utils'

const badgeVariants = cva(
  'inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium transition-colors',
  {
    variants: {
      variant: {
        default:
          'bg-indigo-900/50 text-indigo-300 border border-indigo-800/50',
        secondary:
          'bg-slate-800 text-slate-300 border border-slate-700',
        success:
          'bg-green-900/50 text-green-300 border border-green-800/50',
        warning:
          'bg-yellow-900/50 text-yellow-300 border border-yellow-800/50',
        destructive:
          'bg-red-900/50 text-red-300 border border-red-800/50',
        outline:
          'border border-slate-700 text-slate-400',
        easy:
          'bg-green-900/50 text-green-300 border border-green-800/50',
        medium:
          'bg-yellow-900/50 text-yellow-300 border border-yellow-800/50',
        hard:
          'bg-red-900/50 text-red-300 border border-red-800/50',
      },
    },
    defaultVariants: {
      variant: 'default',
    },
  }
)

export interface BadgeProps
  extends React.HTMLAttributes<HTMLDivElement>,
    VariantProps<typeof badgeVariants> {}

function Badge({ className, variant, ...props }: BadgeProps) {
  return (
    <div className={cn(badgeVariants({ variant }), className)} {...props} />
  )
}

export { Badge, badgeVariants }
