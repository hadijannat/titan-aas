interface ErrorStateProps {
  message: string
}

export function ErrorState({ message }: ErrorStateProps) {
  return (
    <div className="bg-red-500/10 border border-red-500/30 rounded-lg p-4">
      <p className="text-red-400">{message}</p>
    </div>
  )
}
