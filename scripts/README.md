# scripts/

## 目录结构

```
scripts/
├── experiment_v3.py          主实验入口（BigCodeBench 自举进化）
│
├── diag/                     诊断 / 查询 / 内省工具
│   ├── inspect_dag.py        三层 DAG Router 注册内省
│   ├── inspect_dbs.py        route_graph.db / intent_traces.db 内容查看
│   ├── query_errors.py       从 events.db 查询 LLM 错误详情
│   ├── query_evo.py          查询进化状态 (mutation_state)
│   ├── query_round.py        按轮次查询任务执行详情
│   ├── query_task6.py        查询 BigCodeBench/6 专项数据
│   ├── show_rules.py         显示条件规则 (ConditionalRule) 详情
│   └── smoke.py              Anthropic API 连通性测试
│
├── analysis/                 分析与报告
│   ├── ab_report.py          A/B 实验（有/无 route hints）对比报告
│   ├── analyze_experiment.py intent_traces.db 实验轨迹分析
│   ├── analyze_routes.py     route_graph.db 节点与成功率分析
│   ├── analyze_run.py        checkpoint 中每轮执行细节解析
│   ├── check_progress.py     过夜进化实验进度检查
│   ├── precision_run.py      单次精密执行 + 完整链路追踪
│   ├── review_all.py         violations / action_class 汇总统计
│   └── semantic_analysis.py  从 precision_run.log 提取泛化语义教训
│
├── runners/                  运行入口 / 守护进程
│   ├── guardian.py           多目标统一守护进程（swe/bigcode/unity/battle）
│   ├── meta_evolve.py        元进化主循环（SWE-bench Docker）
│   ├── overnight_evolution.py 过夜进化实验闭环
│   ├── swe_run_task.py       单个 SWE-bench 任务执行
│   └── watchdog_evolve.sh    meta_evolve.py 看门狗脚本
│
├── integration/              外部集成
│   ├── feishu_im.py          协作平台 IM 命令行工具
│   └── feishu_oauth.py       协作平台 OAuth 授权
│
├── test_scripts/             手动测试脚本（非 pytest）
│   ├── test_context.py       ContextRouter + LLM 调用验证
│   ├── test_docker_exec.py   Docker exec 连通性验证
│   ├── test_editor_container.py str_replace_editor 容器内验证
│   ├── test_intent_v1.py     V1 意图轨迹采集验证（5 任务）
│   ├── test_intent_v1_tasks.py V1 多任务验证（15 任务）
│   ├── test_intent_v2_hard.py V2 高难度 + 路由提示注入验证
│   └── trace_agent.py        从 meta_task_*.db 打印 agent 步骤
│
├── archive/                  已归档的旧实验
└── evolution_lab/            进化实验室（独立问题集 + runner）
```

## 常用命令

```bash
# 主实验
python scripts/experiment_v3.py --rounds 5 --tasks-per-round 5 --max-steps 200

# 查看 DAG 注册
python scripts/diag/inspect_dag.py
python scripts/diag/inspect_dag.py --verbose --layer runtime

# 诊断查询
python scripts/diag/query_errors.py data/exp_v3_events.db
python scripts/diag/show_rules.py
```
