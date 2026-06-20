# research domain — 公开调研管线设计

> 用户 2026-06-14 新开「公开调研」线。核心 = **一条通用性价比研究管线 + 一个统一研究库(累积、开跑前查重,绝不重复调研)**。本质是把手搓的"拆题→并行联网查证带来源→综合成不打分报告"固化成可反复跑的 Team。

## 现状:SOTA parity 六节点(2026-06-14,架构已端到端验证)

`omni run research.run -i topic="<题目>" [-i max_rounds=2 -i max_subtopics=4 -i workers=4]`,六节点:

1. **intake**(RULE)—— 归一化 + 查重门(同题带出增量),建 run_dir。
2. **planner**(LLM·中端 qwen3.6-plus,`routers/deep.py`)—— **先搜后拆**:拿原题搜背景→产**互不重叠的多视角子主题**(含"基础覆盖"+"冷门/替代"兜底,STORM 召回机制);失败有确定性兜底拆题。
3. **orchestrate**(`routers/deep.py`)—— **节点内循环**:`run_parallel_items` 并行派子研究员(各自独立局部上下文:多 query 搜→抓→单页摘要→抽带来源发现)→ 反思看覆盖账本指缺口 + 打捞未用上的料 → 有界迭代(默认 2 轮,衰减广度)。覆盖账本落 `data/domains/research/coverage/<run>.json`。
4. **synthesize**(LLM·便宜档,`routers/synth.py`)—— 据带来源发现综合成接地、带引用编号、不打分的结论;失败降级。
5. **claim_verify**(LLM·中端,`routers/synth.py`)—— **对抗式逐条核源**:`run_parallel_items` 并行,每条 finding 抓原始来源判 supported/partial/unsupported,写回 `support`;report 里 unsupported 显眼标 ⚠。
6. **library_write**(RULE)—— 去重累积 upsert 进统一库,渲 report.md。

模型档位:拆题/反思/核源走中端 qwen3.6-plus(错代价大),摘要/抽取/综合走便宜默认档。验证(`OMNI_WEB_SEARCH_DRY_RUN=1` 离线 mock):planner 真产多视角子主题(`degraded:false`)、并行子研究+反思+覆盖账本全跑、mock 无内容时 0 findings(防幻觉)、同题 dup 增量。

> **当前硬阻断:免费检索源已死。** DuckDuckGo 抓取被封/改版(两个端点都返回零外链,`web_search.py` 正则对不上),真实召回拿不到结果。**解法:配 `SERPER_API_KEY`(serper.dev 免费 2500/月)即自动生效**(`sources/web.py` 检测到 key 自动切 serper,零改码),或加 Tavily Router。这是真实跑出 SOTA 产物的前置。

<details><summary>历史:最小闭环(已被上面的六节点取代)</summary>

`omni run research.run -i topic="<题目>"` 四节点线性:

1. **intake**(RULE,`routers/pipeline.py:TopicIntake`)—— 归一化题目、建 run_dir、**查重门**(`library.lookup_by_topic`,同题已有则带出)、确定性多 query 展开。
2. **retrieve**(RULE,`Retrieve`)—— 逐 query 联网搜索 + 抓正文,产原始片段。复用 `services/_core/agent` 的 WebSearch/WebFetch(`sources/web.py` 薄封装,noop bus 同步调,`OMNI_WEB_SEARCH_DRY_RUN=1` 离线 mock)。
3. **synthesize**(LLM,`Synthesize`)—— 性价比模型(`runtime/llm/structured.call_json`,默认 deepseek-v4-pro)据片段综合成带来源、不打分的结论;**只认片段、不编造**,无支撑的进"还没覆盖的角度";失败降级仍落库。
4. **library_write**(RULE,`LibraryWrite`)—— 组装 record,**去重累积 upsert** 进统一库(`library.py`,topic_norm 为查重键,同题增量合并 findings/sources/keywords,richness 单增,墓碑软删),渲 `report.md`。

**统一研究库**:`data/domains/research/library/records.jsonl`(append-only,最新行权威)+ `index.json`(topic_norm/keyword→record_id)。`omni research library [--topic X]` 看累积/查同题。

验证(`OMNI_WEB_SEARCH_DRY_RUN=1`):首跑 dup=False;同题再跑 dup=True、record_id 不变、增量合并 —— 重复调研被挡住。

</details>

## 设计取舍(已定)

- 苦力一律便宜模型;**挑刺/核源**那步(待加)上中端 `qwen3.6-plus`。
- 研究库先 JSONL+倒排,不上向量;库大了(几百条+)再加语义近邻。
- 顺藤多轮**有界**(默认深度上限 + 收益递减),不做无界收敛。
- 独立 research domain,不塞进 absorption(那个学 AI 编码工具,定位不同)。
- 发布走 curated + **用户自己的a cloud provider服务器**,不用 GitHub Pages。

## 待加(下一刀,按序)

1. **STORM 式召回展开**:`query_expander`(便宜模型)产多关键词/别名/多视角 + 显式覆盖账本(`coverage/<topic>.json`,记"查过哪些词/还没覆盖哪些角度")。直击用户痛点:别因术语/别名没对上漏掉较新/冷门但有效的方案。
2. **顺藤摸瓜多轮**:retrieve 产 frontier_terms,`frontier_gate` 判是否再跑一轮(有界)。
3. **多源可插拔**:`source_router` 按题型(学术/论坛/新闻/文档)选源;新源按 `SingleToolRouter` 加,自动注册。先补 Serper/Tavily(召回质量,**需用户给 key**)、arxiv/Semantic Scholar(学术)。
4. **claim 挑刺核源**:`claim_verifier`(中端模型,复用 `report_author` 的强制 web_fetch 验真骨架),对每条结论抽断言→独立抓原始来源→判 supported/unsupported,SCATTER 批量。
5. **语义查重**:确定性命中候选后,便宜模型判 same/partial/different;partial 进增量调研只补缺的角度。
6. **发布**:record→markdown(导览三件套)→curated→`personal_site`(补 `PersonalSiteChannelAdapter` stub)→ rsync 到用户服务器。

## 复用的现成积木(file:line 见摸查报告)

LLM 苦力 `runtime/llm/structured.call_json` · 批量并行 `runtime/llm/batch.run_parallel_items` · 联网 `services/_core/agent/routers/web_search|web_fetch` · domain 样板 vilo · map-reduce `protocol/team.NodeKind.SCATTER`(召回扇出/批挑刺的原生落点)· 去重范式 `material_registry._dedup` · 发布链 `packages/domains/personal_site`。
