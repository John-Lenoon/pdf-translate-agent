import type { ReactNode } from "react";
import "./globals.css";
import "./responsive.css";
import "./shadcn.css";
import "./redesign.css";

export default function RootLayout({ children }: { children: ReactNode }) {
  return <html lang="zh-CN"><body>{children}</body></html>;
}
