# TDX Docs Full Probe Report

- Generated: 2026-05-20T13:50:08.083942
- Markdown files scanned: 180
- Manual/API candidates from docs: 70
- Implemented in local tqcenter.py: 57
- Documented but not implemented in local tqcenter.py: 13
- Probe cases: 130
- Executed: 96; ok: 96; failed: 0; value-present ok: 75
- Status counts: {"executed": 96, "not_implemented_in_sdk": 13, "skipped_missing_env": 1, "skipped_missing_valid_account_handle": 3, "skipped_side_effect": 17}

## Implemented API Surface

`cancel_order_stock`, `clear_sector`, `create_sector`, `delete_sector`, `download_file`, `exec_to_tdx`, `formula_exp`, `formula_format_data`, `formula_get_data`, `formula_process_mul_xg`, `formula_process_mul_zb`, `formula_set_data`, `formula_set_data_info`, `formula_xg`, `formula_zb`, `get_bkjy_value`, `get_bkjy_value_by_date`, `get_divid_factors`, `get_financial_data`, `get_financial_data_by_date`, `get_gb_info`, `get_gp_one_data`, `get_gpjy_value`, `get_gpjy_value_by_date`, `get_ipo_info`, `get_kzz_info`, `get_market_data`, `get_market_snapshot`, `get_more_info`, `get_relation`, `get_scjy_value`, `get_scjy_value_by_date`, `get_sector_list`, `get_stock_info`, `get_stock_list`, `get_stock_list_in_sector`, `get_subscribe_hq_stock_list`, `get_trackzs_etf_info`, `get_trading_dates`, `get_user_sector`, `initialize`, `order_stock`, `print_to_tdx`, `query_stock_asset`, `query_stock_orders`, `query_stock_positions`, `refresh_cache`, `refresh_kline`, `rename_sector`, `send_bt_data`, `send_file`, `send_message`, `send_user_block`, `send_warn`, `stock_account`, `subscribe_hq`, `unsubscribe_hq`

## Documented But Missing In Local SDK

`get_benchmark_data`, `get_full_tick`, `get_gb_info_by_date`, `get_real_time_data`, `get_report_data`, `get_valid_stock_codes`, `print_exc`, `send_msg`, `send_trade_warn`, `send_warnings_for_stocks`, `subscribe_stocks`, `unsubscribe_single_stock`, `unsubscribe_stocks`

## Field Enums From Docs

- `FN`: 438 fields, ['FN1', 'FN2', 'FN3', 'FN4', 'FN5'] ... ['FN580', 'FN581', 'FN582', 'FN583', 'FN584']
- `GP`: 46 fields, ['GP01', 'GP02', 'GP03', 'GP04', 'GP05'] ... ['GP42', 'GP43', 'GP44', 'GP45', 'GP46']
- `BK`: 15 fields, ['BK5', 'BK6', 'BK7', 'BK8', 'BK9'] ... ['BK15', 'BK16', 'BK17', 'BK18', 'BK19']
- `SC`: 42 fields, ['SC01', 'SC02', 'SC03', 'SC04', 'SC05'] ... ['SC38', 'SC39', 'SC40', 'SC41', 'SC42']
- `GO`: 47 fields, ['GO1', 'GO2', 'GO3', 'GO4', 'GO5'] ... ['GO43', 'GO44', 'GO45', 'GO46', 'GO47']

## Stock List Counts

- `0_user_watchlist` market `0`: count=1, first=[{"Code": "999999.SH", "Name": "上证指数"}]
- `1_positions` market `1`: count=0, first=[]
- `5_all_a` market `5`: count=5525, first=[{"Code": "000001.SZ", "Name": "平安银行"}, {"Code": "000002.SZ", "Name": "万 科Ａ"}]
- `6_sh_index_components` market `6`: count=2213, first=[{"Code": "600000.SH", "Name": "浦发银行"}, {"Code": "600004.SH", "Name": "白云机场"}]
- `7_sh_main` market `7`: count=1705, first=[{"Code": "600000.SH", "Name": "浦发银行"}, {"Code": "600004.SH", "Name": "白云机场"}]
- `8_sz_main` market `8`: count=1495, first=[{"Code": "000001.SZ", "Name": "平安银行"}, {"Code": "000002.SZ", "Name": "万 科Ａ"}]
- `9_key_indexes` market `9`: count=100, first=[{"Code": "999999.SH", "Name": "上证指数"}, {"Code": "399001.SZ", "Name": "深证成指"}]
- `10_all_block_indexes` market `10`: count=586, first=[{"Code": "880081.SH", "Name": "轮动趋势"}, {"Code": "880082.SH", "Name": "板块趋势"}]
- `11_default_industry` market `11`: count=127, first=[{"Code": "881002.SH", "Name": "煤炭开采"}, {"Code": "881005.SH", "Name": "焦炭加工"}]
- `12_concept_blocks` market `12`: count=269, first=[{"Code": "880501.SH", "Name": "含H股"}, {"Code": "880502.SH", "Name": "含B股"}]
- `13_style_blocks` market `13`: count=158, first=[{"Code": "880081.SH", "Name": "轮动趋势"}, {"Code": "880082.SH", "Name": "板块趋势"}]
- `14_region_blocks` market `14`: count=32, first=[{"Code": "880201.SH", "Name": "黑龙江"}, {"Code": "880202.SH", "Name": "新疆板块"}]
- `15_industry_and_concept` market `15`: count=396, first=[{"Code": "880501.SH", "Name": "含H股"}, {"Code": "880502.SH", "Name": "含B股"}]
- `16_research_l1` market `16`: count=30, first=[{"Code": "881001.SH", "Name": "煤炭"}, {"Code": "881006.SH", "Name": "石油"}]
- `17_research_l2` market `17`: count=127, first=[{"Code": "881002.SH", "Name": "煤炭开采"}, {"Code": "881005.SH", "Name": "焦炭加工"}]
- `18_research_l3` market `18`: count=344, first=[{"Code": "881003.SH", "Name": "动力煤"}, {"Code": "881004.SH", "Name": "炼焦煤"}]
- `21_with_h` market `21`: count=189, first=[{"Code": "000002.SZ", "Name": "万 科Ａ"}, {"Code": "000039.SZ", "Name": "中集集团"}]
- `22_with_cb` market `22`: count=333, first=[{"Code": "000301.SZ", "Name": "东方盛虹"}, {"Code": "000401.SZ", "Name": "金隅冀东"}]
- `23_hs300` market `23`: count=300, first=[{"Code": "000001.SZ", "Name": "平安银行"}, {"Code": "000002.SZ", "Name": "万 科Ａ"}]
- `24_zz500` market `24`: count=500, first=[{"Code": "000009.SZ", "Name": "中国宝安"}, {"Code": "000021.SZ", "Name": "深科技"}]
- `25_zz1000` market `25`: count=1000, first=[{"Code": "000012.SZ", "Name": "南 玻Ａ"}, {"Code": "000019.SZ", "Name": "深粮控股"}]
- `26_guozheng2000` market `26`: count=2000, first=[{"Code": "000012.SZ", "Name": "南 玻Ａ"}, {"Code": "000019.SZ", "Name": "深粮控股"}]
- `27_zz2000` market `27`: count=2000, first=[{"Code": "000011.SZ", "Name": "深物业A"}, {"Code": "000014.SZ", "Name": "沙河股份"}]
- `28_zz_a500` market `28`: count=500, first=[{"Code": "000001.SZ", "Name": "平安银行"}, {"Code": "000002.SZ", "Name": "万 科Ａ"}]
- `30_reits` market `30`: count=87, first=[{"Code": "180101.SZ", "Name": "博时蛇口产园REIT"}, {"Code": "180102.SZ", "Name": "华夏合肥高新REIT"}]
- `31_etf` market `31`: count=1578, first=[{"Code": "159001.SZ", "Name": "货币ETF易方达"}, {"Code": "159003.SZ", "Name": "招商快线ETF"}]
- `32_convertible_bond` market `32`: count=344, first=[{"Code": "123054.SZ", "Name": "思特转债"}, {"Code": "123059.SZ", "Name": "银信转债"}]
- `33_lof` market `33`: count=465, first=[{"Code": "160105.SZ", "Name": "南方积配LOF"}, {"Code": "160106.SZ", "Name": "南方高增LOF"}]
- `34_tradeable_fund` market `34`: count=2130, first=[{"Code": "159001.SZ", "Name": "货币ETF易方达"}, {"Code": "159003.SZ", "Name": "招商快线ETF"}]
- `35_hs_fund` market `35`: count=2343, first=[{"Code": "159001.SZ", "Name": "货币ETF易方达"}, {"Code": "159003.SZ", "Name": "招商快线ETF"}]
- `36_t0_fund` market `36`: count=376, first=[{"Code": "159001.SZ", "Name": "货币ETF易方达"}, {"Code": "159003.SZ", "Name": "招商快线ETF"}]
- `49_financial_enterprise` market `49`: count=101, first=[{"Code": "000001.SZ", "Name": "平安银行"}, {"Code": "000166.SZ", "Name": "申万宏源"}]
- `50_hs_a` market `50`: count=5208, first=[{"Code": "000001.SZ", "Name": "平安银行"}, {"Code": "000002.SZ", "Name": "万 科Ａ"}]
- `51_chinext` market `51`: count=1398, first=[{"Code": "300001.SZ", "Name": "特锐德"}, {"Code": "300002.SZ", "Name": "神州泰岳"}]
- `52_star` market `52`: count=610, first=[{"Code": "688001.SH", "Name": "华兴源创"}, {"Code": "688002.SH", "Name": "睿创微纳"}]
- `53_bj` market `53`: count=317, first=[{"Code": "920000.BJ", "Name": "安徽凤凰"}, {"Code": "920001.BJ", "Name": "纬达光电"}]
- `91_etf_tracked_index` market `91`: count=0, first=[]
- `92_domestic_futures_main` market `92`: count=0, first=[]
- `101_domestic_futures` market `101`: count=0, first=[]
- `102_hk` market `102`: count=0, first=[]
- `103_us` market `103`: count=0, first=[]

## Kline Period Coverage

- `1m`: type=dict, len=8, keys=['Close', 'Volume', 'Open', 'Low', 'ForwardFactor', 'VolInStock', 'High', 'Amount'], sample_shape=[5, 1]
- `5m`: type=dict, len=8, keys=['Close', 'Volume', 'Open', 'Low', 'ForwardFactor', 'VolInStock', 'High', 'Amount'], sample_shape=[5, 1]
- `15m`: type=dict, len=8, keys=['Close', 'Volume', 'Open', 'Low', 'ForwardFactor', 'VolInStock', 'High', 'Amount'], sample_shape=[5, 1]
- `30m`: type=dict, len=8, keys=['Close', 'Volume', 'Open', 'Low', 'ForwardFactor', 'VolInStock', 'High', 'Amount'], sample_shape=[5, 1]
- `1h`: type=dict, len=8, keys=['Close', 'Volume', 'Open', 'Low', 'ForwardFactor', 'VolInStock', 'High', 'Amount'], sample_shape=[5, 1]
- `1d`: type=dict, len=8, keys=['Close', 'Volume', 'Open', 'Low', 'ForwardFactor', 'VolInStock', 'High', 'Amount'], sample_shape=[5, 1]
- `1w`: type=dict, len=8, keys=['Close', 'Volume', 'Open', 'Low', 'ForwardFactor', 'VolInStock', 'High', 'Amount'], sample_shape=[5, 1]
- `1mon`: type=dict, len=8, keys=['Close', 'Volume', 'Open', 'Low', 'ForwardFactor', 'VolInStock', 'High', 'Amount'], sample_shape=[5, 1]
- `1q`: type=dict, len=8, keys=['Close', 'Volume', 'Open', 'Low', 'ForwardFactor', 'VolInStock', 'High', 'Amount'], sample_shape=[5, 1]
- `1y`: type=dict, len=8, keys=['Close', 'Volume', 'Open', 'Low', 'ForwardFactor', 'VolInStock', 'High', 'Amount'], sample_shape=[5, 1]
- `tick`: type=dict, len=2, keys=['error', 'msg'], sample_shape=None

## Financial/Feature Field Availability

- `FN_by_date`: non_empty_count=0, fields=[]
- `FN_history`: non_empty_count=0, fields=[]
- `GO`: non_empty_count=47, fields=['GO1', 'GO2', 'GO3', 'GO4', 'GO5', 'GO6', 'GO7', 'GO8', 'GO9', 'GO10', 'GO11', 'GO12', 'GO13', 'GO14', 'GO15', 'GO16', 'GO17', 'GO18', 'GO19', 'GO20', 'GO21', 'GO22', 'GO23', 'GO24', 'GO25', 'GO26', 'GO27', 'GO28', 'GO29', 'GO30']
- `GP_history`: non_empty_count=2, fields=['GP25', 'GP36']
- `GP_by_date`: non_empty_count=0, fields=[]
- `BK_history`: non_empty_count=4, fields=['BK9', 'BK12', 'BK13', 'BK17']
- `BK_by_date`: non_empty_count=0, fields=[]
- `SC_history`: non_empty_count=2, fields=['SC25', 'SC36']
- `SC_by_date`: non_empty_count=0, fields=[]

## Failed Executed Cases

- None

## Skipped Or Non-Executable Cases

- `market_data/get_gb_info_by_date`: not_implemented_in_sdk - Documented in Markdown but local tqcenter.py has get_gb_info only.
- `trading_read/stock_account`: skipped_missing_env - Set TDX_PROBE_ACCOUNT to test trading read APIs without exposing account ids in this script.
- `trading_read/query_stock_asset`: skipped_missing_valid_account_handle - Requires valid stock_account handle; set TDX_PROBE_ACCOUNT.
- `trading_read/query_stock_orders`: skipped_missing_valid_account_handle - Requires valid stock_account handle; set TDX_PROBE_ACCOUNT.
- `trading_read/query_stock_positions`: skipped_missing_valid_account_handle - Requires valid stock_account handle; set TDX_PROBE_ACCOUNT.
- `side_effect_api/cancel_order_stock`: skipped_side_effect - trading side effect
- `side_effect_api/clear_sector`: skipped_side_effect - custom sector write
- `side_effect_api/create_sector`: skipped_side_effect - custom sector write
- `side_effect_api/delete_sector`: skipped_side_effect - custom sector write
- `side_effect_api/exec_to_tdx`: skipped_side_effect - client command side effect
- `side_effect_api/order_stock`: skipped_side_effect - trading side effect
- `side_effect_api/print_to_tdx`: skipped_side_effect - client UI output side effect
- `side_effect_api/refresh_cache`: skipped_side_effect - client cache/download side effect
- `side_effect_api/refresh_kline`: skipped_side_effect - client cache/download side effect
- `side_effect_api/rename_sector`: skipped_side_effect - custom sector write
- `side_effect_api/send_bt_data`: skipped_side_effect - client UI output side effect
- `side_effect_api/send_file`: skipped_side_effect - client UI output side effect
- `side_effect_api/send_message`: skipped_side_effect - client UI output side effect
- `side_effect_api/send_user_block`: skipped_side_effect - custom sector write
- `side_effect_api/send_warn`: skipped_side_effect - client UI output side effect
- `side_effect_api/subscribe_hq`: skipped_side_effect - real-time subscription side effect
- `side_effect_api/unsubscribe_hq`: skipped_side_effect - subscription side effect
- `documented_only/get_benchmark_data`: not_implemented_in_sdk - Documented or mentioned in Markdown, but absent from local tqcenter.py.
- `documented_only/get_full_tick`: not_implemented_in_sdk - Documented or mentioned in Markdown, but absent from local tqcenter.py.
- `documented_only/get_real_time_data`: not_implemented_in_sdk - Documented or mentioned in Markdown, but absent from local tqcenter.py.
- `documented_only/get_report_data`: not_implemented_in_sdk - Documented or mentioned in Markdown, but absent from local tqcenter.py.
- `documented_only/get_valid_stock_codes`: not_implemented_in_sdk - Documented or mentioned in Markdown, but absent from local tqcenter.py.
- `documented_only/print_exc`: not_implemented_in_sdk - Documented or mentioned in Markdown, but absent from local tqcenter.py.
- `documented_only/send_msg`: not_implemented_in_sdk - Documented or mentioned in Markdown, but absent from local tqcenter.py.
- `documented_only/send_trade_warn`: not_implemented_in_sdk - Documented or mentioned in Markdown, but absent from local tqcenter.py.
- `documented_only/send_warnings_for_stocks`: not_implemented_in_sdk - Documented or mentioned in Markdown, but absent from local tqcenter.py.
- `documented_only/subscribe_stocks`: not_implemented_in_sdk - Documented or mentioned in Markdown, but absent from local tqcenter.py.
- `documented_only/unsubscribe_single_stock`: not_implemented_in_sdk - Documented or mentioned in Markdown, but absent from local tqcenter.py.
- `documented_only/unsubscribe_stocks`: not_implemented_in_sdk - Documented or mentioned in Markdown, but absent from local tqcenter.py.
