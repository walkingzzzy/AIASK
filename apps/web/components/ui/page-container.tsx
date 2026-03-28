export function PageContainer({
  children,
  className = '',
  narrow = false,
  mobileBottomSafe = true,
}: {
  children: React.ReactNode;
  className?: string;
  narrow?: boolean;
  mobileBottomSafe?: boolean;
}) {
  return (
    <main
      className={[
        'mx-auto w-full px-0 py-0 font-sans sm:px-1 sm:py-1 lg:px-2',
        narrow ? 'max-w-[1040px]' : 'max-w-[1480px]',
        mobileBottomSafe ? 'pb-[calc(56px+env(safe-area-inset-bottom)+24px)] md:pb-6' : '',
        className,
      ].join(' ')}
    >
      {children}
    </main>
  );
}
