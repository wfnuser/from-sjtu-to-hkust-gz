# Task 7 Report — Actual Coastal Main Route

Status: **DONE_WITH_CONCERNS**

Primary data commit: `f0ec986e23d7a5bc254b8c1e6214f7891600e673` (`data: add audited coastal cycling route`)

## Published result

- Main route: 上海交通大学闵行校区 → 香港科技大学（广州）, 33 segments, 18 riding days.
- Selected distance: 2,444,486 m; AMap cycling duration: 486,551 s (135 h 9 min).
- Direct-candidate baseline: 2,230,959 m; whole-route detour ratio: 1.095711 (+9.57%), below the 15% route-level limit.
- Maximum API subleg: 77,963 m; every generated routing request is at most 80 km.
- Classified distance: national 267,077 m; provincial 209,086 m; county/town 145,021 m; cycleway 4,884 m; city 0 m; UNKNOWN 1,818,418 m.
- Strict audit exits 0. Published data contains no unresolved main polyline and no step that the text-based classifier tagged as hard-risk or freight-risk.
- `unresolved_count = 4` consists only of explicit per-segment detour warnings; it does not mean four missing polylines.

## Commands run

The configured AMap credential was read from `.env.local`; it was never copied into the report, config, or published data.

```bash
python3 scripts/resolve_pois.py \
  --config config/coastal-route.json \
  --env .env.local \
  --output config/poi-resolutions.json

python3 scripts/generate_route.py \
  --config config/coastal-route.json \
  --resolutions config/poi-resolutions.json \
  --env .env.local \
  --output-dir web/data

python3 scripts/audit_route.py \
  --config config/coastal-route.json \
  --data-dir web/data \
  --env .env.local \
  --strict
```

The client uses the repository response cache, and the default live-request interval was raised to 1.05 s after AMap's query-per-second limit rejected the original 0.34 s interval.

## POI resolution and provenance

All 34 required main-route waypoints have a selected candidate and `unresolved_queries` is empty. Important endpoint/office selections were verified by full Chinese address:

| Query | POI ID | Selected AMap name | Full address |
|---|---|---|---|
| 上海交通大学闵行校区 | `B00155R1D5` | 上海交通大学(闵行本部校区) | 上海市上海市闵行区东川路800号 |
| 杭州阿里巴巴总部 | `B023B1D4BX` | 阿里巴巴西溪园区A区 | 浙江省杭州市余杭区文一西路969号 |
| 香港科技大学（广州） | `B0IGJURJOJ` | 香港科技大学(广州) | 广东省广州市南沙区笃学路1号 |

The AMap v3 geocoder returned `30001 ENGINE_RESPONSE_DATA_ERROR` for the official HKUST (Guangzhou) name. The resolver now falls back to the v3 place-text endpoint and stores its POI ID rather than silently substituting a coordinate.

Optional Shanghai check-ins were also preserved with provenance. The exact matches selected were:

- 上海科技小学 alias → `B0J05CXO4Y`, 上海市静安区科技学校, 上海市上海市静安区阳曲路350弄1号.
- 上海当代（杨波）中学 historical alias → `B00155L2HA`, 上海市民办扬波中学, 上海市上海市静安区大统路991号.
- 上海交通大学闵行校区 → the same `B00155R1D5` candidate above.

Four optional check-ins remain intentionally unresolved because the input does not identify one safe candidate: 阳曲路住处 has no street number; 上海交大附中 has multiple campuses; 上海字节办公点 has multiple offices; 上海阿里中心 has competing 虹桥/徐汇 results. They do not participate in the main route.

## Anchors and route refinement

Twenty-one accepted anchors were added across 17 main segments. They include 亭林、三界、瑞安、马站、牙城、盐田、下白石、罗源、连江、福清、晋江、东孚、漳浦、陇田、葵潭、陆丰、梅陇、吉隆、企石、萝岗. Cross-city anchors use the explicit `城市::查询` syntax so, for example, 罗源县 is resolved in 福州 rather than in the segment's origin city.

Material rejected alternatives included:

- 苍南—福鼎 via 马站/沙埕 removed labelled national-road use but approached three times the direct route; the shorter 马站-only coastal result was retained.
- 莆田—惠安 via 笏石/东庄/辋川 increased labelled national-road use to 20,792 m and detour to more than 51%.
- 厦门—云霄 via 佛昙/杜浔 removed labelled national-road use, but added 531 m of 疏港大道辅路 freight exposure and 53% detour.
- 惠来—汕尾 via 甲子/碣石/金厢 increased labelled national-road use to 64,325 m and introduced freight-road text.
- 汕尾—惠东 via 鲘门/稔山 produced over-80-km sublegs, 24,353 m freight-road text, and roughly threefold detour.
- 博罗—增城 direct candidates included 23–39 m of `G35济广高速入口`; the 企石 anchor produced a 75,594 m route without a labelled hard-risk step and was retained despite its 32.74% segment detour.

## National-road exceptions

The following values are the labelled national-road distances measured in the selected AMap steps. Each is capped by `allowed_national_m` and accompanied by an audit record. These measurements support the selected candidate among the alternatives that were actually queried; they are **not proof that no unqueried parallel road exists**. Road aliases and UNKNOWN steps make a stronger claim unjustified.

| Segment | Allowed/measured | Inspection result |
|---|---:|---|
| main-06-to-main-07 | 9,745 m | 新昌儒岙至天台白鹤的山口段，两条返回候选共用104国道；县乡路未形成连续铺装跨山通道。 |
| main-07-to-main-08 | 5,510 m | 已优先采用316省道，三条候选仍借104国道连接河谷；保留返回候选中的最低值。 |
| main-09-to-main-10 | 15,307 m | 温岭大溪—乐清大荆/雁荡的三条候选均用104国道；平行镇道未连续穿越山口。 |
| main-10-to-main-11 | 4,348 m | 乐清北白象的铁路、河道及互通切割平行镇道；保留三条候选中的最低值。 |
| main-14-to-main-15 | 17,001 m | 盐田、下白石锚点固定沿海补给线；福安湾/蕉城北跨河仍使用353/104国道。 |
| main-15-to-main-16 | 17,149 m | 罗源、连江锚点控制子段并保留补给；飞鸾/罗源湾山海夹道候选仍使用104国道。 |
| main-16-to-main-17 | 24,812 m | 福清锚点把 labelled national 从56,272 m降到24,812 m；河道、铁路切割县乡路。 |
| main-17-to-main-18 | 14,875 m | 沿海镇道试跑反而达到20,792 m national 且绕行超过51%；保留较低内陆候选。 |
| main-19-to-main-20 | 10,035 m | 晋江拆段后，经石狮/翔安试跑仍共用324国道且多绕24%；保留实测值。 |
| main-21-to-main-22 | 55,336 m | 漳浦锚点将74,077 m降到55,336 m；佛昙/杜浔替代线因疏港道路和53%绕行被拒。 |
| main-22-to-main-23 | 19,254 m | 东厦/四都试跑增加到22,680 m并绕行44%；保留228/324国道较短候选。 |
| main-23-to-main-24 | 11,338 m | 黄冈/钱东锚点仍共用省界—黄冈228国道，未降低 labelled national 距离。 |
| main-26-to-main-27 | 43,308 m | 葵潭/陆丰从51,104 m降到43,308 m；甲子/碣石/金厢反而到64,325 m并有 freight 标签。 |
| main-28-to-main-29 | 19,059 m | 梅陇/吉隆从33,011 m降到19,059 m；鲘门/稔山出现长子段、货运道路和三倍绕行。 |

## Eighteen-day grouping

The 2,444.5 km route cannot satisfy both an 18-day deadline and an 80–120 km/day target: even the arithmetic average is 135.8 km/day. The generated plan therefore preserves the requested deadline structure and ends each day at a named county/city, but it is an aggressive itinerary.

| Day | From → To | Distance |
|---:|---|---:|
| 1 | 上海交通大学闵行校区 → 海宁 | 124.8 km |
| 2 | 海宁 → 绍兴 | 145.0 km |
| 3 | 绍兴 → 天台 | 145.7 km |
| 4 | 天台 → 温岭 | 128.6 km |
| 5 | 温岭 → 温州 | 110.4 km |
| 6 | 温州 → 福鼎 | 160.2 km |
| 7 | 福鼎 → 霞浦 | 99.6 km |
| 8 | 霞浦 → 宁德 | 114.8 km |
| 9 | 宁德 → 福州 | 137.6 km |
| 10 | 福州 → 惠安 | 190.6 km |
| 11 | 惠安 → 厦门 | 132.1 km |
| 12 | 厦门 → 云霄 | 179.0 km |
| 13 | 云霄 → 汕头 | 154.9 km |
| 14 | 汕头 → 惠来 | 122.7 km |
| 15 | 惠来 → 汕尾 | 130.9 km |
| 16 | 汕尾 → 惠东 | 125.6 km |
| 17 | 惠东 → 增城 | 130.6 km |
| 18 | 增城 → 香港科技大学（广州） | 111.4 km |

## The four unresolved-count warnings

All four are `DETOUR_OVER_15_PERCENT` warnings measured against the direct AMap cycling candidate for that waypoint pair:

| Segment | Endpoints | Baseline | Selected | Ratio | Why retained |
|---|---|---:|---:|---:|---|
| main-07-to-main-08 | 天台 → 临海 | 46.457 km | 53.458 km | 1.150698 | The selected valley connection minimizes measured 104国道 use among the returned candidates; it is only 0.07 percentage point over the threshold. |
| main-12-to-main-13 | 苍南 → 福鼎 | 35.419 km | 85.513 km | 2.414326 | 马站 anchor takes the coastal line and removes labelled national-road use; the safety preference costs 50.094 km. |
| main-25-to-main-26 | 汕头 → 惠来 | 93.337 km | 122.700 km | 1.314591 | 陇田 anchor splits the long request and steers through a town/supply point; the selected route remains warning-worthy. |
| main-31-to-main-32 | 博罗 → 增城 | 56.951 km | 75.594 km | 1.327352 | 企石 anchor avoids the returned alternatives' labelled `G35济广高速入口` hard-risk steps; the 18.643 km cost is explicit. |

The UI now deduplicates segment-wide warnings to one review link per segment while retaining an individual link for every genuinely hard-tagged step.

## Why 1,818 km is UNKNOWN

`UNKNOWN` is a conservative classifier result, not a statement that those roads are unsafe or that they are local roads. AMap's cycling response supplies road names/instructions but no authoritative administrative road class. The deterministic classifier only recognizes explicit `G###`/`国道`, `S###`/`省道`, `X###`/`Y###`/`县道`/`乡道`, cycleway keywords, and explicit city-road keywords. Ordinary names such as `新城大道`, aliases that omit a route number, and blank step names therefore stay UNKNOWN.

Of the 1,818,418 m UNKNOWN total, 618,858 m has no road name and 1,199,560 m has one of 682 ordinary/alias names. Consequently, the audit proves only that no **text-labelled** hard/freight step exceeds the policy and that labelled national-road use is within the documented allowances. It does not prove complete national-road avoidance or exclude a hidden national/high-risk identity inside an alias/unnamed step. Road-level rider verification remains necessary.

## Browser inspection

The generated map loaded 33 cards grouped under 18 day headings. Browser-side GeoJSON distance summed exactly to the 2,444,486 m summary total. Road-level inspections were made in all four required provinces:

- 上海, main-01: 65 steps / 2,145 geometry points; road-following geometry and Chinese names such as 学森路、光斗路 were visible.
- 浙江, main-06: 34 steps / 1,708 points; 619县道、太下线 and the orange national-road portion were visible; card was grouped under day 3.
- 福建, main-21: 95 steps / 2,449 points; Chinese road names and 55,336 m labelled national total matched the artifact; grouped under day 12.
- 广东, main-28: 90 steps / 2,699 points; 红城大道西、228国道、梅北大道、深汕大道 were visible; 19,059 m labelled national total matched; grouped under day 16.

Clicking one Zhejiang national-road review opened the exact `104国道` step and showed `道路分类：国道`. The only console error observed was a missing optional `/favicon.ico`.

## Verification and concerns

The fresh deterministic suite passed 73 tests covering POI fallback/provenance, cache/throttle behavior, cross-city anchors, exception enforcement, audit, day grouping, and browser contracts. The live smoke test was omitted from that final suite because the configured account reached AMap `10044 USER_DAILY_QUERY_OVER_LIMIT` after the route and alternative probes had already been cached. Four late Zhejiang anchor experiments could not be run for that reason; the retained Zhejiang choices are based on the already cached direct alternatives, not an exhaustive parallel-road search.

Remaining concerns before real travel:

1. The 18-day deadline is physically aggressive (average 135.8 km/day; maximum 190.6 km on day 10).
2. UNKNOWN covers 74.39% of the route, so classifier-based safety and national-road findings have the limitations described above.
3. Four optional Shanghai check-ins need precise user addresses/campus choices.
4. Four selected segments intentionally remain over the 15% per-segment detour threshold.
5. The AMap daily quota prevented four additional Zhejiang alternative probes. Re-run them after quota reset before claiming broader coverage.
