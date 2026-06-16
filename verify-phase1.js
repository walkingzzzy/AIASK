const { _electron: electron } = require('playwright');
const path = require('path');

(async () => {
  console.log('启动 AIASK Desktop 应用...');

  // 启动 Electron 应用
  const electronApp = await electron.launch({
    args: [path.join(__dirname, '..', 'desktop-out', 'main', 'index.js')],
    timeout: 30000
  });

  // 等待主窗口
  const window = await electronApp.firstWindow();
  await window.waitForLoadState('domcontentloaded');

  console.log('应用已启动，等待页面加载...');
  await window.waitForTimeout(3000);

  // 验证 Phase 1: 检查侧边栏导航项数量
  console.log('\n=== Phase 1 验证 ===');

  // 查找侧边栏导航项
  const navItems = await window.locator('.sidebar-nav-item, [role="navigation"] button, .nav-button').all();
  console.log(`✓ 找到 ${navItems.length} 个侧边栏导航项`);

  // 获取导航项文本
  for (let i = 0; i < navItems.length; i++) {
    const text = await navItems[i].textContent();
    console.log(`  ${i + 1}. ${text?.trim() || '(无文本)'}`);
  }

  // 截图保存
  await window.screenshot({ path: 'phase1-verification.png', fullPage: true });
  console.log('\n✓ 截图已保存: phase1-verification.png');

  // 验证预期的 6 个核心导航
  const expectedNavs = ['工作台', '项目', '运行', '集成', '金融', '设置'];
  console.log('\n预期的 6 个核心导航:', expectedNavs.join(', '));

  if (navItems.length === 6) {
    console.log('✅ 验证成功: 侧边栏显示 6 个导航项');
  } else {
    console.log(`⚠️  验证警告: 预期 6 个导航项，实际找到 ${navItems.length} 个`);
  }

  // 点击"集成"导航，验证卡片
  console.log('\n=== 验证集成中心 ===');
  const integrationsBtn = await window.locator('text=集成').first();
  if (await integrationsBtn.isVisible()) {
    await integrationsBtn.click();
    await window.waitForTimeout(1000);

    const cards = await window.locator('.optimization-card, .integration-card, [class*="card"]').all();
    console.log(`✓ 集成中心显示 ${cards.length} 个卡片`);

    if (cards.length === 5) {
      console.log('✅ 验证成功: 集成中心显示 5 个卡片 (包含新增的"工具审批")');
    } else {
      console.log(`⚠️  验证警告: 预期 5 个卡片，实际找到 ${cards.length} 个`);
    }

    await window.screenshot({ path: 'integrations-page.png' });
    console.log('✓ 集成中心截图已保存: integrations-page.png');
  }

  // 点击"金融实验室"，验证卡片
  console.log('\n=== 验证金融实验室 ===');
  const financeBtn = await window.locator('text=金融').first();
  if (await financeBtn.isVisible()) {
    await financeBtn.click();
    await window.waitForTimeout(1000);

    const financeCards = await window.locator('.optimization-card, .finance-card, [class*="card"]').all();
    console.log(`✓ 金融实验室显示 ${financeCards.length} 个卡片`);

    if (financeCards.length === 7) {
      console.log('✅ 验证成功: 金融实验室显示 7 个模块卡片');
    } else {
      console.log(`⚠️  验证警告: 预期 7 个卡片，实际找到 ${financeCards.length} 个`);
    }

    await window.screenshot({ path: 'finance-lab-page.png' });
    console.log('✓ 金融实验室截图已保存: finance-lab-page.png');
  }

  console.log('\n=== 验证完成 ===');
  console.log('请查看截图文件确认界面效果');

  await electronApp.close();
  console.log('应用已关闭');
})().catch(err => {
  console.error('验证失败:', err);
  process.exit(1);
});
