# Quant Workbench 能力扩展计划

## 目标
将系统从"基础指标+信号"升级到包含"形态识别、量价分析、指标叠加、画线工具"的完整分析平台。

---

## 阶段1：后端形态识别引擎

### 1.1 价格形态（Price Patterns）

| 形态 | 算法思路 | 优先级 |
|------|----------|--------|
| **双顶（M头）** | 扫描两个相近高点 + 中间低点 + 颈线跌破 | P0 |
| **双底（W底）** | 扫描两个相近低点 + 中间高点 + 颈线突破（已部分实现） | P0 |
| **头肩顶** | 扫描三个峰（中间最高）+ 颈线跌破 | P0 |
| **头肩底** | 扫描三个谷（中间最低）+ 颈线突破（已部分实现） | P0 |
| **三角形（收敛）** | 扫描高低点逐步收敛的三角形 | P1 |
| **三角形（上升/下降）** | 扫描一边水平、一边收敛的三角形 | P1 |
| **旗形/楔形** | 扫描平行通道或发散通道 | P1 |
| **V型反转** | 扫描急跌后急涨（或急涨后急跌） | P1 |
| **圆弧底/顶** | 扫描渐进式圆弧底部 | P2 |

### 1.2 波浪结构（Wave Structure）

| 能力 | 算法思路 | 优先级 |
|------|----------|--------|
| **浪型识别** | 基于高低点序列识别5-3波浪结构 | P1 |
| **斐波那契回调** | 计算关键回调位（0.382/0.5/0.618） | P0 |
| **黄金分割** | 关键支撑/阻力位的斐波那契扩展 | P1 |

### 1.3 量价节点分析

| 节点类型 | 算法 | 优先级 |
|----------|------|--------|
| **放量突破点** | 成交量>1.5倍20日均值 + 价格突破 | P0 |
| **缩量回调点** | 成交量<0.5倍20日均值 + 价格下跌 | P0 |
| **天量/地量** | 成交量为N日最大/最小 | P0 |
| **量价背离** | 价格新高+量未新高 / 价格新低+量未新低 | P0 |

### 1.4 支撑/阻力位

| 类型 | 算法 | 优先级 |
|------|------|--------|
| **历史高低点** | 最近N日/周/月的高低点 | P0 |
| **密集成交区** | 成交量加权价格分布的高密度区域 | P1 |
| **斐波那契位** | 0.382/0.5/0.618 回调位 | P1 |
| **整数关口** | 价格整数位（如10.00, 11.00） | P2 |

---

## 阶段2：前端图表升级

### 2.1 主图叠加指标

| 指标 | 叠加方式 | 实现方式 |
|------|----------|----------|
| MA5/MA10/MA20/MA60 | 折线叠加 | lightweight-charts LineSeries |
| BOLL（UP/MID/DOWN） | 折线叠加 | 三条线 |

### 2.2 副图指标（新Panel）

| 指标 | 副图位置 | 实现方式 |
|------|----------|----------|
| MACD（DIF/DEA/BAR） | 副图1 | 柱状+折线混合 |
| KDJ（K/D/J） | 副图2 | 三条折线 |
| RSI（6/12/24） | 副图3 | 三条折线 + 超买超卖线 |
| 成交量 | 副图0（已有） | 柱状图 |

### 2.3 形态标记叠加

| 标记类型 | 展示方式 |
|----------|----------|
| 双顶/双底 | 在对应K线上方/下方显示形态名称标签 |
| 头肩形态 | 用连线标记三个峰/谷 + 颈线 |
| 三角形 | 用连线标记收敛的高低点 |
| 波浪标记 | 在K线上方标注浪号（1,2,3,4,5,A,B,C） |
| 支撑/阻力 | 用水平线 + 标签标注 |
| 量价节点 | 在对应K线上方标记节点类型（放量突破/缩量回调等） |

### 2.4 画线工具

| 工具 | 交互方式 |
|------|----------|
| 趋势线 | 两点连线，自动延长 |
| 水平线 | 点击Y轴位置，生成水平参考线 |
| 黄金分割线 | 选择两点，自动画0.382/0.5/0.618线 |
| 斐波那契扩展 | 选择三点，画扩展位 |

---

## 阶段3：API设计

### 3.1 新增API端点

```
GET /api/v1/quote/{symbol}/patterns
  → 返回识别出的形态列表（类型、位置、置信度）
  
GET /api/v1/quote/{symbol}/volume-analysis
  → 返回量价节点列表（类型、日期、价格、成交量）
  
GET /api/v1/quote/{symbol}/support-resistance
  → 返回支撑/阻力位列表（价格、类型、强度）
  
GET /api/v1/quote/{symbol}/wave-structure
  → 返回波浪结构（浪号、起止日期、起止价格）
  
GET /api/v1/quote/{symbol}/fibonacci
  → 返回斐波那契位（回调/扩展位、价格）
```

---

## 阶段4：数据结构

### 4.1 PatternResult
```python
class PatternResult:
    type: str           # "double_top", "double_bottom", "head_shoulder_top"...
    start_date: str
    end_date: str
    start_price: float
    end_price: float
    peak_prices: List[float]
    trough_prices: List[float]
    confidence: float   # 0-1
    neck_line: float    # 颈线价格
    target: float       # 等幅测量目标价
    description: str
```

### 4.2 VolumeNode
```python
class VolumeNode:
    type: str           # "breakout", "shrinkage", "divergence_bull", "divergence_bear"
    date: str
    price: float
    volume: float
    volume_ratio: float  # 相对于20日均量的倍数
    description: str
```

### 4.3 SupportResistance
```python
class SupportResistance:
    price: float
    type: str           # "support", "resistance"
    source: str         # "history_high_low", "dense_volume", "fibonacci"
    strength: int       # 1-5（触碰次数）
    touch_dates: List[str]
```

### 4.4 WaveStructure
```python
class WaveStructure:
    waves: List[Wave]
    
class Wave:
    number: str         # "1", "2", "3", "4", "5", "A", "B", "C"
    start_date: str
    end_date: str
    start_price: float
    end_price: float
    direction: str      # "up", "down"
    length: float       # 价格幅度
```
