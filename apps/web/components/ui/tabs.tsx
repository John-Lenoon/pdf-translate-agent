import type { ButtonHTMLAttributes, HTMLAttributes } from "react";
import { cn } from "../../lib/utils";
export function TabsList({ className, ...props }: HTMLAttributes<HTMLDivElement>) { return <div className={cn("ui-tabs-list", className)} {...props} />; }
export function TabsTrigger({ className, active, ...props }: ButtonHTMLAttributes<HTMLButtonElement> & { active?: boolean }) { return <button type="button" className={cn("ui-tab", active && "ui-tab-active", className)} {...props} />; }
