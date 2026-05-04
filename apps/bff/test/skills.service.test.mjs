import test from 'node:test';
import assert from 'node:assert/strict';

const { SkillsService } = await import('../dist/skills/skills.service.js');

test('SkillsService.listSkills falls back to executable built-ins when MCP registry is unavailable', async () => {
  const service = new SkillsService({
    callTool: async (tool) => {
      assert.equal(tool, 'list_skills');
      return 'Unknown tool: list_skills';
    },
  });

  const response = await service.listSkills();
  assert.equal(response.source, 'bff_fallback');
  assert.equal(response.data.filter((skill) => skill.executable).length >= 3, true);
  assert.equal(response.data.some((skill) => skill.id === 'akshare-stock-deep-analysis'), true);
});

test('SkillsService.listSkills returns normalized registry entries when MCP responds with a registry payload', async () => {
  const service = new SkillsService({
    callTool: async (tool) => {
      assert.equal(tool, 'list_skills');
      return {
        success: true,
        data: {
          count: 1,
          source: 'codex_registry',
          skills: [
            {
              id: 'akshare-market',
              name: 'akshare-market',
              description: 'A股行情与基础查询',
              category: 'market',
              tags: ['market'],
              executable: true,
              status: 'executable',
            },
          ],
        },
      };
    },
  });

  const response = await service.listSkills();
  assert.equal(response.count >= 4, true);
  assert.equal(response.source, 'codex_registry');
  const marketSkill = response.data.find((skill) => skill.id === 'akshare-market');
  assert.equal(marketSkill?.status, 'executable');
  assert.equal(response.data.some((skill) => skill.id === 'akshare-strategy-factory' && skill.executable), true);
});

test('SkillsService.triggerSkill executes fallback executable skills through BFF local runner', async () => {
  const service = new SkillsService({
    callTool: async (tool) => {
      assert.equal(tool, 'list_skills');
      return 'Unknown tool: list_skills';
    },
  });

  const response = await service.triggerSkill('akshare-market', { code: '601398', task: 'quote_only' }, 'u_admin');

  assert.equal(response.success, true);
  assert.equal(response.skill.id, 'akshare-market');
  assert.equal(response.execution.status, 'completed');
  assert.equal(response.result.status, 'completed');
  assert.equal(response.result.skill_id, 'akshare-market');
  assert.equal(response.meta.backend_used, 'bff_local_runner');
  assert.equal(response.meta.fallback_used, true);
  assert.match(response.workbench.href, /skill=akshare-market/);
});

test('SkillsService.triggerSkill uses MCP run_skill before local fallback when registry is available', async () => {
  const calls = [];
  const service = new SkillsService({
    callTool: async (tool, args) => {
      calls.push({ tool, args });
      if (tool === 'list_skills') {
        return {
          success: true,
          data: {
            count: 1,
            source: 'codex_registry',
            skills: [
              {
                id: 'akshare-market',
                name: 'A股行情',
                category: 'market',
                executable: true,
                status: 'executable',
                handler_available: true,
                execution_mode: 'orchestrated',
                supported_tasks: ['quote_only'],
              },
            ],
          },
        };
      }
      assert.equal(tool, 'run_skill');
      return {
        success: true,
        data: {
          skill: { id: 'akshare-market', status: 'executable', executable: true },
          execution: { status: 'completed', skill_id: 'akshare-market' },
          result: { status: 'completed', skill_id: 'akshare-market', backend_used: 'built_in_orchestrator' },
          message: 'Skill executed via built-in orchestrator',
          source: 'codex_registry',
        },
        backend_requested: 'skill_executor',
        backend_used: 'built_in_orchestrator',
        fallback_used: false,
        fallback_reason: null,
        latency_ms: 12,
      };
    },
  });

  const response = await service.triggerSkill('akshare-market', { code: '601398', task: 'quote_only' }, 'u_admin');

  assert.deepEqual(calls.map((call) => call.tool), ['list_skills', 'run_skill']);
  assert.equal(calls[1].args.skill_id, 'akshare-market');
  assert.equal(response.success, true);
  assert.equal(response.meta.backend_used, 'built_in_orchestrator');
  assert.equal(response.meta.fallback_used, false);
});

test('SkillsService.triggerSkill prefers run_skill execution meta over generic MCP source meta', async () => {
  const service = new SkillsService({
    callTool: async (tool) => {
      if (tool === 'list_skills') {
        return {
          success: true,
          data: {
            count: 1,
            source: 'codex_registry',
            skills: [
              {
                id: 'akshare-market',
                name: 'A股行情',
                category: 'market',
                executable: true,
                status: 'executable',
                handler_available: true,
                execution_mode: 'orchestrated',
                supported_tasks: ['quote_only'],
              },
            ],
          },
        };
      }
      assert.equal(tool, 'run_skill');
      return {
        success: true,
        source: 'akshare',
        backend_requested: 'akshare',
        backend_used: 'akshare',
        fallback_used: false,
        data: {
          skill: { id: 'akshare-market', status: 'executable', executable: true },
          execution: { status: 'completed', skill_id: 'akshare-market' },
          result: { status: 'completed', skill_id: 'akshare-market' },
          message: 'Skill executed via built-in orchestrator',
          source: 'codex_registry',
          backend_requested: 'skill_executor',
          backend_used: 'built_in_orchestrator',
          fallback_used: false,
          fallback_reason: null,
          latency_ms: 42,
        },
      };
    },
  });

  const response = await service.triggerSkill('akshare-market', { code: '601398', task: 'quote_only' }, 'u_admin');

  assert.equal(response.meta.backend_requested, 'skill_executor');
  assert.equal(response.meta.backend_used, 'built_in_orchestrator');
  assert.equal(response.meta.latency_ms, 42);
});

test('SkillsService.triggerSkill falls back locally only when MCP run_skill is unavailable', async () => {
  const calls = [];
  const service = new SkillsService({
    callTool: async (tool) => {
      calls.push(tool);
      if (tool === 'list_skills') {
        return {
          success: true,
          data: {
            count: 1,
            source: 'codex_registry',
            skills: [
              {
                id: 'akshare-market',
                name: 'A股行情',
                category: 'market',
                executable: true,
                status: 'executable',
                handler_available: true,
                execution_mode: 'orchestrated',
                supported_tasks: ['quote_only'],
              },
            ],
          },
        };
      }
      throw new Error('Unknown tool: run_skill');
    },
  });

  const response = await service.triggerSkill('akshare-market', { code: '601398', task: 'quote_only' }, 'u_admin');

  assert.deepEqual(calls, ['list_skills', 'run_skill']);
  assert.equal(response.success, true);
  assert.equal(response.meta.backend_used, 'bff_local_runner');
  assert.equal(response.meta.fallback_used, true);
  assert.match(response.meta.fallback_reason, /mcp_run_skill_unavailable/);
});

test('SkillsService.triggerSkill falls back locally when merged fallback skill is missing from MCP run_skill', async () => {
  const calls = [];
  const service = new SkillsService({
    callTool: async (tool) => {
      calls.push(tool);
      if (tool === 'list_skills') {
        return {
          success: true,
          data: {
            count: 1,
            source: 'codex_registry',
            skills: [
              {
                id: 'akshare-market',
                name: 'A股行情',
                category: 'market',
                executable: true,
                status: 'executable',
                handler_available: true,
                execution_mode: 'orchestrated',
                supported_tasks: ['quote_only'],
              },
            ],
          },
        };
      }
      assert.equal(tool, 'run_skill');
      return {
        success: false,
        error_code: 'SKILL_NOT_FOUND',
        message: 'Skill akshare-market not found in MCP run_skill registry',
      };
    },
  });

  const response = await service.triggerSkill('akshare-market', { code: '601398', task: 'quote_only' }, 'u_admin');

  assert.deepEqual(calls, ['list_skills', 'run_skill']);
  assert.equal(response.success, true);
  assert.equal(response.meta.backend_used, 'bff_local_runner');
  assert.equal(response.meta.fallback_used, true);
  assert.match(response.meta.fallback_reason, /skill_not_found/i);
});
