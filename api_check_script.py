import subprocess
import json
import os
import sys

BASE = 'http://localhost:5889'

# Fix Windows encoding
sys.stdout.reconfigure(encoding='utf-8')

def curl(path):
    try:
        r = subprocess.run(
            ['curl', '-s', '-w', '\nHTTP_CODE:%{http_code}', f'{BASE}{path}'],
            capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=30
        )
        out = r.stdout.strip().split('HTTP_CODE:')
        body = out[0].strip() if len(out) > 0 else ''
        code = out[1].strip() if len(out) > 1 else '0'
    except Exception as e:
        return {'status': 0, 'data': None, 'raw': f'请求失败: {type(e).__name__}: {e}'}
    try:
        data = json.loads(body) if body else None
    except Exception:
        data = None
    return {'status': int(code), 'data': data, 'raw': body[:3000]}

all_results = {}

# 1. health
h = curl('/health')
all_results['health'] = h
print('=== 1. /health ===')
print(json.dumps(h['data'], indent=2, ensure_ascii=False))

# 2. stock-list
sl = curl('/api/v1/data/stock-list')
all_results['stock_list'] = sl
print('\n=== 2. /api/v1/data/stock-list ===')
print(f'Status: {sl["status"]}, Type: {type(sl["data"])}')
if isinstance(sl['data'], list):
    print(f'Length: {len(sl["data"])}')
    for item in sl['data'][:5]:
        print(json.dumps(item, ensure_ascii=False))
    num_names = 0
    print('\n--- First 20 name check ---')
    for i, item in enumerate(sl['data'][:20]):
        name = item.get('name', '') or ''
        code = item.get('code', item.get('symbol', 'N/A'))
        is_num = bool(name.strip() and all(c.isdigit() for c in name.strip()))
        if is_num: num_names += 1
        print(f'  {i}: code={code}, name={repr(name)}, is_numeric={is_num}')
    print(f'Numeric names in first 20: {num_names}')

# 3. search
sr = curl('/api/v1/stock/search?q=000001')
all_results['stock_search'] = sr
print('\n=== 3. /api/v1/stock/search?q=000001 ===')
print(json.dumps(sr, indent=2, ensure_ascii=False)[:1500])

# 4. watchlist
wl = curl('/api/v1/watchlist/with-quotes')
all_results['watchlist'] = wl
print('\n=== 4. /api/v1/watchlist/with-quotes ===')
print(json.dumps(wl, indent=2, ensure_ascii=False)[:2000])

# 5. ohlcv
oh = curl('/api/v1/quote/000001/ohlcv')
all_results['ohlcv'] = oh
print('\n=== 5. /api/v1/quote/000001/ohlcv ===')
print(json.dumps(oh, indent=2, ensure_ascii=False)[:2000])

# 6. indicators
ind = curl('/api/v1/quote/000001/indicators')
all_results['indicators'] = ind
print('\n=== 6. /api/v1/quote/000001/indicators ===')
print(json.dumps(ind, indent=2, ensure_ascii=False)[:2000])

# 7. patterns
pat = curl('/api/v1/quote/000001/patterns')
all_results['patterns'] = pat
print('\n=== 7. /api/v1/quote/000001/patterns ===')
print(json.dumps(pat, indent=2, ensure_ascii=False)[:2000])

# 8. signal
sig = curl('/api/v1/quote/000001/signal')
all_results['signal'] = sig
print('\n=== 8. /api/v1/quote/000001/signal ===')
print(json.dumps(sig, indent=2, ensure_ascii=False)[:2000])

# 9. resonance
res = curl('/api/v1/quote/000001/resonance')
all_results['resonance'] = res
print('\n=== 9. /api/v1/quote/000001/resonance ===')
print(json.dumps(res, indent=2, ensure_ascii=False)[:2000])

# 10. volume-analysis
vol = curl('/api/v1/quote/000001/volume-analysis')
all_results['volume_analysis'] = vol
print('\n=== 10. /api/v1/quote/000001/volume-analysis ===')
print(json.dumps(vol, indent=2, ensure_ascii=False)[:2000])

# 11. support-resistance
sr2 = curl('/api/v1/quote/000001/support-resistance')
all_results['support_resistance'] = sr2
print('\n=== 11. /api/v1/quote/000001/support-resistance ===')
print(json.dumps(sr2, indent=2, ensure_ascii=False)[:2000])

# 12. market overview
mo = curl('/api/v1/market/overview')
all_results['market_overview'] = mo
print('\n=== 12. /api/v1/market/overview ===')
print(json.dumps(mo, indent=2, ensure_ascii=False)[:2000])

# 13. market sentiment
ms = curl('/api/v1/market/sentiment')
all_results['market_sentiment'] = ms
print('\n=== 13. /api/v1/market/sentiment ===')
print(json.dumps(ms, indent=2, ensure_ascii=False)[:2000])

# 14. market hotspots
mh = curl('/api/v1/market/hotspots')
all_results['market_hotspots'] = mh
print('\n=== 14. /api/v1/market/hotspots ===')
print(json.dumps(mh, indent=2, ensure_ascii=False)[:2000])

# 15. market sectors
ms2 = curl('/api/v1/market/sectors')
all_results['market_sectors'] = ms2
print('\n=== 15. /api/v1/market/sectors ===')
print(json.dumps(ms2, indent=2, ensure_ascii=False)[:2000])

# 16. signals
sigs = curl('/api/v1/signals')
all_results['signals'] = sigs
print('\n=== 16. /api/v1/signals ===')
print(json.dumps(sigs, indent=2, ensure_ascii=False)[:2000])

# 17. backtest strategies
bt = curl('/api/v1/backtest/strategies')
all_results['backtest_strategies'] = bt
print('\n=== 17. /api/v1/backtest/strategies ===')
print(json.dumps(bt, indent=2, ensure_ascii=False)[:2000])

# Save all results
with open('api_check_results.json', 'w', encoding='utf-8') as f:
    json.dump(all_results, f, ensure_ascii=False, indent=2)
print('\n\n=== Results saved to api_check_results.json ===')
