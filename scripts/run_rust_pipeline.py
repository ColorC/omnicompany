"""Rust 管线翻译 — 通过 lang-rewrite DAG 管线将 Python 引擎层翻译为 Rust

复用 TS 管线的全部 DAG 结构，差异仅在 bindings 参数：
  target_lang = "rust"
  work_dir    = data/rewrite/rs_phase1/  (带 Cargo.toml)
  rs_dir      = data/rewrite/rs_phase1/  (SupplyScanner 扫 .rs 文件)

翻译顺序（从简到难，无 async）：
  bus/memory.py → bus/sqlite.py → runtime/router.py → runtime/runner.py

输出到 data/rewrite/rs_phase1/src/{module}.rs
编译验证：cargo check（TypeCheckerRouter 自动写 lib.rs 声明）
风格验证：cargo clippy -- -D warnings（StyleCheckerRouter）
"""

import asyncio
import pathlib
import subprocess
import time
import logging

from dotenv import load_dotenv
load_dotenv()

logging.basicConfig(level=logging.WARNING, format='%(message)s')

from omnicompany.packages.domains.software_engineering.lang_rewrite.pipeline import build_pipeline
from omnicompany.packages.domains.software_engineering.lang_rewrite.run import build_bindings
from omnicompany.runtime.exec.runner import PipelineRunner
from omnicompany.bus.memory import MemoryBus

RS_DIR = pathlib.Path('data/rewrite/rs_phase1')
RS_DIR.mkdir(parents=True, exist_ok=True)
(RS_DIR / 'src').mkdir(exist_ok=True)

# Phase 2: 协议层 + 原语层 + bus基类（纯类型/trait，最简单）
# Phase 3: runtime 基础设施（llm, tool_executor, registry, embedding, self_types）
MODULES = [
    # -- Phase 2a: primitives（从简到难）--
    'src/omnicompany/primitives/signal.py',
    'src/omnicompany/primitives/hook.py',
    'src/omnicompany/primitives/node.py',
    'src/omnicompany/primitives/tool.py',
    'src/omnicompany/primitives/intent.py',
    # -- Phase 2b: protocol --
    'src/omnicompany/protocol/events.py',
    'src/omnicompany/protocol/format.py',
    'src/omnicompany/protocol/anchor.py',
    'src/omnicompany/protocol/pipeline.py',
    'src/omnicompany/protocol/registry.py',
    'src/omnicompany/protocol/state.py',
    # -- Phase 2c: bus 基类 --
    'src/omnicompany/bus/base.py',
    'src/omnicompany/bus/client.py',
    # -- Phase 3: runtime 基础 --
    'src/omnicompany/runtime/self_types.py',
    'src/omnicompany/runtime/embedding_client.py',
    'src/omnicompany/runtime/registry.py',
    'src/omnicompany/runtime/llm.py',
    'src/omnicompany/runtime/tool_executor.py',
]

results: list[tuple] = []
t_total = time.time()

pipeline = build_pipeline()
bindings = build_bindings({
    'target_lang': 'rust',
    'work_dir': str(RS_DIR),
    'rs_dir': str(RS_DIR),
})

print(f"Pipeline nodes: {[n.id for n in pipeline.nodes]}")
print(f"idiom_translator in-degree: {PipelineRunner(pipeline=pipeline, bindings=bindings, bus=MemoryBus())._in_degree.get('idiom_translator')}")


async def run_module(mod: str):
    name = mod.split('/')[-1]
    stem = name.replace('.py', '')
    t0 = time.time()
    print(f'\n{"=" * 55}')
    print(f'Module: {name} (Rust)')
    print(f'{"=" * 55}')

    bus = MemoryBus()
    runner = PipelineRunner(
        pipeline=pipeline,
        bindings=bindings,
        bus=bus,
        max_steps=20,
    )

    result = await runner.run({
        'source_path': mod,
        'target_lang': 'rust',
    })

    elapsed = time.time() - t0

    if result is None:
        print(f'  FAIL: pipeline returned None')
        results.append((name, 'FAIL-pipeline', 'None result', elapsed))
        return

    generated_code = result.get('generated_code', '') if isinstance(result, dict) else ''
    if not generated_code:
        print(f'  FAIL: no generated_code in result')
        print(f'  result keys: {list(result.keys()) if isinstance(result, dict) else type(result)}')
        results.append((name, 'FAIL-no-code', str(result)[:200], elapsed))
        return

    print(f'  translate: PASS ({elapsed:.1f}s, {len(generated_code)} chars)')

    # 将生成代码写入 rs_phase1/src/{stem}.rs（此脚本是 src/ 的权威管理者）
    src_dir = RS_DIR / 'src'
    src_dir.mkdir(exist_ok=True)
    rs_file = src_dir / f'{stem}.rs'
    rs_file.write_text(generated_code, encoding='utf-8')

    # 更新 lib.rs 声明（累积模式：每个模块翻译后追加）
    lib_rs = src_dir / 'lib.rs'
    mod_decl = f'pub mod {stem};\n'
    if lib_rs.exists():
        lib_content = lib_rs.read_text(encoding='utf-8')
        if mod_decl.strip() not in lib_content:
            lib_rs.write_text(lib_content + mod_decl, encoding='utf-8')
    else:
        lib_rs.write_text(mod_decl, encoding='utf-8')

    print(f'  wrote: {rs_file}')

    # archive 副本
    out_dir = pathlib.Path('data/rewrite/rs_phase3_pipeline')
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / f'{stem}.rs'
    out_file.write_text(generated_code, encoding='utf-8')

    # 最终 cargo check — 检查所有已翻译模块累积编译（真实验证）
    import os as _os
    _home = _os.path.expanduser("~")
    _rust_path = _os.pathsep.join([
        _os.path.join(_home, ".cargo", "bin"),
        _os.path.join(_home, "mingw64", "mingw64", "bin"),
    ])
    _env = {**_os.environ, "PATH": _rust_path + _os.pathsep + _os.environ.get("PATH", "")}
    verify = subprocess.run(
        'cargo check',
        capture_output=True, text=True, timeout=120,
        cwd=str(RS_DIR), shell=True,
        encoding='utf-8', errors='replace',
        env=_env,
    )
    total_elapsed = time.time() - t0
    if verify.returncode == 0:
        warnings = [l for l in (verify.stderr or '').splitlines() if l.startswith('warning')]
        warn_note = f' ({len(warnings)} warnings)' if warnings else ''
        print(f'  cargo check: PASS{warn_note} ({total_elapsed:.1f}s)')
        results.append((name, 'PASS', f'{len(generated_code)}ch', total_elapsed))
    else:
        err = (verify.stderr or verify.stdout)[:1000]
        # encode/decode to strip chars GBK terminal can't handle
        err_safe = err.encode('ascii', errors='replace').decode('ascii')
        print(f'  cargo check: FAIL')
        for line in err_safe.splitlines()[:15]:
            print(f'    {line}')
        results.append((name, 'FAIL-cargo', err_safe[:100], total_elapsed))


async def main():
    for mod in MODULES:
        await run_module(mod)

    total = time.time() - t_total
    print(f'\n{"=" * 55}')
    print(f'Rust Pipeline RESULTS ({total:.0f}s total):')
    for name, status, detail, t in results:
        print(f'  [{status}] {name:25s} {detail} ({t:.0f}s)')


asyncio.run(main())
