"use client";

import { ShimmerBlock, SurfaceCard } from "@/components/workbench-ui";

export function RouteLoadingFrame() {
  return (
    <div className="min-h-screen bg-canvas px-4 py-6 md:px-6">
      <div className="mx-auto max-w-[1480px] workbench-shell px-4 py-4 md:px-5 md:py-5">
        <div className="flex flex-col gap-4">
          <SurfaceCard className="px-4 py-4">
            <div className="flex items-center justify-between gap-3">
              <ShimmerBlock className="h-10 w-64" />
              <div className="flex gap-2">
                <ShimmerBlock className="h-10 w-24 rounded-full" />
                <ShimmerBlock className="h-10 w-10 rounded-full" />
              </div>
            </div>
          </SurfaceCard>
          <div className="grid dense-grid xl:grid-cols-[1.25fr_0.75fr]">
            <SurfaceCard className="px-5 py-5">
              <ShimmerBlock className="h-4 w-28" />
              <ShimmerBlock className="mt-3 h-10 w-72" />
              <ShimmerBlock className="mt-2 h-4 w-full" />
              <ShimmerBlock className="mt-1 h-4 w-3/4" />
              <div className="mt-5 grid gap-3 md:grid-cols-3">
                <ShimmerBlock className="h-24" />
                <ShimmerBlock className="h-24" />
                <ShimmerBlock className="h-24" />
              </div>
            </SurfaceCard>
            <SurfaceCard className="px-5 py-5">
              <ShimmerBlock className="h-4 w-24" />
              <div className="mt-4 space-y-3">
                <ShimmerBlock className="h-16" />
                <ShimmerBlock className="h-16" />
                <ShimmerBlock className="h-16" />
              </div>
            </SurfaceCard>
          </div>
          <div className="grid dense-grid lg:grid-cols-3">
            <SurfaceCard className="px-5 py-5">
              <ShimmerBlock className="h-44" />
            </SurfaceCard>
            <SurfaceCard className="px-5 py-5 lg:col-span-2">
              <ShimmerBlock className="h-44" />
            </SurfaceCard>
          </div>
        </div>
      </div>
    </div>
  );
}
