import Link from 'next/link';

export default function NotFound() {
  return (
    <div className="max-w-[480px] mx-auto mt-20 text-center font-sans px-4">
      <div className="glass rounded-xl p-8">
        <div className="text-5xl mb-4 opacity-40">404</div>
        <h2 className="text-lg font-bold mt-0">页面不存在</h2>
        <p className="text-text-secondary text-sm mt-2">你访问的页面可能已被移除或地址有误</p>
        <div className="flex gap-3 justify-center mt-6">
          <Link href="/" className="px-4 py-2 bg-primary text-white rounded no-underline text-sm">
            返回首页
          </Link>
          <Link href="/market" className="px-4 py-2 border border-border rounded no-underline text-text-secondary text-sm">
            查看行情
          </Link>
          <Link href="/stock" className="px-4 py-2 border border-border rounded no-underline text-text-secondary text-sm">
            个股分析
          </Link>
        </div>
      </div>
    </div>
  );
}
