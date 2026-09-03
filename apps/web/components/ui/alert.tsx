import type { HTMLAttributes } from "react";
import { cn } from "../../lib/utils";
export function Alert({ className, variant = "default", ...props }: HTMLAttributes<HTMLDivElement> & { variant?: "default" | "destructive" | "warning" }) { return <div role="alert" className={cn("ui-alert", `ui-alert-${variant}`, className)} {...props} />; }
