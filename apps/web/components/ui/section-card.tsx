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
      className={`surface-card ${
        tabAttached ? 'rounded-b-[22px] rounded-t-none' : 'rounded-[22px]'
      } ${tabAttached ? 'mt-0 p-4' : 'mt-4 p-4 sm:p-5'} ${
        className
      }`}
    >
      {children}
    </section>
  );
}
