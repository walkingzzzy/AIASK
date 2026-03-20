"""用户管理器"""

import json
import time
from ...storage import get_db
from ...services.kyc_dynamic import kyc_service
from ..manager_protocol import fail_with_meta, normalize_manager_kwargs, ok_with_meta


def _normalize_limit(value, default: int = 50, minimum: int = 1, maximum: int = 200) -> int:
    try:
        limit = int(value)
    except Exception:
        limit = default
    return max(minimum, min(limit, maximum))


def register_user_manager(mcp):
    """注册用户管理器工具"""

    @mcp.tool()
    async def user_manager(action: str, kwargs: str = '{}', **extra_kwargs):
        """用户管理器（统一 action + kwargs 协议）

        Args:
            action (str, required): 操作类型，可选 help/get_profile/update_preferences/list/list_users/assess_kyc
            kwargs: JSON 字符串，不同 action 所需参数:
                - help: 无需额外参数
                - get_profile: user_id(str, optional, 默认 "default")
                - update_preferences: user_id(str, optional), preferences(dict)
                - list / list_users: 无需额外参数
                - assess_kyc: user_id(str, optional, 默认 "default")

        Returns:
            dict: {"success": bool, "data": {...}, "error": str|None}

        Examples:
            # 查看帮助
            user_manager(action="help", kwargs="{}")
            # 获取用户信息
            user_manager(action="get_profile", kwargs='{"user_id":"default"}')
            # 更新偏好设置
            user_manager(action="update_preferences", kwargs='{"preferences":{"theme":"dark","risk_level":"balanced"}}')
            # 列出用户
            user_manager(action="list", kwargs="{}")
            # 动态KYC评估
            user_manager(action="assess_kyc", kwargs='{"user_id":"default"}')
        """
        start_time = time.perf_counter()
        try:
            db = get_db()
            raw_kwargs = dict(extra_kwargs)
            raw_kwargs["kwargs"] = kwargs
            params = normalize_manager_kwargs(raw_kwargs)

            def _ok(data: dict, source_chain=None):
                return ok_with_meta(
                    data,
                    tool_name="user_manager",
                    action=action,
                    started_at=start_time,
                    source_chain=source_chain,
                )

            def _fail(message: str, source_chain=None):
                return fail_with_meta(
                    message,
                    tool_name="user_manager",
                    action=action,
                    started_at=start_time,
                    source_chain=source_chain,
                )

            SUPPORTED_ACTIONS = {
                'get_profile': '获取用户信息',
                'update_preferences': '更新偏好设置',
                'list': '列出用户（别名）',
                'list_users': '列出用户（别名）',
                'assess_kyc': '动态KYC适当性评估',
                'help': '显示帮助信息',
            }

            if action == 'help':
                return _ok({'supported_actions': SUPPORTED_ACTIONS}, source_chain=['user_manager'])
            
            elif action == 'get_profile':
                user_id = params.get('user_id', 'default')
                async with db.acquire() as conn:
                    user = await conn.fetchrow(
                        "SELECT * FROM users WHERE id = $1",
                        user_id
                    )
                    if not user:
                        return _fail('User not found', source_chain=['user_manager', 'db.users'])
                    profile = dict(user)
                
                return _ok(profile, source_chain=['user_manager', 'db.users'])
            
            elif action == 'update_preferences':
                user_id = params.get('user_id', 'default')
                preferences = params.get('preferences', {})
                if not isinstance(preferences, dict):
                    return _fail('preferences 必须为对象', source_chain=['user_manager'])
                
                async with db.acquire() as conn:
                    row = await conn.fetchrow(
                        "SELECT settings FROM users WHERE id = $1",
                        user_id,
                    )
                    if not row:
                        return _fail('User not found', source_chain=['user_manager', 'db.users'])
                    current_settings = {}
                    existing = row.get('settings') if isinstance(row, dict) else row['settings']
                    if existing:
                        if isinstance(existing, dict):
                            current_settings = dict(existing)
                        else:
                            try:
                                current_settings = json.loads(existing)
                            except Exception:
                                current_settings = {}
                    merged_settings = {**current_settings, **preferences}
                    await conn.execute(
                        "UPDATE users SET settings = $1, updated_at = NOW() WHERE id = $2",
                        json.dumps(merged_settings), user_id
                    )
                return _ok(
                    {'user_id': user_id, 'updated': True, 'preferences': merged_settings},
                    source_chain=['user_manager', 'db.users'],
                )
            
            elif action in ['list', 'list_users']:
                limit = _normalize_limit(params.get('limit', 50))
                async with db.acquire() as conn:
                    rows = await conn.fetch(
                        "SELECT id, username, email, created_at FROM users ORDER BY created_at DESC LIMIT $1",
                        limit
                    )
                    users = [dict(row) for row in rows]
                return _ok({'users': users, 'count': len(users)}, source_chain=['user_manager', 'db.users'])

            elif action == 'assess_kyc':
                user_id = params.get('user_id', 'default')
                result = await kyc_service.assess_risk_level(user_id, db)
                # Persist KYC level to users.settings
                async with db.acquire() as conn:
                    row = await conn.fetchrow(
                        "SELECT settings FROM users WHERE id = $1", user_id,
                    )
                    settings = {}
                    if row and row['settings']:
                        settings = row['settings'] if isinstance(row['settings'], dict) else json.loads(row['settings'])
                    settings['kyc_level'] = result['kyc_level']
                    await conn.execute(
                        "UPDATE users SET settings = $1, updated_at = NOW() WHERE id = $2",
                        json.dumps(settings), user_id,
                    )
                return _ok(result, source_chain=['user_manager', 'kyc_service', 'db.users'])

            else:
                return _fail(
                    f'Unknown action: {action}. Supported: {", ".join(SUPPORTED_ACTIONS.keys())}',
                    source_chain=['user_manager'],
                )
        except Exception as e:
            return fail_with_meta(
                str(e),
                tool_name='user_manager',
                action=action,
                started_at=start_time,
                source_chain=['user_manager'],
            )
