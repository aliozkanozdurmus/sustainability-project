"use client";

// Bu bilesen, route loading arayuz parcasini kurar.

import { ShimmerBlock, SurfaceCard } from "@/components/workbench-ui";

export function RouteLoadingFrame() {
  return (
    <div className="min-h-screen bg-canvas px-3 py-4 md:px-5 md:py-6">
      <div className="mx-auto max-w-[1540px] workbench-shell p-3 md:p-4">
        <div className="grid gap-3 xl:grid-cols-[232px_minmax(0,1fr)]">
          <div className="rail-surface hidden min-h-[calc(100vh-4rem)] p-4 xl:block">
            <ShimmerBlock className="h-14 rounded-[1.3rem]" />
            <div className="mt-8 space-y-3">
              <ShimmerBlock className="h-10 rounded-[1rem]" />
              <ShimmerBlock className="h-10 rounded-[1rem]" />
              <ShimmerBlock className="h-10 rounded-[1rem]" />
              <ShimmerBlock className="h-10 rounded-[1rem]" />
            </div>
            <ShimmerBlock className="mt-8 h-32 rounded-[1.8rem]" />
          </div>

          <div className="content-surface min-h-[calc(100vh-4rem)] p-3 md:p-4">
            <div className="flex items-center gap-3">
              <ShimmerBlock className="h-11 flex-1 rounded-full" />
              <ShimmerBlock className="size-11 rounded-full" />
              <ShimmerBlock className="size-11 rounded-full" />
              <ShimmerBlock className="hidden h-11 w-48 rounded-full md:block" />
            </div>

            <div className="mt-4 rounded-[1.9rem] border border-[rgba(23,22,19,0.06)] bg-white/78 px-4 py-4 shadow-[0_14px_36px_rgba(41,38,31,0.05)] md:px-5">
              <ShimmerBlock className="h-4 w-36" />
              <ShimmerBlock className="mt-4 h-10 w-72" />
              <ShimmerBlock className="mt-3 h-4 w-full" />
            </div>

            <div className="mt-4 space-y-4">
              <div className="grid dense-grid xl:grid-cols-[1.2fr_0.8fr]">
                <SurfaceCard className="px-5 py-5">
                  <ShimmerBlock className="h-4 w-28" />
                  <ShimmerBlock className="mt-4 h-12 w-80" />
                  <ShimmerBlock className="mt-3 h-4 w-full" />
                  <div className="mt-5 grid gap-3 md:grid-cols-3">
                    <ShimmerBlock className="h-24" />
                    <ShimmerBlock className="h-24" />
                    <ShimmerBlock className="h-24" />
                  </div>
                </SurfaceCard>
                <SurfaceCard className="px-5 py-5">
                  <ShimmerBlock className="h-4 w-24" />
                  <div className="mt-4 grid gap-3 md:grid-cols-3 xl:grid-cols-1">
                    <ShimmerBlock className="h-20" />
                    <ShimmerBlock className="h-20" />
                    <ShimmerBlock className="h-20" />
                  </div>
                </SurfaceCard>
              </div>

              <div className="grid dense-grid md:grid-cols-2 xl:grid-cols-4">
                <ShimmerBlock className="h-28" />
                <ShimmerBlock className="h-28" />
                <ShimmerBlock className="h-28" />
                <ShimmerBlock className="h-28" />
              </div>

              <div className="grid dense-grid xl:grid-cols-[1.05fr_0.95fr_0.8fr]">
                <ShimmerBlock className="h-[22rem]" />
                <ShimmerBlock className="h-[22rem]" />
                <ShimmerBlock className="h-[22rem]" />
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
