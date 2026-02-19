export function SectionCard({
  children,
  className = '',
  tabAttached = false,
}: {
  children: React.ReactNode;
  className?: string;
  tabAttached?: boolean;
}) {
  return (
    <section
      className={`border border-border p-3 ${
        tabAttached ? 'rounded-b-[8px]' : 'rounded-[8px] mt-3'
      } ${className}`}
    >
      {children}
    </section>
  );
}
