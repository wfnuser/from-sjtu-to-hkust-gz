# 沿海电助力骑行路线规划器

从上海交通大学闵行校区骑行至香港科技大学（广州）的可配置路线规划基础。

路线数据位于 `config/coastal-route.json`。坐标将在地点解析阶段写入；当前所有地点均以中文查询保存，并且可选的宁波和深圳支线默认禁用。

运行配置测试：

```bash
python3 -m unittest tests.test_config -v
```

## AMap 本地配置与 TLS

将 Web 服务 Key 保存在被 Git 忽略的 `.env.local` 中，使用 `AMAP_WEB_SERVICE_KEY=...`（也兼容 `AMAP_KEY=...`）。运行 AMap 实测：

```bash
python3 -m unittest tests.test_amap.AmapLiveSmokeTest -v
```

客户端始终使用标准库 `ssl.create_default_context()` 的证书和主机名校验。在此 macOS Python 环境中，默认 CA 发现不可用时，客户端会使用存在的系统 CA bundle `/etc/ssl/cert.pem`；`SSL_CERT_FILE` 若指向有效文件则优先使用。不会使用未验证的 TLS context。
