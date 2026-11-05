"use client";

import { useQueryClient } from "@tanstack/react-query";
import {
  BookOpen,
  Bot,
  CalendarDays,
  FileText,
  KanbanSquare,
  LogOut,
  MessagesSquare,
  type LucideIcon,
} from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { Suspense, useEffect } from "react";

import { Button } from "@/components/ui/button";
import { useCurrentUser } from "@/hooks/use-current-user";
import { authApi } from "@/lib/api/auth";
import { ApiError } from "@/lib/api/client";
import { cn } from "@/lib/utils";

type NavItem = { href: string; label: string; icon: LucideIcon };

const NAV: NavItem[] = [
  { href: "/board", label: "求职看板", icon: KanbanSquare },
  { href: "/calendar", label: "日历", icon: CalendarDays },
  { href: "/resume", label: "我的简历", icon: FileText },
  { href: "/interviews", label: "面试复盘", icon: MessagesSquare },
  { href: "/questions", label: "题库", icon: BookOpen },
  { href: "/agent", label: "求职 Agent", icon: Bot },
];

function CurrentNavLinks() {
  return <NavLinks pathname={usePathname()} />;
}

function NavLinks({ pathname }: { pathname: string }) {
  return (
    <nav className="flex flex-1 flex-col gap-1 px-3">
      {NAV.map(({ href, label, icon: Icon }) => {
        // 投递详情页属于“求职看板”
        const active =
          pathname.startsWith(href) || (href === "/board" && pathname.startsWith("/applications"));
        return (
          <Link
            key={href}
            href={href}
            className={cn(
              "flex items-center gap-3 rounded-md px-3 py-2 text-sm transition-colors",
              active
                ? "bg-primary text-primary-foreground"
                : "text-muted-foreground hover:bg-muted hover:text-foreground",
            )}
          >
            <Icon className="size-4" />
            {label}
          </Link>
        );
      })}
    </nav>
  );
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const queryClient = useQueryClient();
  const { data: user, error, isPending } = useCurrentUser();

  // Cookie 存在但已失效（过期、被篡改）：后端返回 401。
  // 必须先让后端清掉这个失效 Cookie，否则 proxy.ts 看到 Cookie 还在，会把 /login 又重定向回 /board。
  useEffect(() => {
    if (error instanceof ApiError && error.status === 401) {
      authApi
        .logout()
        .catch(() => {})
        .finally(() => {
          queryClient.clear();
          router.replace("/login");
        });
    }
  }, [error, router, queryClient]);

  async function handleLogout() {
    await authApi.logout();
    queryClient.clear();
    router.replace("/login");
    router.refresh();
  }

  return (
    <div className="flex min-h-screen flex-1">
      <aside className="flex w-56 shrink-0 flex-col border-r bg-muted/30">
        <div className="px-5 py-5">
          <Link href="/board" className="text-lg font-semibold tracking-tight">
            AlphaJob
          </Link>
        </div>
        {/* 读取当前 URL 的部分必须放在 Suspense 里：开启 cacheComponents 后，
            动态路由（如 /applications/[id]）的 URL 只有运行时才知道，不能阻塞静态外壳的预渲染 */}
        <Suspense fallback={<NavLinks pathname="" />}>
          <CurrentNavLinks />
        </Suspense>
        <div className="border-t p-3">
          <div className="truncate px-2 pb-2 text-sm" title={user?.email}>
            {isPending ? "加载中…" : (user?.display_name ?? user?.email)}
          </div>
          <Button variant="ghost" size="sm" className="w-full justify-start" onClick={handleLogout}>
            <LogOut className="size-4" />
            退出登录
          </Button>
        </div>
      </aside>
      <main className="flex-1 overflow-auto p-8">{children}</main>
    </div>
  );
}
