import type { HTMLAttributes } from "react";
export function Empty({ className, ...props }: HTMLAttributes<HTMLDivElement>) { return <div className={`ui-empty${className ? ` ${className}` : ""}`} {...props} />; }
