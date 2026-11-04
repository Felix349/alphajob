import { NextResponse, type NextRequest } from "next/server";

// 必须与后端 settings.cookie_name 保持一致
const AUTH_COOKIE = "alphajob_token";
const AUTH_PAGES = ["/login", "/register"];

/**
 * 路由守卫（乐观检查）：只看 Cookie 是否存在，不校验 JWT 签名。
 * 真正的鉴权永远在后端完成；这里只是为了让未登录用户不必先看到空白页面再跳转。
 */
export function proxy(request: NextRequest) {
  const { pathname } = request.nextUrl;
  const hasToken = request.cookies.has(AUTH_COOKIE);
  const isAuthPage = AUTH_PAGES.some((p) => pathname.startsWith(p));

  if (!hasToken && !isAuthPage) {
    return NextResponse.redirect(new URL("/login", request.url));
  }
  if (hasToken && isAuthPage) {
    return NextResponse.redirect(new URL("/board", request.url));
  }
  return NextResponse.next();
}

export const config = {
  // 不拦截接口请求、静态资源和图片
  matcher: ["/((?!api|_next/static|_next/image|favicon.ico|.*\\.(?:png|jpg|svg|ico)$).*)"],
};
