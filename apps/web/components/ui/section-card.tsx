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
      className={`glass glass-hover p-3 ${
        tabAttached ? 'rounded-b-[12px]' : 'rounded-[12px] mt-3'
      } ${className}`}
    >
      {children}
    </section>
  );
}
