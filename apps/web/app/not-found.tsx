import Link from 'next/link';

export default function NotFound() {
  return (
    <div className="max-w-[600px] mx-auto mt-20 text-center font-sans">
      <h2 className="text-xl font-bold">404 - 页面不存在</h2>
      <Link href="/" className="mt-4 inline-block text-primary">
        返回首页
      </Link>
    </div>
  );
}
