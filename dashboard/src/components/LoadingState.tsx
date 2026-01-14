interface LoadingStateProps {
  heightClassName?: string
}

export function LoadingState({ heightClassName = 'h-64' }: LoadingStateProps) {
  return (
    <div className={`flex items-center justify-center ${heightClassName}`}>
      <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-titan-500"></div>
    </div>
  )
}
