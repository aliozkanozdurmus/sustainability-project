// Bu temel UI bileseni, button davranisini tasarim sistemiyle hizalar.

import * as React from "react"
import { cva, type VariantProps } from "class-variance-authority"
import { Slot } from "radix-ui"

import { cn } from "@/lib/utils"

const buttonVariants = cva(
  "inline-flex shrink-0 items-center justify-center gap-2 whitespace-nowrap rounded-full text-[13px] font-medium tracking-[-0.01em] transition-all duration-150 outline-none focus-visible:ring-[3px] focus-visible:ring-ring disabled:pointer-events-none disabled:opacity-55 [&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg:not([class*='size-'])]:size-4",
  {
    variants: {
      variant: {
        default: "bg-primary text-primary-foreground shadow-[inset_0_-1px_0_rgba(255,255,255,0.08)] hover:-translate-y-px hover:bg-primary/95",
        destructive:
          "bg-destructive text-destructive-foreground hover:-translate-y-px hover:bg-destructive/92",
        outline:
          "border border-[color:var(--border)] bg-white/70 text-foreground shadow-[0_10px_24px_rgba(42,39,33,0.06)] hover:-translate-y-px hover:bg-white",
        secondary:
          "bg-secondary text-secondary-foreground hover:-translate-y-px hover:bg-[#f2e6c8]",
        ghost:
          "bg-transparent text-[color:var(--foreground-soft)] hover:bg-white/50 hover:text-foreground",
        soft:
          "bg-[color:rgba(228,199,100,0.28)] text-foreground hover:bg-[color:rgba(228,199,100,0.4)]",
        link: "text-primary underline-offset-4 hover:underline",
      },
      size: {
        default: "h-10 px-4 py-2 has-[>svg]:px-3.5",
        xs: "h-7 gap-1 rounded-full px-2.5 text-[11px] has-[>svg]:px-2 [&_svg:not([class*='size-'])]:size-3",
        sm: "h-8 gap-1.5 rounded-full px-3.5 text-[12px] has-[>svg]:px-3",
        lg: "h-11 rounded-full px-6 text-[14px] has-[>svg]:px-4.5",
        icon: "size-10",
        "icon-xs": "size-7 rounded-full [&_svg:not([class*='size-'])]:size-3",
        "icon-sm": "size-8 rounded-full",
        "icon-lg": "size-11 rounded-full",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  }
)

function Button({
  className,
  variant = "default",
  size = "default",
  asChild = false,
  ...props
}: React.ComponentProps<"button"> &
  VariantProps<typeof buttonVariants> & {
    asChild?: boolean
  }) {
  const Comp = asChild ? Slot.Root : "button"

  return (
    <Comp
      data-slot="button"
      data-variant={variant}
      data-size={size}
      className={cn(buttonVariants({ variant, size, className }))}
      {...props}
    />
  )
}

export { Button, buttonVariants }
