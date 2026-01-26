/**
 * 输入区域组件 - 匹配 AetherTrade 设计图
 */

import React, { useState, KeyboardEvent, useRef } from 'react';

interface InputAreaProps {
    onSend: (content: string) => void;
    disabled?: boolean;
}

const InputArea: React.FC<InputAreaProps> = ({ onSend, disabled = false }) => {
    const [input, setInput] = useState('');
    const [isRecording, setIsRecording] = useState(false);
    const fileInputRef = useRef<HTMLInputElement>(null);
    const recognitionRef = useRef<any>(null);

    const handleSend = () => {
        if (input.trim() && !disabled) {
            onSend(input.trim());
            setInput('');
        }
    };

    const handleKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            handleSend();
        }
    };

    const handleAttach = () => {
        fileInputRef.current?.click();
    };

    const readFileAsText = (file: File): Promise<string | null> => {
        const MAX_SIZE = 60 * 1024;
        const allowed = ['txt', 'md', 'csv', 'json', 'log'];
        const ext = file.name.split('.').pop()?.toLowerCase() || '';
        const isText = file.type.startsWith('text/') || allowed.includes(ext);

        if (!isText || file.size > MAX_SIZE) {
            return Promise.resolve(null);
        }

        return new Promise(resolve => {
            const reader = new FileReader();
            reader.onload = () => resolve(typeof reader.result === 'string' ? reader.result : null);
            reader.onerror = () => resolve(null);
            reader.readAsText(file);
        });
    };

    const handleFilesSelected = async (event: React.ChangeEvent<HTMLInputElement>) => {
        const files = Array.from(event.target.files || []);
        if (files.length === 0) return;

        const parts: string[] = [];
        for (const file of files) {
            const content = await readFileAsText(file);
            if (content) {
                parts.push(`[附件: ${file.name}]\n${content}\n[/附件]`);
            } else {
                parts.push(`[附件: ${file.name}]`);
            }
        }

        setInput(prev => (prev ? `${prev}\n\n${parts.join('\n')}` : parts.join('\n')));
        event.target.value = '';
    };

    const toggleRecording = () => {
        const SpeechRecognitionCtor =
            (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
        if (!SpeechRecognitionCtor) {
            setInput(prev => (prev ? `${prev} [语音输入不可用]` : '[语音输入不可用]'));
            return;
        }

        if (isRecording && recognitionRef.current) {
            recognitionRef.current.stop();
            return;
        }

        const recognition = new SpeechRecognitionCtor();
        recognition.lang = 'zh-CN';
        recognition.interimResults = false;
        recognition.maxAlternatives = 1;

        recognition.onresult = (event: any) => {
            const transcript = event.results?.[0]?.[0]?.transcript;
            if (transcript) {
                setInput(prev => (prev ? `${prev} ${transcript}` : transcript));
            }
        };

        recognition.onend = () => {
            setIsRecording(false);
        };

        recognition.onerror = () => {
            setIsRecording(false);
        };

        recognition.start();
        recognitionRef.current = recognition;
        setIsRecording(true);
    };

    return (
        <div className="input-area-enhanced">
            <div className="input-container">
                {/* 附件按钮 */}
                <button className="input-icon-btn" title="添加附件" onClick={handleAttach} disabled={disabled}>
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                        <path d="M21.44 11.05l-9.19 9.19a6 6 0 01-8.49-8.49l9.19-9.19a4 4 0 015.66 5.66l-9.2 9.19a2 2 0 01-2.83-2.83l8.49-8.48" />
                    </svg>
                </button>

                {/* 输入框 */}
                <input
                    type="text"
                    className="input-field"
                    value={input}
                    onChange={e => setInput(e.target.value)}
                    onKeyDown={handleKeyDown}
                    placeholder="Ask AetherTrade AI..."
                    disabled={disabled}
                />

                {/* 语音按钮 */}
                <button
                    className="input-icon-btn"
                    title={isRecording ? '停止语音输入' : '语音输入'}
                    onClick={toggleRecording}
                    disabled={disabled}
                >
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                        <path d="M12 1a3 3 0 00-3 3v8a3 3 0 006 0V4a3 3 0 00-3-3z" />
                        <path d="M19 10v2a7 7 0 01-14 0v-2" />
                        <line x1="12" y1="19" x2="12" y2="23" />
                        <line x1="8" y1="23" x2="16" y2="23" />
                    </svg>
                </button>

                {/* 发送按钮 */}
                <button
                    className="input-send-btn"
                    onClick={handleSend}
                    disabled={disabled || !input.trim()}
                    title="发送"
                >
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                        <line x1="22" y1="2" x2="11" y2="13" />
                        <polygon points="22 2 15 22 11 13 2 9 22 2" />
                    </svg>
                </button>
            </div>
            <input
                ref={fileInputRef}
                type="file"
                multiple
                style={{ display: 'none' }}
                onChange={handleFilesSelected}
            />
        </div>
    );
};

export default InputArea;
