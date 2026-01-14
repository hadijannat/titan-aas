import type { LucideIcon } from 'lucide-react'
import type { ReactNode } from 'react'

interface StatCardProps {
  icon: LucideIcon
  label: string
  value: ReactNode
  subtext?: ReactNode
  iconClassName?: string
}

export function StatCard({ icon: Icon, label, value, subtext, iconClassName }: StatCardProps) {
  const iconClasses = iconClassName ?? 'text-titan-500'

  return (
    <div className="bg-slate-800 rounded-lg p-4 border border-slate-700">
      <div className="flex items-center gap-3">
        <Icon className={`w-8 h-8 ${iconClasses}`} />
        <div>
          <p className="text-slate-400 text-sm">{label}</p>
          <p className="text-white font-semibold text-lg">{value}</p>
          {subtext && <p className="text-slate-500 text-xs">{subtext}</p>}
        </div>
      </div>
    </div>
  )
}
