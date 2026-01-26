/**
 * 产业链分析服务
 * 提供产业链结构、上下游关系、事件传导分析
 */

// 产业链节点
export interface ChainNode {
    name: string;           // 节点名称
    type: 'upstream' | 'midstream' | 'downstream';  // 上游/中游/下游
    description: string;    // 描述
    stocks: string[];       // 相关股票代码
    keywords: string[];     // 关键词
}

// 产业链定义
export interface IndustryChain {
    id: string;
    name: string;
    description: string;
    nodes: ChainNode[];
    relations: Array<{
        from: string;
        to: string;
        type: 'supply' | 'demand' | 'compete';
    }>;
}

// 核心产业链数据（自建知识库）
export const INDUSTRY_CHAINS: Record<string, IndustryChain> = {
    // ========== 新能源汽车产业链 ==========
    new_energy_vehicle: {
        id: 'new_energy_vehicle',
        name: '新能源汽车',
        description: '从锂矿到整车的完整产业链',
        nodes: [
            {
                name: '锂矿资源',
                type: 'upstream',
                description: '锂矿开采和锂盐生产',
                stocks: ['002460', '002466', '300750'],  // 赣锋锂业、天齐锂业、宁德时代
                keywords: ['锂矿', '碳酸锂', '氢氧化锂'],
            },
            {
                name: '正极材料',
                type: 'upstream',
                description: '三元材料、磷酸铁锂等',
                stocks: ['002074', '300073', '603659'],
                keywords: ['正极', '三元材料', '磷酸铁锂'],
            },
            {
                name: '负极材料',
                type: 'upstream',
                description: '石墨负极、硅碳负极',
                stocks: ['603659', '835185'],
                keywords: ['负极', '石墨', '硅碳'],
            },
            {
                name: '电解液',
                type: 'upstream',
                description: '电解液及添加剂',
                stocks: ['300014', '002407'],
                keywords: ['电解液', '六氟磷酸锂'],
            },
            {
                name: '隔膜',
                type: 'upstream',
                description: '湿法隔膜、干法隔膜',
                stocks: ['002812', '300568'],
                keywords: ['隔膜', '湿法', '干法'],
            },
            {
                name: '动力电池',
                type: 'midstream',
                description: '电芯、模组、PACK',
                stocks: ['300750', '002594', '300014'],  // 宁德时代、比亚迪
                keywords: ['动力电池', '电芯', '电池包'],
            },
            {
                name: '电机电控',
                type: 'midstream',
                description: '驱动电机、电机控制器',
                stocks: ['002196', '300748'],
                keywords: ['电机', '电控', '驱动'],
            },
            {
                name: '整车制造',
                type: 'downstream',
                description: '新能源整车企业',
                stocks: ['002594', '601238', '000625'],  // 比亚迪、广汽、长安
                keywords: ['整车', '新能源车', '电动车'],
            },
            {
                name: '充电桩',
                type: 'downstream',
                description: '充电设备和运营',
                stocks: ['300001', '002121'],
                keywords: ['充电桩', '充电站', '换电'],
            },
        ],
        relations: [
            { from: '锂矿资源', to: '正极材料', type: 'supply' },
            { from: '正极材料', to: '动力电池', type: 'supply' },
            { from: '负极材料', to: '动力电池', type: 'supply' },
            { from: '电解液', to: '动力电池', type: 'supply' },
            { from: '隔膜', to: '动力电池', type: 'supply' },
            { from: '动力电池', to: '整车制造', type: 'supply' },
            { from: '电机电控', to: '整车制造', type: 'supply' },
            { from: '整车制造', to: '充电桩', type: 'demand' },
        ],
    },

    // ========== 半导体产业链 ==========
    semiconductor: {
        id: 'semiconductor',
        name: '半导体',
        description: '从设计到封测的完整产业链',
        nodes: [
            {
                name: '半导体设备',
                type: 'upstream',
                description: '光刻机、刻蚀机、薄膜设备',
                stocks: ['002371', '688012', '300604'],
                keywords: ['光刻', '刻蚀', '半导体设备'],
            },
            {
                name: '半导体材料',
                type: 'upstream',
                description: '硅片、光刻胶、靶材',
                stocks: ['688126', '300236', '300346'],
                keywords: ['硅片', '光刻胶', '靶材'],
            },
            {
                name: 'IC设计',
                type: 'midstream',
                description: '芯片设计公司',
                stocks: ['688981', '603986', '300782'],  // 中芯国际、兆易创新、卓胜微
                keywords: ['芯片设计', 'IC设计', 'Fabless'],
            },
            {
                name: '晶圆代工',
                type: 'midstream',
                description: '芯片制造代工',
                stocks: ['688981', '600584'],  // 中芯国际、长电科技
                keywords: ['晶圆', '代工', '制造'],
            },
            {
                name: '封装测试',
                type: 'downstream',
                description: '芯片封装和测试',
                stocks: ['600584', '002156', '603005'],
                keywords: ['封测', '封装', '测试'],
            },
            {
                name: '芯片应用',
                type: 'downstream',
                description: '消费电子、汽车电子等',
                stocks: ['000725', '002475', '300223'],
                keywords: ['消费电子', '汽车电子', '物联网'],
            },
        ],
        relations: [
            { from: '半导体设备', to: '晶圆代工', type: 'supply' },
            { from: '半导体材料', to: '晶圆代工', type: 'supply' },
            { from: 'IC设计', to: '晶圆代工', type: 'demand' },
            { from: '晶圆代工', to: '封装测试', type: 'supply' },
            { from: '封装测试', to: '芯片应用', type: 'supply' },
        ],
    },

    // ========== 光伏产业链 ==========
    photovoltaic: {
        id: 'photovoltaic',
        name: '光伏',
        description: '从硅料到电站的完整产业链',
        nodes: [
            {
                name: '多晶硅',
                type: 'upstream',
                description: '硅料生产',
                stocks: ['600438', '002459', '603806'],  // 通威股份、晶澳科技
                keywords: ['多晶硅', '硅料', '工业硅'],
            },
            {
                name: '硅片',
                type: 'upstream',
                description: '单晶硅片、多晶硅片',
                stocks: ['601012', '002129'],  // 隆基绿能、中环股份
                keywords: ['硅片', '单晶', '切片'],
            },
            {
                name: '电池片',
                type: 'midstream',
                description: 'PERC、TOPCon、HJT电池',
                stocks: ['600438', '002459', '688223'],
                keywords: ['电池片', 'PERC', 'TOPCon', 'HJT'],
            },
            {
                name: '组件',
                type: 'midstream',
                description: '光伏组件封装',
                stocks: ['601012', '002459', '688599'],
                keywords: ['组件', '光伏板', '封装'],
            },
            {
                name: '逆变器',
                type: 'midstream',
                description: '光伏逆变器',
                stocks: ['300274', '688390'],  // 阳光电源
                keywords: ['逆变器', '储能'],
            },
            {
                name: '光伏电站',
                type: 'downstream',
                description: '电站建设和运营',
                stocks: ['601012', '600025'],
                keywords: ['电站', '运营', '发电'],
            },
        ],
        relations: [
            { from: '多晶硅', to: '硅片', type: 'supply' },
            { from: '硅片', to: '电池片', type: 'supply' },
            { from: '电池片', to: '组件', type: 'supply' },
            { from: '组件', to: '光伏电站', type: 'supply' },
            { from: '逆变器', to: '光伏电站', type: 'supply' },
        ],
    },

    // ========== 消费电子产业链 ==========
    consumer_electronics: {
        id: 'consumer_electronics',
        name: '消费电子',
        description: '手机、电脑等消费电子产业链',
        nodes: [
            {
                name: '面板',
                type: 'upstream',
                description: 'LCD、OLED面板',
                stocks: ['000725', '000100', '002387'],  // 京东方、TCL
                keywords: ['面板', 'LCD', 'OLED', '显示'],
            },
            {
                name: '被动元件',
                type: 'upstream',
                description: '电容、电阻、电感',
                stocks: ['603986', '300655'],
                keywords: ['电容', 'MLCC', '被动元件'],
            },
            {
                name: '连接器',
                type: 'upstream',
                description: '各类连接器',
                stocks: ['002475', '300351'],
                keywords: ['连接器', '接插件'],
            },
            {
                name: '摄像头模组',
                type: 'midstream',
                description: '手机摄像头模组',
                stocks: ['002241', '300691'],
                keywords: ['摄像头', '模组', '光学'],
            },
            {
                name: '声学器件',
                type: 'midstream',
                description: '扬声器、麦克风',
                stocks: ['002241', '002655'],
                keywords: ['声学', '扬声器', '麦克风'],
            },
            {
                name: '品牌终端',
                type: 'downstream',
                description: '手机、电脑品牌商',
                stocks: ['000063', '002415'],  // 中兴、海康
                keywords: ['手机', '电脑', '终端'],
            },
        ],
        relations: [
            { from: '面板', to: '品牌终端', type: 'supply' },
            { from: '被动元件', to: '品牌终端', type: 'supply' },
            { from: '连接器', to: '品牌终端', type: 'supply' },
            { from: '摄像头模组', to: '品牌终端', type: 'supply' },
            { from: '声学器件', to: '品牌终端', type: 'supply' },
        ],
    },

    // ========== 医药产业链 ==========
    pharmaceutical: {
        id: 'pharmaceutical',
        name: '医药',
        description: '从原料药到终端的医药产业链',
        nodes: [
            {
                name: '原料药',
                type: 'upstream',
                description: 'API原料药生产',
                stocks: ['000078', '002422', '300199'],
                keywords: ['原料药', 'API', '中间体'],
            },
            {
                name: '医药中间体',
                type: 'upstream',
                description: '医药中间体',
                stocks: ['002422', '300199'],
                keywords: ['中间体', '精细化工'],
            },
            {
                name: '创新药',
                type: 'midstream',
                description: '创新药研发和生产',
                stocks: ['600276', '000963', '300760'],  // 恒瑞医药、华东医药
                keywords: ['创新药', '新药', '研发'],
            },
            {
                name: '仿制药',
                type: 'midstream',
                description: '仿制药生产',
                stocks: ['600276', '002001', '000513'],
                keywords: ['仿制药', '一致性评价'],
            },
            {
                name: 'CXO',
                type: 'midstream',
                description: '医药研发外包',
                stocks: ['603259', '300759', '300347'],  // 药明康德、康龙化成
                keywords: ['CRO', 'CMO', 'CDMO', '外包'],
            },
            {
                name: '医药流通',
                type: 'downstream',
                description: '医药分销和零售',
                stocks: ['600998', '601607', '002727'],
                keywords: ['流通', '分销', '药店'],
            },
        ],
        relations: [
            { from: '原料药', to: '创新药', type: 'supply' },
            { from: '原料药', to: '仿制药', type: 'supply' },
            { from: '医药中间体', to: '原料药', type: 'supply' },
            { from: 'CXO', to: '创新药', type: 'supply' },
            { from: '创新药', to: '医药流通', type: 'supply' },
            { from: '仿制药', to: '医药流通', type: 'supply' },
        ],
    },

    // ========== 白酒产业链 ==========
    liquor: {
        id: 'liquor',
        name: '白酒',
        description: '白酒产业链',
        nodes: [
            {
                name: '粮食原料',
                type: 'upstream',
                description: '高粱、小麦等酿酒原料',
                stocks: ['000998', '600598'],
                keywords: ['高粱', '小麦', '粮食'],
            },
            {
                name: '包装材料',
                type: 'upstream',
                description: '酒瓶、纸箱、瓶盖',
                stocks: ['002696', '002831'],
                keywords: ['包装', '酒瓶', '纸箱'],
            },
            {
                name: '高端白酒',
                type: 'midstream',
                description: '高端白酒品牌',
                stocks: ['600519', '000858', '000568'],  // 茅台、五粮液、泸州老窖
                keywords: ['高端', '茅台', '五粮液'],
            },
            {
                name: '次高端白酒',
                type: 'midstream',
                description: '次高端白酒品牌',
                stocks: ['000568', '600779', '603369'],
                keywords: ['次高端', '汾酒', '今世缘'],
            },
            {
                name: '区域白酒',
                type: 'midstream',
                description: '区域性白酒品牌',
                stocks: ['600559', '000596', '600199'],
                keywords: ['区域', '地方酒'],
            },
            {
                name: '白酒流通',
                type: 'downstream',
                description: '白酒经销和零售',
                stocks: ['300919', '603198'],
                keywords: ['经销', '零售', '电商'],
            },
        ],
        relations: [
            { from: '粮食原料', to: '高端白酒', type: 'supply' },
            { from: '粮食原料', to: '次高端白酒', type: 'supply' },
            { from: '包装材料', to: '高端白酒', type: 'supply' },
            { from: '高端白酒', to: '白酒流通', type: 'supply' },
            { from: '次高端白酒', to: '白酒流通', type: 'supply' },
        ],
    },

    // ========== AI人工智能产业链 ==========
    artificial_intelligence: {
        id: 'artificial_intelligence',
        name: '人工智能',
        description: 'AI算力、算法、应用产业链',
        nodes: [
            {
                name: 'AI芯片',
                type: 'upstream',
                description: 'GPU、NPU、AI加速芯片',
                stocks: ['688256', '688041', '603986'],
                keywords: ['GPU', 'AI芯片', '算力'],
            },
            {
                name: '服务器',
                type: 'upstream',
                description: 'AI服务器、算力基础设施',
                stocks: ['000977', '603019', '688396'],
                keywords: ['服务器', '算力', '数据中心'],
            },
            {
                name: '大模型',
                type: 'midstream',
                description: '大语言模型、多模态模型',
                stocks: ['002230', '300418', '688083'],
                keywords: ['大模型', 'LLM', 'GPT', 'AI'],
            },
            {
                name: 'AI应用',
                type: 'downstream',
                description: 'AI应用软件和服务',
                stocks: ['300033', '002415', '300496'],
                keywords: ['AI应用', '智能', '自动化'],
            },
            {
                name: '智能驾驶',
                type: 'downstream',
                description: '自动驾驶解决方案',
                stocks: ['002405', '300496', '601127'],
                keywords: ['自动驾驶', '智能驾驶', 'ADAS'],
            },
        ],
        relations: [
            { from: 'AI芯片', to: '服务器', type: 'supply' },
            { from: '服务器', to: '大模型', type: 'supply' },
            { from: '大模型', to: 'AI应用', type: 'supply' },
            { from: '大模型', to: '智能驾驶', type: 'supply' },
        ],
    },
};


// ========== 服务函数 ==========

/**
 * 获取所有产业链列表
 */
export function getAllChains(): Array<{ id: string; name: string; description: string; nodeCount: number }> {
    return Object.values(INDUSTRY_CHAINS).map(chain => ({
        id: chain.id,
        name: chain.name,
        description: chain.description,
        nodeCount: chain.nodes.length,
    }));
}

/**
 * 获取产业链详情
 */
export function getChainDetail(chainId: string): IndustryChain | null {
    return INDUSTRY_CHAINS[chainId] || null;
}

/**
 * 根据股票代码查找所属产业链
 */
export function findChainsByStock(stockCode: string): Array<{
    chainId: string;
    chainName: string;
    nodeName: string;
    nodeType: string;
}> {
    const results: Array<{
        chainId: string;
        chainName: string;
        nodeName: string;
        nodeType: string;
    }> = [];

    for (const chain of Object.values(INDUSTRY_CHAINS)) {
        for (const node of chain.nodes) {
            if (node.stocks.includes(stockCode)) {
                results.push({
                    chainId: chain.id,
                    chainName: chain.name,
                    nodeName: node.name,
                    nodeType: node.type,
                });
            }
        }
    }

    return results;
}

/**
 * 获取产业链上下游股票
 */
export function getChainStocks(chainId: string, nodeType?: 'upstream' | 'midstream' | 'downstream'): Array<{
    code: string;
    nodeName: string;
    nodeType: string;
}> {
    const chain = INDUSTRY_CHAINS[chainId];
    if (!chain) return [];

    const results: Array<{ code: string; nodeName: string; nodeType: string }> = [];

    for (const node of chain.nodes) {
        if (nodeType && node.type !== nodeType) continue;

        for (const code of node.stocks) {
            results.push({
                code,
                nodeName: node.name,
                nodeType: node.type,
            });
        }
    }

    return results;
}

/**
 * 分析事件对产业链的影响
 */
export function analyzeChainImpact(
    chainId: string,
    affectedNode: string,
    impactType: 'positive' | 'negative'
): Array<{
    nodeName: string;
    nodeType: string;
    impactLevel: 'direct' | 'indirect';
    impactDirection: 'positive' | 'negative';
    stocks: string[];
    reason: string;
}> {
    const chain = INDUSTRY_CHAINS[chainId];
    if (!chain) return [];

    const results: Array<{
        nodeName: string;
        nodeType: string;
        impactLevel: 'direct' | 'indirect';
        impactDirection: 'positive' | 'negative';
        stocks: string[];
        reason: string;
    }> = [];

    // 找到受影响的节点
    const sourceNode = chain.nodes.find(n => n.name === affectedNode);
    if (!sourceNode) return [];

    // 分析直接影响（上下游关系）
    for (const relation of chain.relations) {
        if (relation.from === affectedNode) {
            // 下游受影响
            const targetNode = chain.nodes.find(n => n.name === relation.to);
            if (targetNode) {
                const direction = relation.type === 'supply'
                    ? (impactType === 'positive' ? 'positive' : 'negative')
                    : impactType;

                results.push({
                    nodeName: targetNode.name,
                    nodeType: targetNode.type,
                    impactLevel: 'direct',
                    impactDirection: direction,
                    stocks: targetNode.stocks,
                    reason: `${affectedNode}${impactType === 'positive' ? '利好' : '利空'}，作为其下游${direction === 'positive' ? '受益' : '受损'}`,
                });
            }
        }

        if (relation.to === affectedNode) {
            // 上游受影响
            const targetNode = chain.nodes.find(n => n.name === relation.from);
            if (targetNode) {
                const direction = relation.type === 'demand'
                    ? impactType
                    : (impactType === 'positive' ? 'positive' : 'negative');

                results.push({
                    nodeName: targetNode.name,
                    nodeType: targetNode.type,
                    impactLevel: 'direct',
                    impactDirection: direction,
                    stocks: targetNode.stocks,
                    reason: `${affectedNode}${impactType === 'positive' ? '利好' : '利空'}，作为其上游${direction === 'positive' ? '需求增加' : '需求减少'}`,
                });
            }
        }
    }

    return results;
}

/**
 * 根据关键词搜索产业链节点
 */
export function searchChainByKeyword(keyword: string): Array<{
    chainId: string;
    chainName: string;
    nodeName: string;
    nodeType: string;
    stocks: string[];
}> {
    const results: Array<{
        chainId: string;
        chainName: string;
        nodeName: string;
        nodeType: string;
        stocks: string[];
    }> = [];

    const lowerKeyword = keyword.toLowerCase();

    for (const chain of Object.values(INDUSTRY_CHAINS)) {
        for (const node of chain.nodes) {
            const match = node.keywords.some(k => k.toLowerCase().includes(lowerKeyword)) ||
                node.name.toLowerCase().includes(lowerKeyword) ||
                node.description.toLowerCase().includes(lowerKeyword);

            if (match) {
                results.push({
                    chainId: chain.id,
                    chainName: chain.name,
                    nodeName: node.name,
                    nodeType: node.type,
                    stocks: node.stocks,
                });
            }
        }
    }

    return results;
}
