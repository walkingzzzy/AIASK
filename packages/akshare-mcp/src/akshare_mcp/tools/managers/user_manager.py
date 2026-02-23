"""用户管理器"""

import json
from ...storage import get_db
from ...utils import ok, fail
from ...services.kyc_dynamic import kyc_service


def register_user_manager(mcp):
    """注册用户管理器工具"""

    @mcp.tool()
    async def user_manager(action: str, kwargs: str = '{}'):
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
        try:
            db = get_db()

            # Normalize kwargs from JSON string
            if isinstance(kwargs, str):
                try:
                    params = json.loads(kwargs)
                except (json.JSONDecodeError, TypeError):
                    params = {}
            elif isinstance(kwargs, dict):
                params = kwargs
            else:
                params = {}

            SUPPORTED_ACTIONS = {
                'get_profile': '获取用户信息',
                'update_preferences': '更新偏好设置',
                'list': '列出用户（别名）',
                'list_users': '列出用户（别名）',
                'assess_kyc': '动态KYC适当性评估',
                'help': '显示帮助信息',
            }

            if action == 'help':
                return ok({'supported_actions': SUPPORTED_ACTIONS})
            
            elif action == 'get_profile':
                user_id = params.get('user_id', 'default')
                async with db.acquire() as conn:
                    user = await conn.fetchrow(
                        "SELECT * FROM users WHERE id = $1",
                        user_id
                    )
                    if not user:
                        return fail('User not found')
                    profile = dict(user)
                
                return ok(profile)
            
            elif action == 'update_preferences':
                user_id = params.get('user_id', 'default')
                preferences = params.get('preferences', {})
                
                async with db.acquire() as conn:
                    await conn.execute(
                        "UPDATE users SET settings = $1, updated_at = NOW() WHERE id = $2",
                        json.dumps(preferences), user_id
                    )
                return ok({'user_id': user_id, 'updated': True})
            
            elif action in ['list', 'list_users']:
                limit = params.get('limit', 50)
                async with db.acquire() as conn:
                    rows = await conn.fetch(
                        "SELECT id, username, email, created_at FROM users ORDER BY created_at DESC LIMIT $1",
                        limit
                    )
                    users = [dict(row) for row in rows]
                return ok({'users': users, 'count': len(users)})

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
                return ok(result)

            else:
                return fail(f'Unknown action: {action}. Supported: {", ".join(SUPPORTED_ACTIONS.keys())}')
        except Exception as e:
            return fail(str(e))
