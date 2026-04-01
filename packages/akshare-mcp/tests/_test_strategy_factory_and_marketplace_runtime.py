from __future__ import annotations

from ._test_strategy_factory_and_marketplace_support import *

class TestRuntimeRiskEnhancements:
    @pytest.mark.asyncio
    async def test_runtime_risk_scan_executes_risk_actions(self, monkeypatch):
        from akshare_mcp.services.runtime_risk import StrategyRuntimeRiskService

        db = _StrategyDB()
        await db.save_strategy({
            'id': 'sid_risk',
            'name': '风险策略',
            'strategy_type': 'momentum',
            'status': 'listed',
            'params': {'lookback': 20},
            'factor_weights': {},
        })
        db._paper_accounts['acct_risk'] = {'id': 'acct_risk', 'strategy_id': 'sid_risk', 'status': 'active', 'initial_capital': 100000, 'total_value': 70000}
        await db.save_strategy_incubation_account('sid_risk', 'acct_risk', stage='candidate', status='active')
        await db.save_strategy_incubation_metric('sid_risk', '2026-03-07', {
            'account_id': 'acct_risk',
            'max_drawdown': 0.35,
            'daily_return': -0.02,
            'exposure_rate': 0.98,
            'alpha_decay': 0.1,
            'drift_score': 0.1,
            'decision': 'halt',
        })

        class _DummyAction:
            def to_dict(self):
                return {'action_type': 'force_liquidate', 'code': '600519', 'shares': 100, 'price': 10.0, 'reason': 'test'}

        class _DummyExecutor:
            async def enforce(self, account_id):
                assert account_id == 'acct_risk'
                return [_DummyAction()]

        monkeypatch.setattr('akshare_mcp.services.risk_executor.get_risk_executor', lambda: _DummyExecutor())

        service = StrategyRuntimeRiskService()
        result = await service.scan(db, [{'id': 'sid_risk', 'status': 'listed'}], enforce_actions=True)

        assert result['event_count'] >= 1
        assert result['action_count'] == 1
        assert result['snapshot_count'] >= 1
        latest_snapshot = await db.get_latest_strategy_runtime_risk_snapshot('sid_risk')
        assert latest_snapshot is not None
        assert latest_snapshot['posture_level'] == 'critical'
        assert latest_snapshot['control_mode'] == 'halted'
        control = await db.get_strategy_runtime_control('sid_risk')
        assert control['control_mode'] == 'halted'
        domain_events = await db.list_strategy_domain_events(strategy_id='sid_risk', event_type='runtime_risk.actions_executed', limit=10)
        assert len(domain_events) == 1

    @pytest.mark.asyncio
    async def test_runtime_risk_recovery_restores_strategy_and_snapshot(self, monkeypatch):
        mcp = _DummyMCP()
        sm_mod.register_strategy_manager(mcp)
        db = _StrategyDB()
        monkeypatch.setattr(sm_mod, 'get_db', lambda: db)

        await db.save_strategy({
            'id': 'sid_recover',
            'name': '恢复策略',
            'strategy_type': 'momentum',
            'status': 'listed',
            'params': {'lookback': 20},
            'factor_weights': {},
        })
        await db.update_strategy_status('sid_recover', 'suspended', actor_id='runtime_risk', reason='runtime_circuit_breaker')
        db._paper_accounts['acct_recover'] = {
            'id': 'acct_recover',
            'strategy_id': 'sid_recover',
            'status': 'frozen',
            'promotion_candidate': False,
            'initial_capital': 100000,
            'total_value': 98000,
        }
        await db.save_strategy_incubation_account('sid_recover', 'acct_recover', stage='candidate', status='active')
        await db.save_strategy_incubation_metric('sid_recover', '2026-03-08', {
            'account_id': 'acct_recover',
            'max_drawdown': 0.08,
            'daily_return': 0.01,
            'exposure_rate': 0.42,
            'alpha_decay': 0.06,
            'drift_score': 0.08,
            'decision': 'promote',
        })
        await db.save_strategy_runtime_risk_event({
            'strategy_id': 'sid_recover',
            'account_id': 'acct_recover',
            'severity': 'critical',
            'event_type': 'liquidity_stress',
            'action': 'halt_and_liquidate',
            'title': '损失与暴露复合熔断',
            'reason': 'test',
            'status': 'open',
            'payload': {},
        })
        await db.save_strategy_runtime_control({
            'strategy_id': 'sid_recover',
            'control_mode': 'halted',
            'status': 'active',
            'reason': 'test',
            'source': 'runtime_risk',
        })

        recovery = await mcp.strategy_manager(action='risk_recovery', kwargs=json.dumps({'strategy_id': 'sid_recover', 'source': 'pytest'}))
        snapshots = await mcp.strategy_manager(action='risk_snapshots', kwargs=json.dumps({'strategy_id': 'sid_recover', 'limit': 10}))
        detail = await mcp.strategy_manager(action='detail', kwargs=json.dumps({'strategy_id': 'sid_recover'}))
        strategy = await db.get_strategy('sid_recover')
        control = await db.get_strategy_runtime_control('sid_recover')
        latest_snapshot = await db.get_latest_strategy_runtime_risk_snapshot('sid_recover')
        open_events = await db.list_strategy_runtime_risk_events(strategy_id='sid_recover', status='open', limit=10)

        assert recovery['success'] is True
        assert recovery['data']['eligible'] is True
        assert recovery['data']['recovered'] is True
        assert recovery['data']['recovery']['to_status'] == 'listed'
        assert strategy['status'] == 'listed'
        assert control['control_mode'] == 'active'
        assert db._paper_accounts['acct_recover']['status'] == 'active'
        assert db._paper_accounts['acct_recover']['promotion_candidate'] is True
        assert open_events == []
        assert latest_snapshot is not None
        assert latest_snapshot['posture_level'] == 'safe'
        assert latest_snapshot['control_mode'] == 'active'
        assert snapshots['data']['count'] >= 1
        assert snapshots['data']['latest']['posture_level'] == 'safe'
        assert detail['data']['latest_runtime_risk_snapshot']['posture_level'] == 'safe'


class TestRuntimeAlertEnhancements:
    @pytest.mark.asyncio
    async def test_runtime_risk_scan_generates_runtime_alerts_and_ack(self, monkeypatch):
        mcp = _DummyMCP()
        sm_mod.register_strategy_manager(mcp)
        db = _StrategyDB()
        monkeypatch.setattr(sm_mod, 'get_db', lambda: db)

        await db.save_strategy({
            'id': 'sid_alert',
            'name': '告警策略',
            'strategy_type': 'momentum',
            'status': 'listed',
            'params': {'lookback': 10},
            'factor_weights': {},
        })
        await db.save_strategy_incubation_account('sid_alert', 'acct_alert', stage='candidate', status='active')
        await db.save_strategy_incubation_metric('sid_alert', '2026-03-08', {
            'account_id': 'acct_alert',
            'max_drawdown': 0.31,
            'daily_return': -0.09,
            'exposure_rate': 0.98,
            'alpha_decay': 0.12,
            'drift_score': 0.18,
        })

        scan = await mcp.strategy_manager(action='risk_scan_run', kwargs=json.dumps({'strategy_id': 'sid_alert', 'enforce_actions': False}))
        alerts = await mcp.strategy_manager(action='runtime_alerts', kwargs=json.dumps({'strategy_id': 'sid_alert', 'limit': 20}))

        assert scan['success'] is True
        assert scan['data']['alert_count'] >= 1
        assert alerts['data']['count'] >= 1
        first_alert = alerts['data']['items'][0]
        ack = await mcp.strategy_manager(action='runtime_alert_ack', kwargs=json.dumps({'alert_id': first_alert['alert_id'], 'acknowledged_by': 'pytest'}))
        latest = await db.get_latest_strategy_runtime_alert('sid_alert')

        assert ack['success'] is True
        assert ack['data']['status'] == 'acknowledged'
        assert latest is not None
        assert latest['status'] in {'open', 'acknowledged'}

    @pytest.mark.asyncio
    async def test_runtime_risk_recovery_resolves_runtime_alerts(self, monkeypatch):
        mcp = _DummyMCP()
        sm_mod.register_strategy_manager(mcp)
        db = _StrategyDB()
        monkeypatch.setattr(sm_mod, 'get_db', lambda: db)

        await db.save_strategy({
            'id': 'sid_alert_recover',
            'name': '恢复告警策略',
            'strategy_type': 'momentum',
            'status': 'listed',
            'params': {'lookback': 20},
            'factor_weights': {},
        })
        await db.update_strategy_status('sid_alert_recover', 'suspended', actor_id='runtime_risk', reason='runtime_circuit_breaker')
        await db.save_strategy_incubation_account('sid_alert_recover', 'acct_alert_recover', stage='candidate', status='active')
        await db.save_strategy_incubation_metric('sid_alert_recover', '2026-03-08', {
            'account_id': 'acct_alert_recover',
            'max_drawdown': 0.08,
            'daily_return': 0.02,
            'exposure_rate': 0.35,
            'alpha_decay': 0.05,
            'drift_score': 0.05,
            'decision': 'promote',
        })
        await db.save_strategy_runtime_control({
            'strategy_id': 'sid_alert_recover',
            'account_id': 'acct_alert_recover',
            'control_mode': 'halted',
            'status': 'engaged',
            'source': 'runtime_risk',
            'reason': 'test',
        })
        await db.save_strategy_runtime_alert({
            'strategy_id': 'sid_alert_recover',
            'account_id': 'acct_alert_recover',
            'alert_key': 'control:sid_alert_recover:halted',
            'category': 'halted_control',
            'severity': 'critical',
            'status': 'open',
            'title': '运行控制已熔断',
            'message': 'test',
            'escalation_level': 3,
        })

        recovery = await mcp.strategy_manager(action='risk_recovery', kwargs=json.dumps({'strategy_id': 'sid_alert_recover', 'source': 'pytest'}))
        resolved = await mcp.strategy_manager(action='runtime_alerts', kwargs=json.dumps({'strategy_id': 'sid_alert_recover', 'status': 'resolved', 'limit': 20}))

        assert recovery['success'] is True
        assert recovery['data']['recovered'] is True
        assert resolved['data']['count'] >= 1
        assert any(item.get('category') == 'halted_control' for item in resolved['data']['items'])

class TestVectorGovernanceEnhancements:
    @pytest.mark.asyncio
    async def test_vector_rebuild_creates_task_run_and_registry(self, monkeypatch):
        from akshare_mcp.services.vector_governance import StrategyVectorGovernanceService

        db = _StrategyDB()
        await db.save_strategy({'id': 'sid_vec_1', 'name': '向量1', 'strategy_type': 'momentum', 'status': 'listed', 'params': {'lookback': 20}, 'factor_weights': {}})
        await db.save_strategy({'id': 'sid_vec_2', 'name': '向量2', 'strategy_type': 'momentum', 'status': 'incubating', 'params': {'lookback': 10}, 'factor_weights': {}})
        await db.save_vector_index_registry({'index_name': 'strategy_behavior', 'index_version': 'old_v1', 'status': 'active', 'metadata': {}})

        class _DummyVectorPlatform:
            class engine:
                backend = 'index'

            async def build_profiles_for_strategies(self, db, strategies, profile_type='behavior', vector_method='price_volume', index_name='strategy_behavior', index_version='v1'):
                built = []
                for idx, strategy in enumerate(strategies, 1):
                    built.append(await db.save_strategy_vector_profile({
                        'strategy_id': strategy['id'],
                        'profile_type': profile_type,
                        'vector_method': vector_method,
                        'metric': 'cosine',
                        'vector_dim': 3,
                        'embedding': [0.1 * idx, 0.2 * idx, 0.3 * idx],
                        'signature': f'sig_{idx}',
                        'backend': 'index',
                        'index_version': index_version,
                        'metadata': {'index_name': index_name, 'index_version': index_version},
                    }))
                return {'count': len(strategies), 'items': built}

            async def build_persisted_ann_index(self, db, index_name='strategy_behavior', index_version='v1', profile_type='behavior', task_run_id=None, source='vector_governance', limit_profiles=5000):
                snapshot = await db.save_strategy_vector_index_snapshot({
                    'index_name': index_name,
                    'index_version': index_version,
                    'status': 'active',
                    'profile_type': profile_type,
                    'vector_method': 'price_volume',
                    'metric': 'cosine',
                    'backend': 'index',
                    'profile_count': 2,
                    'bucket_count': 1,
                    'vector_dim': 3,
                    'centroids': [{'bucket_id': 'bucket_01', 'size': 2, 'neighbors': []}],
                    'metadata': {'task_run_id': task_run_id, 'source': source},
                    'task_run_id': task_run_id,
                    'source': source,
                })
                await db.replace_strategy_vector_index_items(index_name, index_version, [
                    {'profile_id': 1, 'strategy_id': 'sid_vec_1', 'profile_type': profile_type, 'vector_method': 'price_volume', 'metric': 'cosine', 'vector_dim': 3, 'bucket_id': 'bucket_01', 'coarse_score': 0.99, 'embedding': [0.1, 0.2, 0.3], 'metadata': {'signature': 'sig_1'}},
                    {'profile_id': 2, 'strategy_id': 'sid_vec_2', 'profile_type': profile_type, 'vector_method': 'price_volume', 'metric': 'cosine', 'vector_dim': 3, 'bucket_id': 'bucket_01', 'coarse_score': 0.98, 'embedding': [0.2, 0.4, 0.6], 'metadata': {'signature': 'sig_2'}},
                ])
                return {'snapshot': snapshot, 'items_count': 2, 'bucket_count': 1, 'profile_count': 2}

        monkeypatch.setattr('akshare_mcp.services.vector_platform.get_strategy_vector_platform', lambda: _DummyVectorPlatform())

        service = StrategyVectorGovernanceService()
        result = await service.rebuild_index(db, index_name='strategy_behavior', index_version='v2', statuses=['listed', 'incubating'], limit=10)

        assert result['task_run_id'] is not None
        assert result['built_profiles'] == 2
        assert result['persisted_snapshot_id'] is not None
        assert result['persisted_items'] == 2
        indexes = await db.list_vector_index_registry(index_name='strategy_behavior', limit=10)
        assert any(item.get('index_version') == 'v2' for item in indexes)
        assert any(item.get('index_version') == 'old_v1' and item.get('status') == 'stale' for item in indexes)
        snapshots = await db.list_strategy_vector_index_snapshots(index_name='strategy_behavior', limit=10)
        assert any(item.get('index_version') == 'v2' and item.get('status') == 'active' for item in snapshots)
        items = await db.list_strategy_vector_index_items(index_name='strategy_behavior', index_version='v2', limit=10)
        assert len(items) == 2


__all__ = [name for name in globals() if name.startswith("Test")]
