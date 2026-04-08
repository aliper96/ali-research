import * as React from 'react'
import { cn } from '@/lib/utils'

export interface InputProps
  extends React.InputHTMLAttributes<HTMLInputElement> {}

const Input = React.forwardRef<HTMLInputElement, InputProps>(
  ({ className, type, ...props }, ref) => {
    return (
      <input
        type={type}
        className={cn(
          'flex h-10 w-full rounded-xl border border-[#1d2d47] bg-[#0d1526]/60 px-3 py-2 text-sm text-slate-100 placeholder:text-slate-500',
          'transition-all duration-150',
          'focus:outline-none focus:ring-2 focus:ring-indigo-500/60 focus:border-indigo-500/50',
          'hover:border-[#2d3f5a]',
          'disabled:cursor-not-allowed disabled:opacity-40',
          className
        )}
        ref={ref}
        {...props}
      />
    )
  }
)
Input.displayName = 'Input'

export { Input }
