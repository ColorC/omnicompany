# [OMNI] origin=claude-code domain=software_engineering/lang_rewrite_verifier ts=2026-04-08T03:23:42Z
# [OMNI] migrated 2026-05-03: 旧 omnicompany.runtime.agent.agent_node_loop.AgentNodeLoop 已 deprecate, 现用 packages.services._core.agent.AgentNodeLoop (router 化新基础设施).
# [OMNI] material_id="material:domains.software_engineering.lang_rewrite_verifier.smoke_routers.implementation.py"
"""lang_rewrite_verifier.routers — 冒烟测试生成 + 执行

两个节点：

  SmokeTestGeneratorRouter (AgentNodeLoop)
    全局阅读翻译后的 Rust 项目，生成有针对性的冒烟测试套件。
    FORMAT_IN:  rewrite.verified-code
    FORMAT_OUT: smoke.test-suite

  SmokeRunnerRouter (HARD Router)
    顺序执行测试套件，第一个 fatal 失败即停并打包 debug.error-report。
    FORMAT_IN:  smoke.test-suite
    FORMAT_OUT: smoke.result (PASS) / debug.error-report (FAIL)
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any, ClassVar

from omnicompany.protocol.anchor import Verdict, VerdictKind
from omnicompany.runtime.agent.agent_loop_config import (
    CompactConfig,
    LoopConfig,
    PermissionConfig,
)
from omnicompany.runtime.routing.router import Router

from omnicompany.packages.services._core.agent import (
    AgentNodeLoop,
    DevBashRouter,
    GlobRouter,
    GrepRouter,
    ReadFileRouter,
)
from omnicompany.packages.services._core.agent.routers.prompt_builder import PromptBuilderRouter
from omnicompany.packages.services._core.agent.routers.extract_result import ExtractResultRouter

DOMAIN = "smoke"


# ── SmokeTestGeneratorRouter ──────────────────────────────────────────────────


_NODE_PROMPT = """\
你是一个 Rust 项目测试专家。你收到的是一个刚从 Python 翻译到 Rust 的项目。
你的任务：分析项目结构和核心功能，生成一套从简到繁的冒烟测试用例。

【工作步骤】
1. 读取 Cargo.toml：确认 crate 类型（[[bin]] 还是 [lib]）、依赖、features
2. 读取 src/main.rs 或 src/lib.rs：了解入口逻辑和公开接口
3. 用 glob 浏览 src/ 下所有 .rs 文件，选择关键文件深入阅读
4. 理解核心数据流：输入是什么，经过什么处理，输出是什么
5. 思考：哪些路径是"能跑起来"的最小验证集？

【输出格式】
通过 finish 工具输出以下 JSON（message 字段）：

```json
{
  "work_dir": "<项目根目录绝对路径>",
  "compile_command": "cargo build",
  "test_cases": [
    {
      "id": "build",
      "description": "编译通过",
      "cmd": "cargo build",
      "success_pattern": "Finished",
      "timeout_secs": 120,
      "fatal": true
    },
    {
      "id": "smoke_run",
      "description": "基础运行：调用 finish",
      "cmd": "cargo run -- \"<符合项目实际用法的参数>\"",
      "success_pattern": "<期望出现在 stdout/stderr 中的字符串>",
      "timeout_secs": 60,
      "fatal": true
    }
  ]
}
```

【规则】
- build 用例永远第一，fatal=true
- 如果是 lib crate（Cargo.toml 无 [[bin]]），不生成 cargo run 用例，改用 cargo test
- cmd 必须是可在 work_dir 下直接执行的完整 shell 命令
- success_pattern 要基于你对代码的实际理解，不要用"OK"这种通用词
- 用例数 3-7 个，宁少勿多，聚焦核心路径
- fatal=false 表示此用例失败不阻断后续用例（用于非关键路径）
"""


class _SmokeTestPromptBuilder(PromptBuilderRouter):
    """冒烟测试生成 agent 自定义首条 user 消息 (拼 work_dir / source_file / target_lang)."""

    def build_initial_messages(self, input_data: dict) -> list[dict]:
        work_dir = input_data.get("work_dir", "")
        rs_dir = input_data.get("rs_dir", work_dir)
        source_file = input_data.get("source_file", "")
        target_lang = input_data.get("target_lang", "rust")

        lines = []
        project_path = rs_dir or work_dir
        if project_path:
            lines.append(f"翻译完成的 Rust 项目位于: {project_path}")
        if source_file:
            lines.append(f"原始 Python 源文件: {source_file}")
        if target_lang and target_lang != "rust":
            lines.append(f"目标语言: {target_lang}")
        lines.append("")
        lines.append("请探查该项目，理解其核心功能，生成冒烟测试套件。")
        lines.append("完成后用 finish 工具输出 JSON 格式的测试套件。")

        return [{"role": "user", "content": "\n".join(lines)}]


class _SmokeTestExtractResult(ExtractResultRouter):
    """冒烟测试 agent 自定义产物提取 — 剥 markdown fence + parse JSON, 校验 test_cases 非空."""

    def extract(
        self,
        *,
        final_text: str,
        messages: list[dict],
        turn_count: int,
        stop_reason: str,
    ) -> Verdict:
        text = (final_text or "").strip()

        # 剥离 markdown 代码围栏
        if "```" in text:
            for part in text.split("```"):
                stripped = part.strip()
                if stripped.startswith("json"):
                    text = stripped[4:].strip()
                    break
                elif stripped.startswith("{"):
                    text = stripped
                    break

        try:
            suite = json.loads(text)
        except Exception as e:
            return Verdict(
                kind=VerdictKind.FAIL,
                output={"error": f"测试套件 JSON 解析失败: {e}", "raw": text[:500]},
                diagnosis=f"SmokeTestGenerator 输出无法解析为 JSON: {e}",
            )

        test_cases = suite.get("test_cases", [])
        if not test_cases:
            return Verdict(
                kind=VerdictKind.FAIL,
                output={"error": "test_cases 为空"},
                diagnosis="SmokeTestGenerator 未生成任何测试用例",
            )

        return Verdict(
            kind=VerdictKind.PASS,
            output={
                "work_dir": suite.get("work_dir", ""),
                "compile_command": suite.get("compile_command", "cargo build"),
                "test_cases": test_cases,
            },
            diagnosis=f"生成 {len(test_cases)} 个冒烟测试用例",
        )


class SmokeTestGeneratorRouter(AgentNodeLoop):
    """AgentNodeLoop (router 化, 2026-05-03 迁): 全局阅读翻译后的 Rust 项目, 生成冒烟测试套件.

    拥有完整的项目视角：读 Cargo.toml、src/*.rs、理解核心接口，
    然后从简到繁生成 3-7 个测试用例。
    """

    FORMAT_IN = "rewrite.verified-code"
    FORMAT_OUT = f"{DOMAIN}.test-suite"
    DESCRIPTION = "AgentNodeLoop: 读取 Rust 项目结构，生成针对性冒烟测试套件"

    NODE_PROMPT: ClassVar[str] = _NODE_PROMPT
    TOOL_ROUTERS: ClassVar[list] = [ReadFileRouter, GrepRouter, GlobRouter, DevBashRouter]
    LOOP_CONFIG: ClassVar[LoopConfig] = LoopConfig(
        max_turns=20,
        compact=CompactConfig(auto_compact_enabled=False),
        permission=PermissionConfig(mode="readonly"),
    )

    def __init__(
        self,
        *,
        model: str | None = None,
        bus: Any | None = None,
        config: LoopConfig | None = None,
    ):
        super().__init__(model=model, bus=bus, config=config or self.LOOP_CONFIG)

    # ── 子类钩子: 自定义 PromptBuilder + ExtractResult + tool context (work_dir → bash root) ──

    def build_prompt_builder(self, *, bus: Any) -> PromptBuilderRouter:
        return _SmokeTestPromptBuilder(template=self.NODE_PROMPT, bus=bus)

    def build_extract_result(self, *, bus: Any) -> ExtractResultRouter:
        return _SmokeTestExtractResult(bus=bus)

    def build_tool_context(self, *, input_data: dict, turn: int, trace_id: str) -> dict:
        # DevBashRouter 要求 cwd 必须在 allowed_bash_roots 内. 这里用 input 的 work_dir/rs_dir
        # 作为根 (Rust 项目根, agent 在里面跑 cargo build).
        work_dir = input_data.get("rs_dir") or input_data.get("work_dir") or ""
        roots: tuple[str, ...] = (work_dir,) if work_dir else ()
        return {
            "trace_id": trace_id,
            "turn_number": turn,
            "allowed_bash_roots": roots,
        }


# ── SmokeRunnerRouter ─────────────────────────────────────────────────────────


class SmokeRunnerRouter(Router):
    """HARD：顺序执行冒烟测试用例。

    遇到第一个 fatal=true 的失败用例即停止，将失败信息打包成
    debug.error-report 格式（含 language="rust"、source_files、
    compile_command）交给 debugger 管线处理。

    全部通过 → PASS（管线 EMIT）。
    """

    FORMAT_IN = f"{DOMAIN}.test-suite"
    FORMAT_OUT = f"{DOMAIN}.result"
    DESCRIPTION = "顺序运行冒烟测试，失败时打包 debug.error-report 进入 debugger"

    def run(self, input_data: dict) -> Verdict:
        work_dir: str = input_data.get("work_dir", "")
        test_cases: list[dict] = input_data.get("test_cases", [])
        compile_command: str = input_data.get("compile_command", "cargo build")

        if not test_cases:
            return Verdict(
                kind=VerdictKind.FAIL,
                output={**input_data, "error": "test_cases 为空"},
                diagnosis="没有测试用例可运行",
            )

        cwd = Path(work_dir) if work_dir else None

        # 预先读取所有源文件，供 debug.error-report 使用
        source_files: dict[str, str] = {}
        if cwd and cwd.is_dir():
            for rs_file in sorted(cwd.glob("src/**/*.rs")):
                try:
                    rel = str(rs_file.relative_to(cwd))
                    source_files[rel] = rs_file.read_text(encoding="utf-8", errors="replace")
                except Exception:
                    pass
            for extra in ("Cargo.toml", "Cargo.lock"):
                p = cwd / extra
                if p.exists():
                    try:
                        source_files[extra] = p.read_text(encoding="utf-8", errors="replace")
                    except Exception:
                        pass

        passed_cases: list[str] = []

        for case in test_cases:
            case_id: str = case.get("id", "unknown")
            cmd: str = case.get("cmd", "")
            success_pattern: str = case.get("success_pattern", "")
            timeout_secs: int = int(case.get("timeout_secs", 60))
            fatal: bool = bool(case.get("fatal", True))
            description: str = case.get("description", cmd)

            if not cmd:
                continue

            output = ""
            success = False
            try:
                result = subprocess.run(
                    cmd,
                    shell=True,
                    capture_output=True,
                    text=True,
                    timeout=timeout_secs,
                    cwd=str(cwd) if cwd else None,
                    encoding="utf-8",
                    errors="replace",
                )
                output = (result.stdout or "") + (result.stderr or "")
                success = result.returncode == 0
                if success and success_pattern:
                    success = success_pattern in output
            except subprocess.TimeoutExpired:
                output = f"[TIMEOUT after {timeout_secs}s]"
            except Exception as e:
                output = str(e)

            if success:
                passed_cases.append(case_id)
            elif fatal:
                # 打包 debug.error-report，透传 work_dir / compile_command
                # 让 TesterRouter 用同一条命令来验证修复是否生效
                return Verdict(
                    kind=VerdictKind.FAIL,
                    output={
                        # 透传上游字段（去掉 test_cases，避免混淆）
                        **{k: v for k, v in input_data.items() if k != "test_cases"},
                        # debug.error-report 必要字段
                        "language": "rust",
                        "error_text": output[:4000],
                        "compile_command": cmd,          # TesterRouter 用此命令验证
                        "work_dir": str(cwd) if cwd else "",
                        "source_files": source_files,
                        # 额外上下文
                        "failed_case_id": case_id,
                        "failed_case_description": description,
                        "passed_cases": passed_cases,
                        "all_test_cases": test_cases,
                    },
                    diagnosis=f"冒烟测试 [{case_id}] {description} 失败: {output[:200]}",
                )
            # fatal=False：记录失败但继续

        return Verdict(
            kind=VerdictKind.PASS,
            output={
                **input_data,
                "passed_cases": [c.get("id") for c in test_cases],
                "smoke_passed": True,
            },
            diagnosis=f"全部 {len(test_cases)} 个冒烟测试通过",
        )
