"use client";

import { QueryClientProvider } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";

import { createWebQueryClient } from "@/lib/api/query-client";

export function Providers({ children }: { children: ReactNode }) {
  const [queryClient] = useState(() => createWebQueryClient());

  return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
}
