import type { ButtonHTMLAttributes } from "react";
import { cn } from "../../lib/utils";

export function Button({ className, variant = "default", size = "default", ...props }: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "default" | "outline" | "destructive" | "ghost"; size?: "default" | "sm" }) {
  return <button className={cn("ui-button", `ui-button-${variant}`, size === "sm" && "ui-button-sm", className)} {...props} />;
}
