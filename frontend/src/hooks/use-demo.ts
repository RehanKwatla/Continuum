import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { getPublicDemoStatus, resetPublicDemo } from "@/services/demo";

export function usePublicDemo() {
  return useQuery({
    queryKey: ["public-demo"],
    queryFn: getPublicDemoStatus,
    staleTime: 60_000,
  });
}

export function useResetPublicDemo() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: resetPublicDemo,
    onSuccess: () => {
      queryClient.invalidateQueries();
    },
  });
}

