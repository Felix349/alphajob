export function ComingSoon({
  title,
  description,
  milestone,
}: {
  title: string;
  description: string;
  milestone: string;
}) {
  return (
    <div className="mx-auto max-w-3xl">
      <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
      <p className="mt-2 text-muted-foreground">{description}</p>
      <div className="mt-8 rounded-lg border border-dashed p-10 text-center text-sm text-muted-foreground">
        这个功能计划在 <span className="font-medium text-foreground">{milestone}</span> 实现
      </div>
    </div>
  );
}
