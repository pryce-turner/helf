import * as React from "react"
import { Slot } from "@radix-ui/react-slot"

import { cn } from "@/lib/utils"

// Button variants mapping to CSS classes from the design system
const variantStyles = {
  default: "btn-primary",
  primary: "btn-primary",
  secondary: "btn-secondary",
  destructive: "btn-danger",
  outline: "btn-secondary",
  ghost: "btn-ghost",
  link: "btn-link",
} as const

const sizeStyles = {
  default: "",
  sm: "text-[13px] py-2 px-3",
  lg: "text-base py-3 px-6",
  icon: "p-2 w-10 h-10",
} as const

type ButtonVariant = keyof typeof variantStyles
type ButtonSize = keyof typeof sizeStyles

// Helper function for components that need to get button variant classes
export function buttonVariants({ variant = "default", size = "default" }: { variant?: ButtonVariant; size?: ButtonSize } = {}) {
  return cn(
    "inline-flex items-center justify-center gap-2 whitespace-nowrap disabled:pointer-events-none disabled:opacity-50",
    variantStyles[variant],
    sizeStyles[size]
  )
}

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  asChild?: boolean
  variant?: ButtonVariant
  size?: ButtonSize
}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant = "default", size = "default", asChild = false, ...props }, ref) => {
    const Comp = asChild ? Slot : "button"
    return (
      <Comp
        className={cn(
          "inline-flex items-center justify-center gap-2 whitespace-nowrap disabled:pointer-events-none disabled:opacity-50 [&_svg]:pointer-events-none [&_svg]:size-4 [&_svg]:shrink-0",
          variantStyles[variant],
          sizeStyles[size],
          className
        )}
        ref={ref}
        {...props}
      />
    )
  }
)
Button.displayName = "Button"

export { Button }
