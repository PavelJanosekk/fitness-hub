/** Minimal Markdown for coach replies (bold, headings, bullet/numbered lists, rules) as React elements, no HTML. */
function inline(text: string) {
  return text.split(/(\*\*[^*]+\*\*)/g).map((part, i) =>
    part.startsWith("**") && part.endsWith("**") ? <strong key={i}>{part.slice(2, -2)}</strong> : part,
  );
}

export function Markdown({ text }: { text: string }) {
  const blocks: React.ReactNode[] = [];
  let list: { ordered: boolean; items: string[] } | null = null;
  const flush = () => {
    if (!list) return;
    const Tag = list.ordered ? "ol" : "ul";
    blocks.push(
      <Tag key={blocks.length} className={`my-1 space-y-0.5 pl-5 ${list.ordered ? "list-decimal" : "list-disc"}`}>
        {list.items.map((item, i) => (
          <li key={i}>{inline(item)}</li>
        ))}
      </Tag>,
    );
    list = null;
  };
  for (const raw of text.split("\n")) {
    const line = raw.trimEnd();
    const bullet = line.match(/^\s*[-*•]\s+(.*)/);
    const numbered = line.match(/^\s*\d+[.)]\s+(.*)/);
    if (bullet || numbered) {
      const ordered = !!numbered;
      if (list && list.ordered !== ordered) flush();
      list ??= { ordered, items: [] };
      list.items.push((bullet ?? numbered)![1]);
      continue;
    }
    flush();
    if (!line.trim()) continue;
    if (/^-{3,}$/.test(line.trim())) blocks.push(<hr key={blocks.length} className="my-2 border-zinc-700" />);
    else if (line.startsWith("#")) blocks.push(<p key={blocks.length} className="mt-2 font-semibold">{inline(line.replace(/^#+\s*/, ""))}</p>);
    else blocks.push(<p key={blocks.length} className="my-1">{inline(line)}</p>);
  }
  flush();
  return <div className="text-[15px] leading-relaxed">{blocks}</div>;
}
