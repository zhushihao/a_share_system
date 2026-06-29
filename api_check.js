const http = require('http');
const { execSync } = require('child_process');
const fs = require('fs');

const BASE = 'http://localhost:5889';
const results = {};

function callApi(path) {
  return new Promise((resolve) => {
    const url = BASE + path;
    const start = Date.now();
    const req = http.get(url, (res) => {
      let data = '';
      res.on('data', chunk => data += chunk);
      res.on('end', () => {
        const time = (Date.now() - start) / 1000;
        resolve({ code: res.statusCode, body: data, time, size: Buffer.byteLength(data) });
      });
    });
    req.on('error', (err) => resolve({ code: 'ERR', body: err.message, time: 0, size: 0 }));
    req.setTimeout(30000, () => { req.destroy(); resolve({ code: 'TIMEOUT', body: '', time: 30, size: 0 }); });
  });
}

async function main() {
  console.log('=== QUANT WORKBENCH API CHECK ===');
  const today = new Date().toISOString().split('T')[0];
  
  // 1. health
  let r = await callApi('/health');
  console.log('\n--- 1. /health ---');
  console.log(`HTTP: ${r.code}, Time: ${r.time.toFixed(3)}s, Size: ${r.size}b`);
  if (r.code === 200) {
    const d = JSON.parse(r.body);
    console.log(`  status: ${d.status}`);
    console.log(`  version: ${d.version}`);
    console.log(`  tdx_dir: ${d.checks?.tdx_dir}`);
    console.log(`  database: ${d.checks?.database}`);
    console.log(`  offline: ${d.checks?.data_sources?.offline_available}`);
    console.log(`  realtime: ${d.checks?.data_sources?.realtime_available}`);
  }
  results.health = { code: r.code, time: r.time, size: r.size };

  // 2. stock-list
  r = await callApi('/api/v1/data/stock-list?limit=20&offset=0');
  console.log('\n--- 2. /api/v1/data/stock-list ---');
  console.log(`HTTP: ${r.code}, Time: ${r.time.toFixed(3)}s, Size: ${r.size}b`);
  if (r.code === 200) {
    const d = JSON.parse(r.body);
    const items = d.items || [];
    console.log(`  items_count: ${items.length}`);
    console.log(`  total: ${d.total}`);
    const numericNames = items.filter(i => /^\d+$/.test(String(i.name || ''))).length;
    console.log(`  numeric_names: ${numericNames}`);
    console.log('  sample_names:');
    items.slice(0, 10).forEach(i => {
      const isNum = /^\d+$/.test(String(i.name || '')) ? 'NUM' : 'OK';
      console.log(`    ${i.symbol} -> ${i.name} [${isNum}]`);
    });
  }
  results.stock_list = { code: r.code, time: r.time, size: r.size };

  // 3. stock search
  r = await callApi('/api/v1/stock/search?q=000001');
  console.log('\n--- 3. /api/v1/stock/search?q=000001 ---');
  console.log(`HTTP: ${r.code}, Time: ${r.time.toFixed(3)}s`);
  if (r.code === 200) {
    const d = JSON.parse(r.body);
    console.log(`  result_count: ${d.length}`);
    d.slice(0, 3).forEach(i => console.log(`    ${i.symbol}: ${i.name}`));
  }
  results.stock_search = { code: r.code, time: r.time };

  // 4. watchlist with quotes
  r = await callApi('/api/v1/watchlist/with-quotes');
  console.log('\n--- 4. /api/v1/watchlist/with-quotes ---');
  console.log(`HTTP: ${r.code}, Time: ${r.time.toFixed(3)}s, Size: ${r.size}b`);
  if (r.code === 200) {
    const d = JSON.parse(r.body);
    const items = d.items || [];
    console.log(`  watchlist_count: ${items.length}`);
    const nullCount = items.filter(i => i.quote?.name === null).length;
    console.log(`  quote_name_null: ${nullCount}`);
    items.slice(0, 5).forEach(i => {
      console.log(`    ${i.symbol}: name=${i.name}, quote.name=${i.quote?.name}`);
    });
  }
  results.watchlist = { code: r.code, time: r.time, size: r.size };

  // 5. ohlcv
  r = await callApi('/api/v1/quote/000001.SZ/ohlcv');
  console.log('\n--- 5. /api/v1/quote/000001.SZ/ohlcv ---');
  console.log(`HTTP: ${r.code}, Time: ${r.time.toFixed(3)}s, Size: ${r.size}b`);
  if (r.code === 200) {
    const d = JSON.parse(r.body);
    const data = d.data || [];
    console.log(`  data_count: ${data.length}`);
    if (data.length > 0) {
      data.slice(0, 3).forEach(i => console.log(`    ${i.date}: close=${i.close}, is_filled=${i.is_filled}`));
      const validPrices = data.filter(i => (i.close || 0) > 0).length;
      console.log(`  prices>0: ${validPrices}/${data.length}`);
      const dates = data.map(i => i.date).filter(Boolean);
      if (dates.length > 0) console.log(`  date_range: ${dates.reduce((a,b) => a < b ? a : b)} ~ ${dates.reduce((a,b) => a > b ? a : b)}`);
    }
  }
  results.ohlcv = { code: r.code, time: r.time, size: r.size };

  // 6. indicators
  r = await callApi('/api/v1/quote/000001.SZ/indicators');
  console.log('\n--- 6. /api/v1/quote/000001.SZ/indicators ---');
  console.log(`HTTP: ${r.code}, Time: ${r.time.toFixed(3)}s, Size: ${r.size}b`);
  if (r.code === 200) {
    const d = JSON.parse(r.body);
    const keys = Object.keys(d).filter(k => k !== 'labels');
    console.log(`  data_keys: ${keys.slice(0, 10)}`);
    console.log(`  has_labels: ${'labels' in d}`);
    if (d.labels) {
      console.log(`  labels_count: ${Object.keys(d.labels).length}`);
      const missing = keys.filter(k => !(k in d.labels));
      console.log(`  missing_labels: ${missing.slice(0, 5)}`);
    }
  }
  results.indicators = { code: r.code, time: r.time, size: r.size };

  // 7. patterns
  r = await callApi('/api/v1/quote/000001.SZ/patterns');
  console.log('\n--- 7. /api/v1/quote/000001.SZ/patterns ---');
  console.log(`HTTP: ${r.code}, Time: ${r.time.toFixed(3)}s, Size: ${r.size}b`);
  if (r.code === 200) {
    const d = JSON.parse(r.body);
    const patterns = d.patterns || [];
    console.log(`  patterns_count: ${patterns.length}`);
    if (patterns.length > 0) {
      patterns.slice(0, 3).forEach(p => {
        console.log(`    pattern=${p.pattern}, name=${p.name}, display_name=${p.display_name}`);
      });
      const hasDisplay = patterns.filter(p => p.display_name).length;
      console.log(`  has_display_name: ${hasDisplay}/${patterns.length}`);
    }
  }
  results.patterns = { code: r.code, time: r.time, size: r.size };

  // 8. signal
  r = await callApi('/api/v1/quote/000001.SZ/signal');
  console.log('\n--- 8. /api/v1/quote/000001.SZ/signal ---');
  console.log(`HTTP: ${r.code}, Time: ${r.time.toFixed(3)}s, Size: ${r.size}b`);
  if (r.code === 200) {
    const d = JSON.parse(r.body);
    const signals = d.signals || [];
    console.log(`  signals_count: ${signals.length}`);
    if (signals.length > 0) {
      signals.slice(0, 3).forEach(s => {
        console.log(`    type=${s.signal_type}, strategy=${s.strategy_name}, date=${s.date}`);
      });
    }
  }
  results.signal = { code: r.code, time: r.time, size: r.size };

  // 9. resonance
  r = await callApi('/api/v1/quote/000001.SZ/resonance');
  console.log('\n--- 9. /api/v1/quote/000001.SZ/resonance ---');
  console.log(`HTTP: ${r.code}, Time: ${r.time.toFixed(3)}s`);
  results.resonance = { code: r.code, time: r.time };

  // 10. volume-analysis
  r = await callApi('/api/v1/quote/000001.SZ/volume-analysis');
  console.log('\n--- 10. /api/v1/quote/000001.SZ/volume-analysis ---');
  console.log(`HTTP: ${r.code}, Time: ${r.time.toFixed(3)}s`);
  results.volume_analysis = { code: r.code, time: r.time };

  // 11. support-resistance
  r = await callApi('/api/v1/quote/000001.SZ/support-resistance');
  console.log('\n--- 11. /api/v1/quote/000001.SZ/support-resistance ---');
  console.log(`HTTP: ${r.code}, Time: ${r.time.toFixed(3)}s`);
  results.support_resistance = { code: r.code, time: r.time };

  // 12. market overview
  r = await callApi('/api/v1/market/overview');
  console.log('\n--- 12. /api/v1/market/overview ---');
  console.log(`HTTP: ${r.code}, Time: ${r.time.toFixed(3)}s, Size: ${r.size}b`);
  if (r.code === 200) {
    const d = JSON.parse(r.body);
    console.log(`  keys: ${Object.keys(d).join(', ')}`);
  }
  results.market_overview = { code: r.code, time: r.time, size: r.size };

  // 13. market sentiment
  r = await callApi('/api/v1/market/sentiment');
  console.log('\n--- 13. /api/v1/market/sentiment ---');
  console.log(`HTTP: ${r.code}, Time: ${r.time.toFixed(3)}s, Size: ${r.size}b`);
  if (r.code === 200) {
    const d = JSON.parse(r.body);
    console.log(`  source: ${d.source}`);
    console.log(`  up_down_ratio: ${d.up_down_ratio}`);
    console.log(`  limit_up: ${d.limit_up}`);
    console.log(`  limit_down: ${d.limit_down}`);
  }
  results.market_sentiment = { code: r.code, time: r.time, size: r.size };

  // 14. market hotspots
  r = await callApi('/api/v1/market/hotspots');
  console.log('\n--- 14. /api/v1/market/hotspots ---');
  console.log(`HTTP: ${r.code}, Time: ${r.time.toFixed(3)}s, Size: ${r.size}b`);
  if (r.code === 200) {
    const d = JSON.parse(r.body);
    const hotspots = d.hotspots || [];
    console.log(`  hotspots_count: ${hotspots.length}`);
  }
  results.market_hotspots = { code: r.code, time: r.time, size: r.size };

  // 15. market sectors
  r = await callApi('/api/v1/market/sectors');
  console.log('\n--- 15. /api/v1/market/sectors ---');
  console.log(`HTTP: ${r.code}, Time: ${r.time.toFixed(3)}s, Size: ${r.size}b`);
  if (r.code === 200) {
    const d = JSON.parse(r.body);
    const sectors = d.sectors || [];
    console.log(`  sectors_count: ${sectors.length}`);
    if (sectors.length > 0) {
      const stockCounts = sectors.map(s => s.stock_count || 0);
      const allZero = stockCounts.every(c => c === 0);
      console.log(`  stock_count_all_zero: ${allZero}`);
      sectors.slice(0, 3).forEach(s => console.log(`    ${s.name}: stock_count=${s.stock_count}`));
    }
  }
  results.market_sectors = { code: r.code, time: r.time, size: r.size };

  // 16. signals
  r = await callApi('/api/v1/signals');
  console.log('\n--- 16. /api/v1/signals ---');
  console.log(`HTTP: ${r.code}, Time: ${r.time.toFixed(3)}s, Size: ${r.size}b`);
  if (r.code === 200) {
    const d = JSON.parse(r.body);
    const signals = d.signals || [];
    console.log(`  signals_count: ${signals.length}`);
    if (signals.length > 0) {
      signals.slice(0, 3).forEach(s => {
        console.log(`    ${s.symbol}: type=${s.signal_type}, strategy=${s.strategy}, date=${s.date}`);
      });
      const dates = signals.map(s => s.date).filter(Boolean);
      if (dates.length > 0) {
        const latest = dates.reduce((a, b) => a > b ? a : b);
        console.log(`  latest_date: ${latest}`);
        const latestDt = new Date(latest + 'T00:00:00');
        const todayDt = new Date(today + 'T00:00:00');
        const daysDiff = Math.floor((todayDt - latestDt) / (1000 * 60 * 60 * 24));
        console.log(`  days_behind: ${daysDiff}`);
      }
    }
  }
  results.signals = { code: r.code, time: r.time, size: r.size };

  // 17. backtest strategies
  r = await callApi('/api/v1/backtest/strategies');
  console.log('\n--- 17. /api/v1/backtest/strategies ---');
  console.log(`HTTP: ${r.code}, Time: ${r.time.toFixed(3)}s`);
  results.backtest_strategies = { code: r.code, time: r.time };

  // 18. f10 routes
  console.log('\n--- 18. F10 Routes ---');
  for (const path of ['/api/v1/f10/000001.SZ', '/api/v1/f10/000001.SZ/profile', '/api/v1/f10/000001.SZ/finance']) {
    r = await callApi(path);
    console.log(`  ${path}: HTTP ${r.code}`);
    results['f10_' + path.split('/').pop()] = { code: r.code, time: r.time };
  }

  console.log('\n=== API CHECK COMPLETE ===');
  
  // Save results
  fs.writeFileSync('api_check_results.json', JSON.stringify(results, null, 2));
  console.log('Results saved to api_check_results.json');
}

main().catch(console.error);
