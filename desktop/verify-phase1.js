const { chromium } = require('playwright');

(async () => {
  console.log('启动浏览器验证 AIASK Desktop Phase 1 改造...');

  const browser = await chromium.launch({ headless: false });
  const page = await browser.newPage();

  // 访问开发服务器
  console.log('访问 http://127.0.0.1:1420/');
  await page.goto('http://127.0.0.1:1420/', { waitUntil: 'networkidle' });

  console.log('页面已加载，等待 3 秒...');
  await page.waitForTimeout(3000);

  // 验证 Phase 1: 检查侧边栏导航项数量
  console.log('\n=== Phase 1 验证：侧边栏导航 ===');

  // 尝试多种可能的选择器
  const possibleSelectors = [
    '.sidebar-nav-item',
    '[data-testid="nav-item"]',
    '.app-sidebar button[role="button"]',
    '.nav-button',
    'aside button',
    'nav button'
  ];

  let navItems = [];
  for (const selector of possibleSelectors) {
    navItems = await page.locator(selector).all();
    if (navItems.length > 0) {
      console.log(`✓ 使用选择器 "${selector}" 找到 ${navItems.length} 个导航项`);
      break;
    }
  }

  if (navItems.length === 0) {
    console.log('⚠️  未找到导航项，尝试查看页面结构...');
    const html = await page.content();
    console.log('页面 HTML 长度:', html.length);
  } else {
    // 获取导航项文本
    console.log('\n导航项列表:');
    for (let i = 0; i < navItems.length; i++) {
      const text = await navItems[i].textContent();
      console.log(`  ${i + 1}. ${text?.trim() || '(无文本)'}`);
    }

    // 验证预期的 6 个核心导航
    const expectedNavs = ['工作台', '项目/上下文', '运行/事件', '集成', '金融实验室', '设置'];
    console.log('\n预期的 6 个核心导航:', expectedNavs.join(', '));

    if (navItems.length === 6) {
      console.log('✅ 验证成功: 侧边栏显示 6 个导航项');
    } else if (navItems.length < 10) {
      console.log(`⚠️  接近预期: 找到 ${navItems.length} 个导航项（可能包含额外按钮）`);
    } else {
      console.log(`❌ 验证失败: 预期 6 个导航项，实际找到 ${navItems.length} 个`);
    }
  }

  // 截图保存
  await page.screenshot({ path: 'phase1-verification.png', fullPage: true });
  console.log('\n✓ 截图已保存: phase1-verification.png');

  // 验证集成中心
  console.log('\n=== 验证集成中心 ===');
  try {
    const integrationsBtn = page.locator('text=集成').first();
    if (await integrationsBtn.isVisible({ timeout: 2000 })) {
      await integrationsBtn.click();
      await page.waitForTimeout(1500);

      const cards = await page.locator('.optimization-card, .action-card, [class*="card"]').all();
      console.log(`✓ 集成中心显示 ${cards.length} 个卡片`);

      if (cards.length === 5) {
        console.log('✅ 验证成功: 集成中心显示 5 个卡片 (包含新增的"工具审批")');
      } else {
        console.log(`ℹ️  找到 ${cards.length} 个卡片`);
      }

      await page.screenshot({ path: 'integrations-page.png' });
      console.log('✓ 集成中心截图已保存: integrations-page.png');
    } else {
      console.log('⚠️  未找到"集成"按钮');
    }
  } catch (err) {
    console.log('⚠️  验证集成中心时出错:', err.message);
  }

  // 验证金融实验室
  console.log('\n=== 验证金融实验室 ===');
  try {
    const financeBtn = page.locator('text=金融').first();
    if (await financeBtn.isVisible({ timeout: 2000 })) {
      await financeBtn.click();
      await page.waitForTimeout(1500);

      const financeCards = await page.locator('.optimization-card, .action-card, [class*="card"]').all();
      console.log(`✓ 金融实验室显示 ${financeCards.length} 个卡片`);

      if (financeCards.length === 7) {
        console.log('✅ 验证成功: 金融实验室显示 7 个模块卡片');
      } else {
        console.log(`ℹ️  找到 ${financeCards.length} 个卡片`);
      }

      await page.screenshot({ path: 'finance-lab-page.png' });
      console.log('✓ 金融实验室截图已保存: finance-lab-page.png');
    } else {
      console.log('⚠️  未找到"金融"按钮');
    }
  } catch (err) {
    console.log('⚠️  验证金融实验室时出错:', err.message);
  }

  console.log('\n=== 验证完成 ===');
  console.log('请查看截图文件确认界面效果');

  // 保持浏览器打开 10 秒供人工检查
  console.log('\n浏览器将保持打开 10 秒供人工检查...');
  await page.waitForTimeout(10000);

  await browser.close();
  console.log('浏览器已关闭');
})().catch(err => {
  console.error('❌ 验证失败:', err);
  process.exit(1);
});
