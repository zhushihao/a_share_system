const http = require('http');
const fs = require('fs');
const path = require('path');

const apis = [
    { method: 'GET', url: 'http://localhost:5889/health', name: 'health' },
    { method: 'GET', url: 'http://localhost:5889/api/v1/data/stock-list?limit=20', name: 'stock-list' },
    { method: 'GET', url: 'http://localhost:5889/api/v1/stock/search?q=000001', name: 'stock-search' },
    { method: 'GET', url: 'http://localhost:5889/api/v1/watchlist/with-quotes', name: 'watchlist-with-quotes' },
    { method: 'GET', url: 'http://localhost:5889/api/v1/quote/000001/ohlcv?limit=10', name: 'quote-ohlcv' },
    { method: 'GET', url: 'http://localhost:5889/api/v1/quote/000001/indicators?limit=10', name: 'quote-indicators' },
    { method: 'GET', url: 'http://localhost:5889/api/v1/quote/000001/patterns?limit=10', name: 'quote-patterns' },
    { method: 'GET', url: 'http://localhost:5889/api/v1/quote/000001/signal', name: 'quote-signal' },
    { method: 'GET', url: 'http://localhost:5889/api/v1/quote/000001/resonance', name: 'quote-resonance' },
    { method: 'GET', url: 'http://localhost:5889/api/v1/quote/000001/volume-analysis', name: 'quote-volume-analysis' },
    { method: 'GET', url: 'http://localhost:5889/api/v1/quote/000001/support-resistance', name: 'quote-support-resistance' },
    { method: 'GET', url: 'http://localhost:5889/api/v1/market/overview', name: 'market-overview' },
    { method: 'GET', url: 'http://localhost:5889/api/v1/market/sentiment', name: 'market-sentiment' },
    { method: 'GET', url: 'http://localhost:5889/api/v1/market/hotspots?limit=10', name: 'market-hotspots' },
    { method: 'GET', url: 'http://localhost:5889/api/v1/market/sectors', name: 'market-sectors' },
    { method: 'GET', url: 'http://localhost:5889/api/v1/signals?limit=20', name: 'signals' },
    { method: 'GET', url: 'http://localhost:5889/api/v1/backtest/strategies', name: 'backtest-strategies' },
    { method: 'GET', url: 'http://localhost:5889/api/v1/f10/000001', name: 'f10-000001' },
    { method: 'GET', url: 'http://localhost:5889/api/v1/f10/000001/profile', name: 'f10-profile' },
    { method: 'GET', url: 'http://localhost:5889/api/v1/f10/000001/finance', name: 'f10-finance' }
];

function hasChinese(text) {
    if (!text) return false;
    for (const ch of String(text)) {
        const code = ch.charCodeAt(0);
        if (code >= 0x4E00 && code <= 0x9FFF) return true;
    }
    return false;
}

function callApi(api) {
    return new Promise((resolve) => {
        const start = Date.now();
        const req = http.get(api.url, { timeout: 15000 }, (res) => {
            let data = '';
            res.on('data', chunk => { data += chunk; });
            res.on('end', () => {
                const elapsed = (Date.now() - start) / 1000;
                const size = Buffer.byteLength(data, 'utf8');
                let json = null;
                try { json = JSON.parse(data); } catch (e) { json = null; }
                resolve({
                    name: api.name,
                    url: api.url,
                    method: api.method,
                    status_code: res.statusCode,
                    response_time_sec: Math.round(elapsed * 1000) / 1000,
                    response_size_bytes: size,
                    error: null,
                    checks: runChecks(api.name, json, res.statusCode)
                });
            });
        });
        req.on('error', (err) => {
            resolve({
                name: api.name,
                url: api.url,
                method: api.method,
                status_code: null,
                response_time_sec: null,
                response_size_bytes: null,
                error: err.message,
                checks: {}
            });
        });
        req.on('timeout', () => {
            req.destroy();
            resolve({
                name: api.name,
                url: api.url,
                method: api.method,
                status_code: null,
                response_time_sec: null,
                response_size_bytes: null,
                error: 'TIMEOUT',
                checks: {}
            });
        });
    });
}

function runChecks(name, data, statusCode) {
    if (name === 'stock-list') {
        if (Array.isArray(data) && data.length > 0) {
            let checked = 0, chineseCount = 0;
            const samples = [];
            for (let i = 0; i < Math.min(20, data.length); i++) {
                const item = data[i];
                const n = item && item.name ? item.name : null;
                if (n) {
                    checked++;
                    if (hasChinese(n)) chineseCount++;
                    if (samples.length < 5) samples.push(n);
                }
            }
            return { total_checked: checked, chinese_name_count: chineseCount, all_chinese: checked > 0 && chineseCount === checked, sample_names: samples };
        }
        return { note: 'empty or invalid data' };
    }
    if (name === 'watchlist-with-quotes') {
        let nullCount = 0, total = 0;
        const samples = [];
        if (Array.isArray(data)) {
            for (const item of data) {
                const quote = item && item.quote ? item.quote : null;
                const n = quote && quote.name !== undefined ? quote.name : null;
                total++;
                if (n === null || n === undefined) nullCount++;
                if (samples.length < 5) samples.push(n);
            }
        }
        return { total_items: total, null_name_count: nullCount, all_have_name: nullCount === 0 && total > 0, sample_names: samples };
    }
    if (name === 'quote-indicators') {
        const hasLabels = data && typeof data === 'object' && !Array.isArray(data) && 'labels' in data;
        const keys = data && typeof data === 'object' && !Array.isArray(data) ? Object.keys(data) : null;
        return { has_labels_field: hasLabels, keys: keys };
    }
    if (name === 'quote-patterns') {
        const hasDN = Array.isArray(data) && data.length > 0 && data[0] && typeof data[0] === 'object' && 'display_name' in data[0];
        const firstKeys = Array.isArray(data) && data.length > 0 && data[0] && typeof data[0] === 'object' ? Object.keys(data[0]) : null;
        return { has_display_name_field: hasDN, first_item_keys: firstKeys };
    }
    if (name === 'market-sentiment') {
        const hasSource = data && typeof data === 'object' && !Array.isArray(data) && 'source' in data;
        const sourceVal = hasSource ? data.source : null;
        return { source_value: sourceVal, has_source_field: hasSource };
    }
    if (name === 'market-hotspots') {
        let count = 0;
        if (Array.isArray(data)) count = data.length;
        else if (data && typeof data === 'object' && Array.isArray(data.data)) count = data.data.length;
        return { returned_count: count, limit: 10 };
    }
    if (name === 'market-sectors') {
        let zeroCount = 0, total = 0;
        if (Array.isArray(data)) {
            for (const item of data) {
                if (item && typeof item === 'object') {
                    total++;
                    const sc = item.stock_count !== undefined ? item.stock_count : -1;
                    if (sc === 0 || sc === '0') zeroCount++;
                }
            }
        }
        return { total_sectors: total, zero_stock_count: zeroCount, all_have_stocks: zeroCount === 0 && total > 0 };
    }
    if (name === 'signals') {
        if (Array.isArray(data) && data.length > 0 && data[0] && typeof data[0] === 'object') {
            const d0 = data[0];
            const dateStr = d0.date || d0.trade_date || d0.datetime || null;
            let days = null;
            if (dateStr) {
                try {
                    const ds = String(dateStr).substring(0, 10);
                    const d = new Date(ds);
                    if (!isNaN(d.getTime())) {
                        const now = new Date();
                        days = Math.floor((now - d) / (1000 * 60 * 60 * 24));
                    }
                } catch (e) {}
            }
            return { latest_date: dateStr, days_from_today: days };
        }
        return { note: 'no data' };
    }
    if (name.startsWith('f10')) {
        return { is_404: statusCode === 404, functional: statusCode !== 404 };
    }
    return {};
}

async function main() {
    const results = [];
    const summary = { total: apis.length, passed: 0, failed: 0, errors: 0, check_time: new Date().toISOString().replace('T', ' ').substring(0, 19), target: 'localhost:5889' };

    for (const api of apis) {
        const r = await callApi(api);
        results.push(r);
        if (r.status_code === 200) summary.passed++;
        else if (r.error) summary.errors++;
        else summary.failed++;
    }

    const output = { summary, results };
    const outPath = path.join(__dirname, 'api_check_results.json');
    fs.writeFileSync(outPath, JSON.stringify(output, null, 2), 'utf8');

    console.log('='.repeat(60));
    console.log(`API检查完成 - ${summary.check_time}`);
    console.log('='.repeat(60));
    console.log(`总计: ${summary.total}  通过: ${summary.passed}  失败: ${summary.failed}  错误: ${summary.errors}`);
    console.log('');
    for (const r of results) {
        const status = r.status_code === 200 ? 'OK' : (r.status_code ? 'FAIL' : 'ERR');
        const err = r.error ? ` [ERR: ${r.error}]` : '';
        const size = r.response_size_bytes ? `${r.response_size_bytes}B` : '-';
        const timeStr = r.response_time_sec ? `${r.response_time_sec}s` : '-';
        console.log(`${status.padEnd(4)} ${r.name.padEnd(30)} HTTP=${r.status_code || 'N/A'}  time=${timeStr.padStart(8)}  size=${size.padStart(10)}${err}`);
    }
    console.log('');
    console.log(`结果已保存至: ${outPath}`);
}

main();
