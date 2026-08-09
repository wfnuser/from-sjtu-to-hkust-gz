# 上海交通大学闵行校区 → 香港科技大学（广州）电助力骑行路线规划器

本仓库将路线生成工具链与可直接发布的静态地图分开：Python 脚本用于解析 POI、请求骑行路线并生成产物，`web/` 保存可部署的地图、样式、脚本和路线数据。

## 当前状态

- 内陆审查基线已经发布并作为网页默认路线，数据位于 `web/data/inland-*`，配置位于 `config/inland-route.json`。当前约 1816.6 km，相对逐段直达基线增加约 7.9%，自动分类出约 230.2 km 国道；国道例外均记录了实测保留量与已试替代方案，但整条路线仍需道路级复核。
- 地图保留当前原路线，并用可关闭的青色虚线展示两条避国道备选：信丰→龙南、南城→广昌。备选线只用于比较，不计入主线总里程。
- 沿海线仍保留在 `web/data/coastal-route.geojson` 与 `web/data/summary.json`，可通过 `?route=coastal` 查看；它明确不能在 15 个骑行日内执行，只可作为参考路线。
- 内陆排程暂不在网页展示。高德电助力时长不是本项目最终采用的长途移动速度口径，逐日 15 天方案将在路径复核后独立锁定，避免把当前诊断误作执行日程。
- 宁波和深圳支线默认关闭，不计入沿海主线总计。

## 本地预览

无需构建，直接从静态产物目录启动本地服务器：

```bash
python3 -m http.server 8765 --bind 127.0.0.1 --directory web
```

然后在浏览器打开 <http://127.0.0.1:8765/>。

- 默认内陆线：<http://127.0.0.1:8765/>
- 沿海参考线：<http://127.0.0.1:8765/?route=coastal>

## 可重复验证（不访问实时 API）

以下命令只运行夹具和本地产物测试，特意排除需要真实高德配额的 `AmapLiveSmokeTest`：

```bash
python3 -m unittest \
  tests.test_amap.AmapClientTests \
  tests.test_artifacts \
  tests.test_audit \
  tests.test_config \
  tests.test_coordinates \
  tests.test_export \
  tests.test_inland_config \
  tests.test_inland_route \
  tests.test_manifest \
  tests.test_planner \
  tests.test_probe_reroutes \
  tests.test_reroute_options \
  tests.test_reroutes \
  tests.test_roads \
  tests.test_route_profile \
  tests.test_web_reroute_status \
  tests.test_web_contract -v
```

## 重新生成避国道备选线

探路报告保存在被 Git 忽略的 `cache/`，发布用几何保存在 `web/data/inland-reroute-options.geojson`。下面的导出只选择“至少减少 10 km 国道、但因未知道路增加而需复核”的候选；原路线始终保留：

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
