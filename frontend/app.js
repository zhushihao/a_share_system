/* Dashboard Frontend - A股动量趋势系统 v5.0 前后端分离 */

const API_BASE = '/api';
let refreshTimer = null;
let serverOnline = false;

// ════════════════════════════════════════════════════════════
// 初始化
// ════════════════════════════════════════════════════════════

document.addEventListener('DOMContentLoaded', () => {
    checkServer();
    updateTime();
    setInterval(updateTime, 1000);
    setRefreshInterval();
});

function updateTime() {
    const now = new Date();
    document.getElementById('current-time').textContent = now.toLocaleString('zh-CN');
}

// ════════════════════════════════════════════════════════════
// 服务器检测
// ════════════════════════════════════════════════════════════

async function checkServer() {
    const badge = document.getElementById('server-badge');
    try {
        const resp = await fetch(`${API_BASE}/health`, { method: 'GET', mode: 'cors', timeout: 3000 });
        if (resp.ok) {
            serverOnline = true;
            badge.textContent = '后端已连接';
            badge.style.background = 'rgba(56, 161, 105, 0.2)';
            badge.style.color = '#68d391';
            document.getElementById('offline-panel').style.display = 'none';
            loadAllData();
            checkEngineStatus();
        } else {
            throw new Error('HTTP ' + resp.status);
        }
    } catch (e) {
        serverOnline = false;
        badge.textContent = '后端离线';
        badge.style.background = 'rgba(229, 62, 62, 0.2)';
        badge.style.color = '#fc8181';
        document.getElementById('offline-panel').style.display = 'block';
        document.getElementById('indices-section').innerHTML = '';
        document.getElementById('sectors-body').innerHTML = '<div style="text-align:center; color:var(--text-light); padding:40px">等待后端连接...</div>';
        document.getElementById('health-grid').innerHTML = '';
        document.getElementById('events-list').innerHTML = '';
    }
}

function startBackend() {
    const msg = document.getElementById('backend-msg');
    msg.textContent = '请运行项目目录下的 launch.bat 或 launch.py 启动后端服务';
    msg.style.color = '#dd6b20';
}

// ════════════════════════════════════════════════════════════
// 数据加载
// ════════════════════════════════════════════════════════════

async function loadAllData() {
    if (!serverOnline) return;
    await Promise.all([
        loadIndices(),
        loadSectors(),
        loadHealth(),
        loadEvents(),
        loadWatchlist(),
    ]);
}

async function loadIndices() {
    try {
        const resp = await fetch(`${API_BASE}/market/overview`);
        const data = await resp.json();
        const indices = data.indices || [];
        const container = document.getElementById('indices-section');
        container.innerHTML = indices.map(idx => `
            <div class="card">
                <div class="card-body index-card">
                    <div class="name">${idx.name}</div>
                    <div class="price" style="color: ${idx.status === 'up' ? 'var(--up)' : idx.status === 'down' ? 'var(--down)' : 'var(--flat)'}">${idx.price}</div>
                    <div class="change ${idx.status}">${idx.change_pct > 0 ? '+' : ''}${idx.change_pct}%</div>
                </div>
            </div>
        `).join('');
    } catch (e) { console.error('indices:', e); }
}

async function loadSectors() {
    try {
        const resp = await fetch(`${API_BASE}/sectors/top?limit=10`);
        const data = await resp.json();
        const sectors = data.sectors || [];
        const tbody = document.getElementById('sectors-body');
        if (sectors.length === 0) {
            tbody.innerHTML = '<div style="text-align:center; color:var(--text-light); padding:40px">暂无板块数据</div>';
            return;
        }
        tbody.innerHTML = `
            <table class="table">
                <thead><tr><th>排名</th><th>板块</th><th>涨幅</th><th>动量</th><th>龙头</th></tr></thead>
                <tbody>
                    ${sectors.map((s, i) => `
                        <tr>
                            <td class="rank ${i < 3 ? 'top3' : ''}">${i + 1}</td>
                            <td class="name-cell">${s.name}</td>
                            <td class="pct ${s.change_pct > 0 ? 'up' : s.change_pct < 0 ? 'down' : ''}">${s.change_pct > 0 ? '+' : ''}${s.change_pct}%</td>
                            <td class="bar-cell"><div class="bar"><div class="bar-fill ${s.change_pct > 0 ? 'up' : 'down'}" style="width: ${s.momentum}%"></div></div></td>
                            <td class="name-cell">${s.leader}<span class="code">${s.leader_code}</span></td>
                        </tr>
                    `).join('')}
                </tbody>
            </table>`;
    } catch (e) { console.error('sectors:', e); }
}

async function loadHealth() {
    try {
        const resp = await fetch(`${API_BASE}/health`);
        const h = await resp.json();
        const grid = document.getElementById('health-grid');
        grid.innerHTML = `
            <div class="health-item"><div class="dot ${h.offline_data ? 'ok' : 'error'}"></div><span class="label">离线数据</span><span class="value">${h.offline_data ? '正常' : '异常'}</span></div>
            <div class="health-item"><div class="dot ${h.realtime_data ? 'ok' : 'warn'}"></div><span class="label">实时服务器</span><span class="value">${h.realtime_data ? '正常' : '离线'}</span></div>
            <div class="health-item"><div class="dot ${h.tdxdir ? 'ok' : 'warn'}"></div><span class="label">数据目录</span><span class="value">${h.tdxdir ? '已连接' : '未配置'}</span></div>
            <div class="health-item"><div class="dot ${h.mootdx ? 'ok' : 'error'}"></div><span class="label">mootdx</span><span class="value">${h.mootdx ? '已安装' : '未安装'}</span></div>
        `;
    } catch (e) { console.error('health:', e); }
}

async function loadEvents() {
    try {
        const resp = await fetch(`${API_BASE}/events/status`);
        const data = await resp.json();
        const list = document.getElementById('events-list');
        // 从 TimeTrigger 获取今日事件
        const events = [
            { name: '开盘前', time: '09:15' },
            { name: '开盘', time: '09:30' },
            { name: '早盘中场', time: '10:30' },
            { name: '早盘收盘', time: '11:30' },
            { name: '午盘开盘', time: '13:00' },
            { name: '尾盘前', time: '14:30' },
            { name: '收盘', time: '15:00' },
            { name: '收盘后复盘', time: '15:05' },
        ];
        list.innerHTML = events.map(e => `
            <div class="event-item"><span class="name">${e.name}</span><span class="time">${e.time}</span></div>
        `).join('');
    } catch (e) { console.error('events:', e); }
}

async function loadWatchlist() {
    try {
        const resp = await fetch(`${API_BASE}/stocks/watchlist?codes=000001,600519,300750`);
        const data = await resp.json();
        const stocks = data.stocks || [];
        if (stocks.length > 0) {
            document.getElementById('watchlist-section').style.display = 'block';
            document.getElementById('watchlist-body').innerHTML = `
                <table class="table">
                    <thead><tr><th>代码</th><th>名称</th><th>现价</th><th>涨跌</th><th>成交量</th><th>成交额</th></tr></thead>
                    <tbody>
                        ${stocks.map(s => `
                            <tr>
                                <td class="name-cell">${s.code}</td>
                                <td>${s.name}</td>
                                <td style="font-weight:600">${s.price}</td>
                                <td class="pct ${s.change_pct > 0 ? 'up' : s.change_pct < 0 ? 'down' : ''}">${s.change_pct > 0 ? '+' : ''}${s.change_pct}%</td>
                                <td>${s.volume.toLocaleString()}</td>
                                <td>${s.amount}亿</td>
                            </tr>
                        `).join('')}
                    </tbody>
                </table>`;
        }
    } catch (e) { console.error('watchlist:', e); }
}

// ════════════════════════════════════════════════════════════
// 引擎控制
// ════════════════════════════════════════════════════════════

async function checkEngineStatus() {
    if (!serverOnline) return;
    try {
        const resp = await fetch(`${API_BASE}/system/status`);
        const data = await resp.json();
        const badge = document.getElementById('engine-status-badge');
        if (data.running) {
            badge.textContent = '事件引擎运行中 (' + data.triggers + '个触发器)';
            badge.style.color = '#38a169';
        } else {
            badge.textContent = '事件引擎已停止';
            badge.style.color = '#a0aec0';
        }
    } catch (e) {
        document.getElementById('engine-status-badge').textContent = '状态检测失败';
    }
}

async function controlEngine(action) {
    const msg = document.getElementById('control-msg');
    msg.textContent = action === 'start' ? '正在启动...' : '正在停止...';
    try {
        const resp = await fetch(`${API_BASE}/system/${action}`, { method: 'POST' });
        const data = await resp.json();
        msg.textContent = data.message || data.error;
        msg.style.color = data.success ? '#38a169' : '#e53e3e';
        setTimeout(checkEngineStatus, 1000);
    } catch (e) {
        msg.textContent = '操作失败: ' + e;
        msg.style.color = '#e53e3e';
    }
}

// ════════════════════════════════════════════════════════════
// 刷新
// ════════════════════════════════════════════════════════════

function setRefreshInterval() {
    const select = document.getElementById('refresh-interval');
    const interval = parseInt(select.value);
    if (refreshTimer) { clearInterval(refreshTimer); refreshTimer = null; }
    if (interval > 0) {
        refreshTimer = setInterval(() => { if (serverOnline) loadAllData(); }, interval * 1000);
    }
}

function refreshData() {
    checkServer();
}
