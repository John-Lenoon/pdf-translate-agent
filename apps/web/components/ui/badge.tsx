import type { HTMLAttributes } from "react";
import { cn } from "../../lib/utils";
export function Badge({ className, variant = "secondary", ...props }: HTMLAttributes<HTMLSpanElement> & { variant?: "secondary" | "outline" | "destructive" | "warning" }) {
  return <span className={cn("ui-badge", `ui-badge-${variant}`, className)} {...props} />;
}
