# 轨迹哨站：包裹时间线与超时清单

一个面向多承运商扫描数据的轨迹还原控制台。前端使用 React，后端使用 FastAPI，分析数据落在 DuckDB。系统以**扫描发生时间**还原物流轨迹，以**接收时间**记录数据到达，按北京时间工作时段计算停滞和整体超时。

## 业务规则

### 状态映射

不同承运商的原始扫描代码统一映射为 8 个规范状态：

- `PENDING`：待揽收
- `PICKED_UP`：揽收
- `IN_TRANSIT`：运输
- `ARRIVED`：到站
- `OUT_FOR_DELIVERY`：派送
- `DELIVERED`：签收
- `RETURNED`：退回
- `CANCELLED`：取消

线性物流状态只允许向前推进：

1. 相同扫描编号（`scan_id`）去重，重复导入不覆盖原记录。
2. 未知承运商状态代码会入库、展示并列为异常，但不推进进度。
3. 同一阶段的重复扫描不重置停滞计时，只有更高阶段的有效进展才会重置。
4. 不合理倒退（如签收后又收到运输扫描）列为异常，不改变当前状态。
5. 晚到的早期扫描按发生时间补进历史，不会让已签收包裹变回运输中。
6. 退回和取消是终态，单独统计，不再产生停滞或整体超时告警。

### 工作时段

- 所有时间按北京时间（UTC+8）解释和输出。
- 每个工作日只累计 09:00–18:00，共 9 个工作小时。
- 周六、周日不计时。
- 导入的节假日不计时，但扫描仍会按发生时间进入轨迹。
- 停滞：自最近一次有效进展起，连续没有有效进展达到 4 个工作小时。
- 整体超时：揽收到签收（未签收则到观察时刻）累计超过 24 个工作小时。
- 观察时刻之后发生的扫描完全不参与判断，即使数据已经提前到达系统。

### 告警生命周期

- 当前告警表以 `(tracking_no, alert_type)` 为主键：同一包裹同一种告警只保留一个当前状态。
- 重算时分别记录 `CREATED`、`UPDATED`、`CLEARED`、`REOPENED` 历史。
- 告警详情包含逐段工作时段以及被跳过的周末、节假日，可解释时间累计在哪里。

## 演示数据覆盖

初始化数据库时会自动生成 8 个包裹：

1. `SF-DEMO-1001`：周五晚揽收、周一签收，验证跨周末不计时。
2. `ZTO-DEMO-2002`：国庆长假期间运输、节后签收，验证导入节假日和告警解除历史。
3. `YTO-DEMO-3003`：缺少到站扫描的停滞件，可通过“补录缺失扫描”解除停滞并保留历史。
4. `JD-DEMO-4004`：跨周末且整体超时的已签收件。
5. `SF-DEMO-5005`：晚到补录、重复导入和签收后异常回退。
6. `ZTO-DEMO-6006`：拒收退回，终态单独统计。
7. `YTO-DEMO-7007`：客户取消，终态单独统计。
8. `SF-DEMO-8008`：未知状态代码，不推进进度。

导入模态框中可以恢复演示数据，也可以手动粘贴扫描 JSON 或导入节假日。

## 目录结构

```text
backend/
  domain.py      # 轨迹还原、工作时段、异常和告警核心规则
  db.py          # DuckDB schema、仓储与告警当前状态/历史
  importer.py    # 多承运商字段归一化、校验和 scan_id 去重
  seed.py        # 演示数据与补录样例
  main.py        # FastAPI 路由，构建后同时托管前端
  tests/         # 核心规则单元测试
frontend/
  src/
    App.jsx      # 页面状态、观察时刻和数据加载
    components/  # 监控台、告警清单、映射、轨迹抽屉、导入弹窗
    styles*.css  # 浅色/深色主题与响应式布局
data/            # 运行时 DuckDB 文件，已在 .gitignore 中忽略
```

## 本地运行

### 1. 后端

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
```

首次启动会自动创建 `data/tracking.duckdb` 并写入演示数据。

可用环境变量指定数据库：

```bash
TRACKER_DB_PATH=/tmp/tracking.duckdb .venv/bin/uvicorn backend.main:app
```

### 2. 前端开发服务器

```bash
cd frontend
npm install
npm run dev
```

Vite 会把 `/api` 代理到 `http://127.0.0.1:8000`。

### 3. 生产构建

```bash
cd frontend
npm run build
```

构建产物在 `frontend/dist`。重新启动 FastAPI 后访问 <http://127.0.0.1:8000/>，后端会直接托管构建后的页面。

## 测试

```bash
.venv/bin/python -m unittest discover -s backend/tests -v
```

测试覆盖：

- 工作窗口裁剪、周末与节假日跳过；
- 晚到扫描按发生时间排序；
- 签收后倒退不回退状态；
- 未知状态不推进；
- 观察时刻排除未来扫描；
- 4 工作小时停滞阈值；
- 相同扫描编号去重。

## 主要 API

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/overview` | 指标、状态统计、活跃告警、节假日和规则阈值 |
| GET | `/api/packages` | 包裹摘要，支持承运商、状态、告警类型和关键字过滤 |
| GET | `/api/packages/{tracking_no}` | 完整轨迹、异常、告警计时段、去重和告警历史 |
| GET | `/api/alerts` | 当前观察时刻的活跃告警 |
| GET | `/api/alerts/history` | 告警变化历史 |
| GET | `/api/mappings` | 承运商代码到规范状态的映射及未映射代码 |
| POST | `/api/scans/import` | 导入扫描 JSON，自动去重并重算告警 |
| POST | `/api/holidays/import` | 导入节假日并重算 |
| POST | `/api/recalculate` | 按指定观察时刻重算当前告警 |
| POST | `/api/packages/{tracking_no}/supplement` | 补录演示缺失扫描 |
| POST | `/api/demo/reset` | 清空并恢复演示数据 |

所有接收 `as_of` 的接口都接受带 `+08:00` 的 ISO 时间，例如：

```text
2026-10-08T15:00:00+08:00
```

## 扫描记录示例

```json
[
  {
    "tracking_no": "SF-DEMO-1001",
    "carrier": "SF",
    "scan_id": "SF1001-NEW-001",
    "status_code": "SF_HUB",
    "occurred_at": "2026-11-09T09:30:00+08:00",
    "received_at": "2026-11-12T10:00:00+08:00",
    "location": "上海虹桥分拨中心",
    "description": "晚到补录扫描"
  }
]
```

导入器也兼容 `waybill_no`、`scan_no`、`scan_time`、`event_time` 等常见字段名；字段缺失或时间无效会进入批次拒绝记录，不会静默丢弃。
