'use client';

import { useState } from 'react';

/** T-040: MaskedValue — shows **** by default, tap to reveal for 3s */
export function MaskedValue({
    value,
    format,
    className = '',
}: {
    value: string | number;
    format?: (v: string | number) => string;
    className?: string;
}) {
    const [visible, setVisible] = useState(false);

    const display = format ? format(value) : String(value);

    const toggleVisible = () => {
        setVisible(true);
        setTimeout(() => setVisible(false), 3000);
    };

    return (
        <span
            onClick={toggleVisible}
            className={`cursor-pointer select-none ${className}`}
            title={visible ? '点击隐藏' : '点击显示'}
        >
            {visible ? display : '****'}
        </span>
    );
}
