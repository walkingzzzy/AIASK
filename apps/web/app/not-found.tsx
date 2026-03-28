import Link from 'next/link';

export default function NotFound() {
  return (
    <div className="mx-auto mt-12 max-w-3xl px-4 font-sans">
      <div className="surface-card rounded-[28px] p-8 text-center md:p-10">
        <p className="m-0 text-xs uppercase tracking-[0.2em] text-text-muted">404 / 页面未找到</p>
        <div className="mb-4 mt-5 text-6xl font-semibold opacity-35">404</div>
        <h2 className="m-0 text-2xl font-bold">这个入口可能已经失效</h2>
        <p className="mx-auto mt-3 max-w-xl text-sm leading-6 text-text-secondary md:text-base">
          你访问的页面可能已被移除、链接地址有误，或者这是一个旧收藏夹入口。先回到常用页面，通常能更快恢复工作流。
        </p>

        <div className="mt-6 flex flex-wrap justify-center gap-3">
          <Link href="/" className="rounded-full bg-primary px-4 py-2 text-sm text-white no-underline">
            返回首页
          </Link>
          <Link href="/market" className="rounded-full border border-border px-4 py-2 text-sm text-text-secondary no-underline">
            查看行情
          </Link>
          <Link href="/stock" className="rounded-full border border-border px-4 py-2 text-sm text-text-secondary no-underline">
            个股分析
          </Link>
        </div>

        <div className="mt-8 grid gap-3 text-left md:grid-cols-2">
          {[
            { href: '/research', title: '研究分析', desc: '想继续看估值、基本面或研报时，从这里重新进入最顺手。' },
            { href: '/watchlist', title: '自选股', desc: '如果你原本想找某只股票，先回到自选列表通常比重新输链接更快。' },
            { href: '/portfolio', title: '组合管理', desc: '继续处理持仓、权重和绩效时，可直接从这里回到你的主流程。' },
            { href: '/chat', title: '智能助手', desc: '如果你不确定下一步去哪，可以先到助手页描述目标，让系统帮你跳回正确入口。' },
          ].map((item) => (
            <Link
              key={item.href}
              href={item.href}
              className="surface-card block rounded-2xl p-4 no-underline text-inherit transition hover:border-primary/20 hover:shadow-md"
            >
              <div className="text-sm font-semibold">{item.title}</div>
              <p className="mb-0 mt-2 text-xs leading-5 text-text-secondary">{item.desc}</p>
            </Link>
          ))}
        </div>
      </div>
    </div>
  );
}
