import * as React from "react";

import { cn } from "@/lib/utils";

/**
 * 原生 <select>，样式与 Input 保持一致。
 * 选项少、不需要搜索的场景下，原生控件的键盘操作和移动端体验都最好。
 */
function NativeSelect({ className, ...props }: React.ComponentProps<"select">) {
  return (
    <select
      data-slot="native-select"
      className={cn(
        "h-8 w-full min-w-0 rounded-lg border border-input bg-transparent px-2.5 text-sm outline-none transition-colors focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 disabled:opacity-50 dark:bg-input/30",
        className,
      )}
      {...props}
    />
  );
}

export { NativeSelect };
