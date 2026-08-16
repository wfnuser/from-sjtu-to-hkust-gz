# 上海交通大学 → 香港科技大学（广州）骑行路线规划器

本仓库将路线生成工具链与可直接发布的静态地图分开：Python 脚本用于解析 POI、请求骑行路线并生成产物，`web/` 保存可部署的地图、样式、脚本和路线数据。

## 当前状态

- 默认网页现为 Day 1–14 江西执行线，产物位于 `web/data/inland-execution-*`，路线与每日住宿配置分别位于 `config/inland-execution-route.json` 和 `config/inland-itinerary.json`。
- 公开行程约 1688.4 km；Day 3–14 剩余约 1506.6 km，骑行日均约 125.6 km。Day 3 从海创园亚朵出发，经桐庐捷安特、富春江镇和新安绿道洋溪段，到建德新安江麗枫，约 134.7 km；后续落点均配置了可洗衣酒店候选。
- Day 7 走浒湾镇、万坊镇补给锚点，约 141.3 km。Day 11 为最长日，约 158.0 km，必须白天骑行并根据现场大车流决定是否改线或提前结束；计划在 Day 14 抵达香港科技大学（广州）。
- 左栏只展示 Day 1–14 日卡；点击日卡缩放到当天道路。手机竖屏采用上方地图、下方独立滚动日程面板；桌面使用左侧日程、右侧地图。
- Day 1 已按实际路线修正为交大闵行 → 叶新公路 → 桐乡酒店，约 111.6 km；通用 GPX 与 Markdown 路书导出到仓库外的 `Exports/SJTU-HKUSTGZ-Day1/`。
- 默认选择可骑行候选中的较短路线；只有平行道路距离接近（显式阈值最多 2 km）且更安全时才优先采用。硬风险和货运风险仍会阻断选择，除非存在精确到路段、带公开证据的安全覆盖；自动检查通过仍不替代出发当天的道路、施工、禁行与车流复核。
- 旧内陆审查基线仍可通过 `?route=inland` 查看，其近距离安全备选和决策证据继续保留，供临时改线参考。
- 沿海线仍保留在 `web/data/coastal-route.geojson` 与 `web/data/summary.json`，可通过 `?route=coastal` 查看；它明确不能在 15 个骑行日内执行，只可作为参考路线。

## 本地预览

无需构建，直接从静态产物目录启动本地服务器：

```bash
python3 -m http.server 8765 --bind 127.0.0.1 --directory web
```

然后在浏览器打开 <http://127.0.0.1:8765/>。

- 默认 Day 1–14 江西执行线：<http://127.0.0.1:8765/>
- 旧内陆审查基线：<http://127.0.0.1:8765/?route=inland>
- 沿海参考线：<http://127.0.0.1:8765/?route=coastal>

## 重新生成执行路线与 Day 1 路书

实时路线生成会使用本机 `.env.local` 的高德 Web 服务 Key；后续每日汇总和 GPX 导出不再访问 API：

```bash
python3 scripts/generate_route.py \
  --config config/inland-execution-route.json \
  --resolutions config/inland-execution-poi-resolutions.json \
  --env .env.local \
  --cache-dir .cache/amap \
  --output-dir web/data \
  --profile execution

python3 scripts/export_itinerary.py \
  --config config/inland-itinerary.json \
  --manifest web/data/inland-execution-route-manifest.json \
  --geojson web/data/inland-execution-route.geojson \
  --output web/data/inland-itinerary.json

python3 scripts/export_day_roadbook.py \
  --geojson web/data/inland-execution-route.geojson \
  --itinerary web/data/inland-itinerary.json \
  --day 1 \
  --output-dir ../../Exports/SJTU-HKUSTGZ-Day1
```

严格审计执行产物：

```bash
python3 scripts/audit_route.py \
  --config config/inland-execution-route.json \
  --data-dir web/data \
  --env .env.local \
  --profile execution \
  --strict
```

## 可重复验证（不访问实时 API）

以下命令只运行夹具和本地产物测试，特意排除需要真实高德配额的 `AmapLiveSmokeTest`：

```bash
python3 -m unittest \
  tests.test_amap.AmapClientTests \
  tests.test_artifacts \
  tests.test_audit \
  tests.test_config \
  tests.test_coordinates \
  tests.test_day_card_model \
  tests.test_day_roadbook \
  tests.test_execution_itinerary \
  tests.test_export \
  tests.test_inland_config \
  tests.test_inland_route \
  tests.test_inland_reroute_decisions \
  tests.test_manifest \
  tests.test_planner \
  tests.test_probe_reroutes \
  tests.test_reroute_options \
  tests.test_reroutes \
  tests.test_roads \
  tests.test_route_profile \
  tests.test_web_reroute_options \
  tests.test_web_reroute_status \
  tests.test_web_contract -v
```

## 重新生成近距离安全备选线

探路报告保存在被 Git 忽略的 `cache/`，发布用几何保存在 `web/data/inland-reroute-options.geojson`。这些旧内陆基线候选用于比较距离接近的平行安全道路；当前执行线不会仅为了减少国道里程而明显绕行，原路线始终保留：

```bash
python3 scripts/export_reroute_options.py \
  --config config/inland-route.json \
  --probes config/inland-reroute-probes.json \
  --resolutions config/inland-poi-resolutions.json \
  --manifest web/data/inland-route-manifest.json \
  --report cache/reports/inland-reroute-probes.json \
  --env .env.local \
  --cache-dir cache \
  --output web/data/inland-reroute-options.geojson
```

审核结论和实测探路报告分开维护；更新 `config/inland-reroute-reviews.json` 后，用下面的确定性导出命令重建公开决策清单，不会调用高德 API：

```bash
python3 scripts/export_reroute_decisions.py \
  --config config/inland-route.json \
  --resolutions config/inland-poi-resolutions.json \
  --manifest web/data/inland-route-manifest.json \
  --probes config/inland-reroute-probes.json \
  --report cache/reports/inland-reroute-probes.json \
  --reviews config/inland-reroute-reviews.json \
  --output web/data/inland-reroute-decisions.json
```

## 可选：高德实时烟雾测试

从模板创建仅供本机使用的环境文件，并填写实际 Web 服务 API Key；`.env.local` 已被 Git 忽略，绝不能提交：

```bash
cp .env.example .env.local
# 编辑 .env.local，填写 AMAP_WEB_SERVICE_KEY 的真实值
python3 -m unittest tests.test_amap.AmapLiveSmokeTest -v
```

实时测试会请求高德骑行路线服务，可能因网络、密钥权限或配额（包括 `10044`）失败。不要将 Key 放入 HTML、JavaScript、配置、缓存或提交历史中。

## 静态部署契约

- 构建命令：无。
- 发布目录：`web/`。
- SPA fallback：不需要；站点使用静态入口 `web/index.html`，并以相对路径读取同目录下的资源和 `web/data/` 产物。
- 部署前运行上面的可重复验证，并以本地预览确认 `index.html`、`styles.css`、`app.mjs` 和数据文件可访问。

本仓库不包含任何特定托管厂商的配置。选择托管平台后，只需将现有 `web/` 目录作为静态发布目录，不需要新增构建步骤。

## Git 与数据卫生

- 路线产物和配置会跟踪：`web/`、`config/`、`route_planner/`、`scripts/` 与测试夹具均是可审查的仓库内容。
- 密钥与 API 缓存会忽略：`.env.local`、其他本地 `.env.*` 文件（`.env.example` 除外）和 `cache/` 均不进入版本控制。
- 若需重新生成路线，使用 `scripts/generate_route.py` 并传入本机 `.env.local`；仅在实时请求成功、数据审查完成后才更新可跟踪的静态产物。

AMap 客户端使用标准库的证书和主机名校验；不会使用未验证的 TLS context。
