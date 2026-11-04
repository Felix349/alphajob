import { GeistMono } from "geist/font/mono";
import { GeistSans } from "geist/font/sans";
import type { Metadata } from "next";

import { Providers } from "./providers";
import "./globals.css";

// 字体文件来自 npm 包 geist，构建时打包进项目，不需要访问 Google Fonts（国内网络下经常失败）

export const metadata: Metadata = {
  title: "AlphaJob · 求职 Agent",
  description: "掌握你全部求职数据的求职 Agent",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="zh-CN" className={`${GeistSans.variable} ${GeistMono.variable} h-full antialiased`}>
      <body className="min-h-full flex flex-col">
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
