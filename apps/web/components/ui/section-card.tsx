export function SectionCard({
  children,
  className = '',
  tabAttached = false,
  interactive = false,
  ...props
}: {
  children: React.ReactNode;
  className?: string;
  tabAttached?: boolean;
  interactive?: boolean;
} & React.HTMLAttributes<HTMLElement>) {
  return (
    <section
      {...props}
      className={`panel-solid ${interactive ? 'card-interactive' : 'glass-hover'} ${
        tabAttached ? 'rounded-[28px] rounded-t-[18px]' : 'rounded-[28px]'
      } ${tabAttached ? 'mt-0 p-5 sm:p-7' : 'mt-5 p-5 sm:p-7'} ${
        className
      }`}
    >
      {children}
    </section>
  );
}
