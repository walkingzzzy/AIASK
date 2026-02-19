'use client';

export default function GlobalError({ error, reset }: { error: Error; reset: () => void }) {
  return (
    <div className="max-w-[600px] mx-auto mt-20 text-center font-sans">
      <h2 className="text-xl font-bold text-error">出错了</h2>
      <p className="mt-2 text-text-secondary">{error.message}</p>
      <button onClick={reset} className="mt-4 px-4 py-2 bg-primary text-white rounded cursor-pointer">
        重试
      </button>
    </div>
  );
}
