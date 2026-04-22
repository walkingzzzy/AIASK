import test from 'node:test';
import assert from 'node:assert/strict';

const { SkillsService } = await import('../dist/skills/skills.service.js');

test('SkillsService.listSkills surfaces MCP text errors instead of returning an empty registry', async () => {
  const service = new SkillsService({
    callTool: async (tool) => {
      assert.equal(tool, 'list_skills');
      return 'Unknown tool: list_skills';
    },
  });

  await assert.rejects(
    () => service.listSkills(),
    (error) => {
      const response = error.getResponse?.();
      assert.equal(response?.code, 'SKILLS_REGISTRY_UNAVAILABLE');
      assert.match(String(response?.message ?? ''), /Unknown tool: list_skills/);
      return true;
    },
  );
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
  assert.equal(response.count, 1);
  assert.equal(response.source, 'codex_registry');
  assert.equal(response.data[0]?.id, 'akshare-market');
  assert.equal(response.data[0]?.status, 'executable');
});
