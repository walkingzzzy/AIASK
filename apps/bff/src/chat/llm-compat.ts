type ProbeEndpointResult = {
  ok: boolean;
  error?: string;
};

type ProbeModelsResult = ProbeEndpointResult & {
  models: string[];
};

type ProbeChatResult = ProbeEndpointResult & {
  probeModel?: string;
  contentPreview?: string;
};

export type LlmCompatibilityReport = {
  modelsEndpoint: ProbeModelsResult;
  chatCompletions: ProbeChatResult;
};

export type LlmCompatibilityProbeResult = {
  success: boolean;
  normalizedBaseUrl: string;
  models: string[];
  compatibility: LlmCompatibilityReport;
  triedBaseUrls: string[];
  error?: string;
};

const REQUEST_TIMEOUT_MS = 10_000;

function uniqueStrings(values: string[]) {
  return values.filter((value, index) => value.length > 0 && values.indexOf(value) === index);
}

function parseErrorMessage(error: unknown) {
  return error instanceof Error ? error.message : String(error);
}

function readPreview(text: string) {
  return text.replace(/\s+/g, ' ').trim().slice(0, 120);
}

async function readJsonBody(response: Response): Promise<Record<string, unknown> | null> {
  const text = await response.text();
  if (!text.trim()) {
    throw new Error('响应体为空');
  }
  try {
    return JSON.parse(text) as Record<string, unknown>;
  } catch {
    throw new Error(`响应不是 JSON：${readPreview(text)}`);
  }
}

async function probeModelsEndpoint(baseUrl: string, apiKey: string): Promise<ProbeModelsResult> {
  const url = `${baseUrl}/models`;
  try {
    const response = await fetch(url, {
      headers: { Authorization: `Bearer ${apiKey}` },
      signal: AbortSignal.timeout(REQUEST_TIMEOUT_MS),
    });
    if (!response.ok) {
      return { ok: false, error: `models 接口返回 ${response.status}`, models: [] };
    }

    const payload = await readJsonBody(response);
    const rows = Array.isArray(payload?.data) ? payload.data : [];
    const models = rows
      .map((row) => {
        if (!row || typeof row !== 'object') return '';
        return String((row as Record<string, unknown>).id ?? '').trim();
      })
      .filter(Boolean)
      .sort((left, right) => left.localeCompare(right));

    if (!models.length) {
      return { ok: false, error: 'models 接口未返回可用模型列表', models: [] };
    }

    return { ok: true, models };
  } catch (error) {
    return {
      ok: false,
      error: parseErrorMessage(error),
      models: [],
    };
  }
}

function extractAssistantContent(payload: Record<string, unknown> | null): string {
  const choices = Array.isArray(payload?.choices) ? payload.choices : [];
  const parts = choices.flatMap((choice) => {
    if (!choice || typeof choice !== 'object') return [];
    const message = (choice as Record<string, unknown>).message;
    if (!message || typeof message !== 'object') return [];
    const content = String((message as Record<string, unknown>).content ?? '').trim();
    return content ? [content] : [];
  });
  return parts.join('\n').trim();
}

async function probeChatEndpoint(baseUrl: string, apiKey: string, model: string): Promise<ProbeChatResult> {
  const url = `${baseUrl}/chat/completions`;
  try {
    const response = await fetch(url, {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${apiKey}`,
        'content-type': 'application/json',
      },
      body: JSON.stringify({
        model,
        stream: false,
        temperature: 0,
        max_tokens: 8,
        messages: [{ role: 'user', content: '请只回复“ok”。' }],
      }),
      signal: AbortSignal.timeout(REQUEST_TIMEOUT_MS),
    });
    if (!response.ok) {
      return { ok: false, error: `chat/completions 接口返回 ${response.status}`, probeModel: model };
    }

    const payload = await readJsonBody(response);
    const content = extractAssistantContent(payload);
    if (!content) {
      return {
        ok: false,
        error: 'chat/completions 返回空正文',
        probeModel: model,
      };
    }

    return {
      ok: true,
      probeModel: model,
      contentPreview: content.slice(0, 80),
    };
  } catch (error) {
    return {
      ok: false,
      error: parseErrorMessage(error),
      probeModel: model,
    };
  }
}

export function buildBaseUrlCandidates(baseUrl: string): string[] {
  const trimmed = String(baseUrl ?? '').trim();
  const withoutTrailingSlash = trimmed.replace(/\/+$/, '');
  const withV1 = withoutTrailingSlash.endsWith('/v1') ? withoutTrailingSlash : `${withoutTrailingSlash}/v1`;
  return uniqueStrings([trimmed, withoutTrailingSlash, withV1]);
}

export async function probeCompatibleBaseUrl(input: {
  baseUrl: string;
  apiKey: string;
  model?: string | null;
}): Promise<LlmCompatibilityProbeResult> {
  const candidates = buildBaseUrlCandidates(input.baseUrl);
  if (!candidates.length) {
    return {
      success: false,
      normalizedBaseUrl: '',
      models: [],
      compatibility: {
        modelsEndpoint: { ok: false, error: 'Base URL 不能为空', models: [] },
        chatCompletions: { ok: false, error: 'Base URL 不能为空' },
      },
      triedBaseUrls: [],
      error: 'Base URL 不能为空',
    };
  }

  let bestFailure: LlmCompatibilityProbeResult | null = null;

  for (const candidate of candidates) {
    const modelsResult = await probeModelsEndpoint(candidate, input.apiKey);
    const probeModel = (input.model ?? '').trim() || modelsResult.models[0] || '';
    const chatResult = probeModel
      ? await probeChatEndpoint(candidate, input.apiKey, probeModel)
      : { ok: false, error: '未找到可用于 chat/completions 探测的模型' };

    const report: LlmCompatibilityProbeResult = {
      success: modelsResult.ok && chatResult.ok,
      normalizedBaseUrl: candidate,
      models: modelsResult.models,
      compatibility: {
        modelsEndpoint: modelsResult,
        chatCompletions: chatResult,
      },
      triedBaseUrls: candidates,
      error: !modelsResult.ok
        ? modelsResult.error
        : !chatResult.ok
          ? chatResult.error
          : undefined,
    };

    if (report.success) {
      return report;
    }

    if (!bestFailure || (modelsResult.ok && !bestFailure.compatibility.modelsEndpoint.ok)) {
      bestFailure = report;
    }
  }

  return bestFailure ?? {
    success: false,
    normalizedBaseUrl: candidates[0] ?? '',
    models: [],
    compatibility: {
      modelsEndpoint: { ok: false, error: '未找到兼容的 Base URL', models: [] },
      chatCompletions: { ok: false, error: '未找到兼容的 Base URL' },
    },
    triedBaseUrls: candidates,
    error: '未找到兼容的 Base URL',
  };
}
