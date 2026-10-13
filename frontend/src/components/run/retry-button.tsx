import { useMutation, useQueryClient } from "@tanstack/react-query"
import { RotateCcw } from "lucide-react"
import { toast } from "sonner"

import { Spinner } from "@/components/common"
import { Button } from "@/components/ui/button"
import { api } from "@/lib/api"

export function RetryRunButton({ runId, size = "sm" }: { runId: string; size?: "sm" | "default" }) {
  const client = useQueryClient()
  const retry = useMutation({
    mutationFn: () => api(`/runs/${runId}/retry`, { method: "POST" }),
    onSuccess: () => {
      toast.success("Запуск снова в работе: продолжит с места ошибки")
      client.invalidateQueries({ queryKey: ["run", runId] })
      client.invalidateQueries({ queryKey: ["runs"] })
    },
    onError: (e) => toast.error((e as Error).message),
  })
  return (
    <Button
      size={size}
      variant="outline"
      onClick={(e) => {
        e.preventDefault()
        retry.mutate()
      }}
      disabled={retry.isPending}
    >
      {retry.isPending ? <Spinner /> : <RotateCcw />} Повторить
    </Button>
  )
}
