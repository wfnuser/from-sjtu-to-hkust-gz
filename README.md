# 沿海电助力骑行路线规划器

从上海交通大学闵行校区骑行至香港科技大学（广州）的可配置路线规划基础。

路线数据位于 `config/coastal-route.json`。坐标将在地点解析阶段写入；当前所有地点均以中文查询保存，并且可选的宁波和深圳支线默认禁用。

运行配置测试：

```bash
python3 -m unittest tests.test_config -v
```
