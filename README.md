# 上海交通大学闵行校区 → 香港科技大学（广州）电助力骑行路线规划器

本仓库将路线生成工具链与可直接发布的静态地图分开：Python 脚本用于解析 POI、请求骑行路线并生成产物，`web/` 保存可部署的地图、样式、脚本和路线数据。

## 当前状态

- 沿海线已经发布，数据位于 `web/data/`，配置位于 `config/coastal-route.json`；不过它明确不能在 15 个骑行日内执行，只可作为待复核的参考路线，不能作为执行方案。
- 内陆走廊、POI 解析结果和排程契约已经准备好（见 `config/inland-route.json` 与 `config/inland-poi-resolutions.json`）。骑行几何尚未生成：高德骑行路径请求受 `10044` 配额限制，恢复可用配额后才可进行实时生成并发布。
- 宁波和深圳支线默认关闭，不计入沿海主线总计。

## 本地预览

无需构建，直接从静态产物目录启动本地服务器：

```bash
python3 -m http.server 8765 --bind 127.0.0.1 --directory web
```

然后在浏览器打开 <http://127.0.0.1:8765/>。

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
  tests.test_planner \
  tests.test_roads \
  tests.test_web_contract -v
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
