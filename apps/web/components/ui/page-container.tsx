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
        'mx-auto px-3 py-4 font-sans sm:px-4 sm:py-7',
        narrow ? 'max-w-[980px]' : 'max-w-[1080px]',
        mobileBottomSafe ? 'pb-[calc(56px+env(safe-area-inset-bottom)+16px)] md:pb-7' : '',
        className,
      ].join(' ')}
    >
      {children}
    </main>
  );
}
