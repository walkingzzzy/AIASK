export function PageContainer({
  children,
  className = '',
  narrow = false,
}: {
  children: React.ReactNode;
  className?: string;
  narrow?: boolean;
}) {
  return (
    <main className={`mx-auto py-4 sm:py-7 px-3 sm:px-4 font-sans ${narrow ? 'max-w-[980px]' : 'max-w-[1080px]'} ${className}`}>
      {children}
    </main>
  );
}
