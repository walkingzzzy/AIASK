'use client';

import { useEffect } from 'react';
import * as Sentry from '@sentry/nextjs';
import Link from 'next/link';

type ErrorAction = { label: string; href?: string; onClick?: () => void; primary?: boolean };
type ErrorLevel = {
  title: string;
  description: string;
  steps: string[];
  actions: ErrorAction[];
};

function classify(error: Error): ErrorLevel {
  const msg = error.message || '';
  if (/fetch|network|ERR_/i.test(msg)) {
    return {
      title: '网络连接失败',
      description: '当前页面没能顺利连接到服务，通常是网络波动、接口暂时不可达，或本地代理状态异常导致。',
      steps: [
        '先点击“再次尝试”或直接刷新页面，确认是不是一次性波动。',
        '如果多个页面都失败，请检查本地网络、代理或后端服务是否正常。',
        '仍然失败时，可稍后重试，避免在异常状态下重复提交操作。',
      ],
      actions: [{ label: '检查登录状态', href: '/login' }],
    };
  }
  if (/401|未登录|登录已过期/i.test(msg)) {
    return {
      title: '登录已过期',
      description: '你的会话已经失效或权限凭证过期，需要重新登录后再继续当前操作。',
      steps: [
        '先回到登录页重新登录。',
        '登录成功后再回到刚才的页面，通常可以恢复。',
        '如果刚登录仍然出现同样提示，请检查账号权限或联系管理员。',
      ],
      actions: [{ label: '去登录', href: '/login', primary: true }],
    };
  }
  if (/403|权限|forbidden/i.test(msg)) {
    return {
      title: '没有访问权限',
      description: '当前账号没有权限访问这个页面或执行这个动作，继续刷新通常不会解决问题。',
      steps: [
        '先确认你是否使用了正确的账号。',
        '如果这是管理页或风控页，请联系管理员确认权限。',
        '可以先返回首页或切换到其他不受限页面继续工作。',
      ],
      actions: [{ label: '去首页', href: '/' }],
    };
  }
  if (/5\d{2}|服务/i.test(msg)) {
    return {
      title: '服务暂时不可用',
      description: '服务端刚刚返回了异常响应，这更像是后端暂时抖动，而不是你当前输入有问题。',
      steps: [
        '先重试一次，排除偶发性的服务波动。',
        '如果是提交类操作，请先确认没有重复下单或重复保存。',
        '连续失败时建议稍后重试，并把错误编号提供给维护人员。',
      ],
      actions: [{ label: '返回市场看板', href: '/market' }],
    };
  }
  return {
    title: '页面暂时无法继续',
    description: '刚刚发生了一个未预期的问题。你可以先尝试恢复页面，再决定是否切换到其他入口继续操作。',
    steps: [
      '先点击“再次尝试”，确认是否只是临时错误。',
      '如果你刚做过提交类操作，恢复前先确认结果是否已经生效。',
      '如问题持续出现，请记录下方错误信息并反馈给维护人员。',
    ],
    actions: [{ label: '去研究分析', href: '/research' }],
  };
}

export default function ErrorPage({ error, reset }: { error: Error; reset: () => void }) {
  useEffect(() => {
    Sentry.captureException(error);
  }, [error]);

  const level = classify(error);
  const digest = (error as Error & { digest?: string }).digest;
  const primaryButtonCls = 'rounded-full bg-primary px-4 py-2 text-sm text-white transition hover:opacity-90 cursor-pointer';
  const secondaryButtonCls = 'rounded-full border border-glass-border px-4 py-2 text-sm text-text-secondary no-underline transition hover:border-primary/40 hover:text-primary';
  const actionButtonCls = 'rounded-full border border-glass-border px-4 py-2 text-sm text-text-secondary transition hover:border-primary/40 hover:text-primary cursor-pointer';

  return (
    <div className="mx-auto mt-10 max-w-3xl px-4 font-sans">
      <div className="glass rounded-[28px] border border-glass-border p-6 md:p-8" role="alert" aria-live="assertive">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="max-w-2xl">
            <p className="m-0 text-xs uppercase tracking-[0.22em] text-text-muted">页面恢复中心</p>
            <h2 className="mt-3 text-2xl font-bold text-error md:text-3xl">{level.title}</h2>
            <p className="mt-3 text-sm leading-6 text-text-secondary md:text-base">{level.description}</p>
          </div>
          <span className="rounded-full border border-danger/25 bg-danger/10 px-3 py-1 text-xs text-danger">可恢复异常</span>
        </div>

        <div className="mt-6 grid gap-4 md:grid-cols-[1.15fr_0.85fr]">
          <section className="rounded-2xl border border-glass-border bg-white/5 p-4 text-left">
            <h3 className="m-0 text-sm font-semibold text-text-primary">建议先这样处理</h3>
            <ol className="mt-3 space-y-2 pl-5 text-sm leading-6 text-text-secondary">
              {level.steps.map((step) => (
                <li key={step}>{step}</li>
              ))}
            </ol>
          </section>

          <section className="rounded-2xl border border-glass-border bg-white/5 p-4 text-left">
            <h3 className="m-0 text-sm font-semibold text-text-primary">快速操作</h3>
            <div className="mt-3 flex flex-wrap gap-2">
              <button type="button" onClick={reset} className={primaryButtonCls}>
                再次尝试
              </button>
              <button type="button" onClick={() => window.location.reload()} className={actionButtonCls}>
                刷新页面
              </button>
              {level.actions.map((action) =>
                action.href ? (
                  <Link key={action.label} href={action.href} className={action.primary ? primaryButtonCls : secondaryButtonCls}>
                    {action.label}
                  </Link>
                ) : (
                  <button key={action.label} type="button" onClick={action.onClick} className={action.primary ? primaryButtonCls : actionButtonCls}>
                    {action.label}
                  </button>
                ),
              )}
              <Link href="/" className={secondaryButtonCls}>
                返回首页
              </Link>
            </div>
          </section>
        </div>

        <details className="mt-4 rounded-2xl border border-glass-border bg-black/10 p-4">
          <summary className="cursor-pointer list-none text-sm font-medium text-text-primary">查看技术信息</summary>
          <div className="mt-3 space-y-2 text-sm text-text-secondary">
            <p className="m-0 break-all">{error.message || '未提供额外错误信息'}</p>
            {digest ? <p className="m-0 text-xs text-text-muted">错误编号：{digest}</p> : null}
          </div>
        </details>
      </div>
    </div>
  );
}
