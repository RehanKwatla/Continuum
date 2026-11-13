import * as React from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { AuthProvider } from "@/contexts/AuthContext";
import { ThemeProvider } from "@/components/ui/theme-provider";
import { ToastProvider } from "@/components/ui/toast";
import { ApiClientError } from "@/services/api";

/**
 * One QueryClient for the whole app. 4xx responses are not retried — they are
 * deterministic and retrying only delays the error state.
 */
export function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: 15_000,
        refetchOnWindowFocus: false,
        retry: (failureCount, error) => {
          if (error instanceof ApiClientError && error.status && error.status < 500) return false;
          return failureCount < 2;
        },
      },
      mutations: { retry: false },
    },
  });
}

export function AppProviders({ children }: { children: React.ReactNode }) {
  const [queryClient] = React.useState(createQueryClient);
  return (
    <QueryClientProvider client={queryClient}>
      <ThemeProvider defaultTheme="dark">
        <ToastProvider>
          <AuthProvider>{children}</AuthProvider>
        </ToastProvider>
      </ThemeProvider>
    </QueryClientProvider>
  );
}
