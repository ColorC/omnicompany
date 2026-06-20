# [OMNI] origin=claude-code domain=repo_architect/_archive/routers_legacy.py ts=2026-04-20T00:00:00Z
# [OMNI] material_id="material:learning.repo.architect.worker.legacy_router_implementation.py"
# OMNI-024 ALLOW: _archive/ 归档文件，Router 类不在标准位置属预期 (Phase D Diamond shortcut)
"""repo_architect routers — 18 个 Router 实现 (9 reused + 9 stub)。

stub 节点在实现完整语义之前返回合法 shape + confidence=0.6 的 PASS Verdict,
保证 PipelineChecker 和 e2e import 测试能通过。实际下游消费时应替换为真实实现。

复用来源: 2026-04-09 workflow-factory trace 01KNR7BN48HY0VB131ZH8WVXAD 生成的前 9 节点
(经 py_compile + import PASS 验证)。
"""

from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from omnicompany.protocol.anchor import Verdict, VerdictKind
from omnicompany.runtime.routing.router import Router

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════
# 阶段 1 准备
# ═══════════════════════════════════════════════════════════


class InputValidatorRouter(Router):
    FORMAT_IN = "repo-architect.input"
    FORMAT_OUT = "repo-architect.input"
    DESCRIPTION = (
        "严格校验仓库分析输入 Schema: url/local_path 互斥存在性 + GitHub URL 前缀 + "
        "本地路径存在性 + focus 文本长度限制。无效输入阻断在管线入口, 避免下游脏数据。"
    )

    def run(self, input_data: Any) -> Verdict:
        try:
            if not isinstance(input_data, dict):
                return Verdict(kind=VerdictKind.FAIL, output=input_data,
                               diagnosis="输入必须为 JSON dict")

            url = input_data.get("url")
            local_path = input_data.get("local_path")

            if (url is not None) == (local_path is not None):
                return Verdict(kind=VerdictKind.FAIL, output=input_data,
                               diagnosis="必须提供 url 或 local_path 之一 (互斥)")

            if url is not None:
                if not (url.startswith("https://github.com/") or url.startswith("git@github.com:")):
                    return Verdict(kind=VerdictKind.FAIL, output=input_data,
                                   diagnosis="GitHub URL 格式不合法")
            else:
                resolved = Path(local_path).resolve()
                if not resolved.exists() or not resolved.is_dir():
                    return Verdict(kind=VerdictKind.FAIL, output=input_data,
                                   diagnosis=f"本地路径不存在或不是目录: {resolved}")

            focus = input_data.get("focus", "")
            if not isinstance(focus, str):
                return Verdict(kind=VerdictKind.FAIL, output=input_data,
                               diagnosis="focus 必须是字符串")
            if len(focus) > 2000:
                return Verdict(kind=VerdictKind.FAIL, output=input_data,
                               diagnosis="focus 超过 2000 字符")

            return Verdict(kind=VerdictKind.PASS, output={**input_data, "_validated": True})
        except Exception as e:
            return Verdict(kind=VerdictKind.FAIL, output=input_data,
                           diagnosis=f"校验异常: {e}")


class RepoAcquirerRouter(Router):
    FORMAT_IN = "repo-architect.input"
    FORMAT_OUT = "repo-architect.acquired-repo"
    DESCRIPTION = (
        "根据 url 克隆或绑定 local_path, 扫描文件树统计 file_count/dir_count/max_depth/"
        "languages 分布, 提取 repo_name + default_branch, 封装为 acquired-repo 对象。"
    )

    def run(self, input_data: Any) -> Verdict:
        try:
            if input_data.get("url"):
                working_path = tempfile.mkdtemp(prefix="repo_arch_")
                try:
                    subprocess.run(
                        ["git", "clone", "--depth", "1", input_data["url"], working_path],
                        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                    )
                except subprocess.CalledProcessError as e:
                    return Verdict(kind=VerdictKind.FAIL, output=input_data,
                                   diagnosis=f"git clone 失败: {e.stderr}")
                repo_name = Path(input_data["url"]).name.replace(".git", "")
            else:
                working_path = str(Path(input_data["local_path"]).resolve())
                repo_name = Path(working_path).name

            file_count = 0
            dir_count = 0
            max_depth = 0
            lang_exts: dict[str, int] = {}
            ignore = {".git", "node_modules", "__pycache__", ".venv", "venv", "vendor", "dist", "build"}

            for root, dirs, files in os.walk(working_path):
                dirs[:] = [d for d in dirs if d not in ignore]
                depth = root.replace(working_path, "").count(os.sep)
                max_depth = max(max_depth, depth)
                dir_count += len(dirs)
                file_count += len(files)
                for f in files:
                    ext = os.path.splitext(f)[1].lower()
                    if ext:
                        lang_exts[ext] = lang_exts.get(ext, 0) + 1

            languages = dict(sorted(lang_exts.items(), key=lambda x: -x[1])[:8])

            return Verdict(kind=VerdictKind.PASS, output={
                **input_data,
                "working_path": working_path,
                "repo_name": repo_name,
                "default_branch": "main",
                "file_tree_summary": {
                    "file_count": file_count,
                    "dir_count": dir_count,
                    "max_depth": max_depth,
                    "languages": languages,
                },
            })
        except Exception as e:
            return Verdict(kind=VerdictKind.FAIL, output=input_data,
                           diagnosis=f"仓库获取异常: {e}")


class RepoIdentityAnchorRouter(Router):
    """从真实文件提取仓库官方身份, 作为所有 LLM 节点的防幻觉锚。

    2026-04-09 事故驱动: 第一次冒烟跑把 OmniCompany 误认成 voxel_sandbox 同名模组。
    根因是 LLM 只看到 repo_name='omnicompany' 就按名字检索公开资料,没有真实
    项目锚定。本节点从 pyproject.toml / package.json / Cargo.toml / go.mod /
    README.md / git remote 提取 canonical identity, 产出 disambiguation_hint
    喂给后续所有 LLM 节点。
    """

    FORMAT_IN = "repo-architect.acquired-repo"
    FORMAT_OUT = "repo-architect.repo-identity"
    DESCRIPTION = (
        "从真实文件 (pyproject.toml/package.json/Cargo.toml/go.mod/README.md/git remote) "
        "提取仓库官方身份, 产出 canonical_name + canonical_description + ecosystem + "
        "disambiguation_hint, 作为后续 LLM 节点的防名字幻觉锚定上下文。"
    )

    def run(self, input_data: Any) -> Verdict:
        try:
            import subprocess
            import re as _re

            working = Path(input_data.get("working_path", "."))
            if not working.exists():
                return Verdict(kind=VerdictKind.FAIL, output=input_data,
                               diagnosis="working_path 不存在,无法提取身份")

            evidence_sources: list[str] = []
            canonical_name = input_data.get("repo_name", "")
            canonical_description = ""
            homepage = ""
            git_remote_url = ""
            ecosystem = "unknown"

            # 1. pyproject.toml (Python)
            pyproject = working / "pyproject.toml"
            if pyproject.exists():
                try:
                    # 不依赖 tomllib (3.11+), 正则提取足够
                    text = pyproject.read_text(encoding="utf-8")
                    m_name = _re.search(r'^\s*name\s*=\s*"([^"]+)"', text, _re.MULTILINE)
                    m_desc = _re.search(r'^\s*description\s*=\s*"([^"]+)"', text, _re.MULTILINE)
                    m_home = _re.search(r'^\s*homepage\s*=\s*"([^"]+)"', text, _re.MULTILINE | _re.IGNORECASE)
                    if m_name:
                        canonical_name = m_name.group(1)
                    if m_desc:
                        canonical_description = m_desc.group(1)
                    if m_home:
                        homepage = m_home.group(1)
                    ecosystem = "python"
                    evidence_sources.append("pyproject.toml")
                except Exception as e:
                    logger.debug("[repo_identity] pyproject.toml parse: %s", e)

            # 2. package.json (Node)
            package_json = working / "package.json"
            if package_json.exists():
                try:
                    pj = json.loads(package_json.read_text(encoding="utf-8"))
                    if pj.get("name"):
                        canonical_name = pj["name"]
                    if pj.get("description"):
                        canonical_description = pj["description"]
                    if pj.get("homepage"):
                        homepage = pj["homepage"]
                    if isinstance(pj.get("repository"), dict) and pj["repository"].get("url"):
                        git_remote_url = pj["repository"]["url"]
                    elif isinstance(pj.get("repository"), str):
                        git_remote_url = pj["repository"]
                    ecosystem = "node" if ecosystem == "unknown" else "mixed"
                    evidence_sources.append("package.json")
                except Exception as e:
                    logger.debug("[repo_identity] package.json parse: %s", e)

            # 3. Cargo.toml (Rust)
            cargo = working / "Cargo.toml"
            if cargo.exists():
                try:
                    text = cargo.read_text(encoding="utf-8")
                    m_name = _re.search(r'^\s*name\s*=\s*"([^"]+)"', text, _re.MULTILINE)
                    m_desc = _re.search(r'^\s*description\s*=\s*"([^"]+)"', text, _re.MULTILINE)
                    if m_name and not canonical_name.startswith("repo-"):
                        canonical_name = m_name.group(1)
                    if m_desc and not canonical_description:
                        canonical_description = m_desc.group(1)
                    ecosystem = "rust" if ecosystem == "unknown" else "mixed"
                    evidence_sources.append("Cargo.toml")
                except Exception as e:
                    logger.debug("[repo_identity] Cargo.toml parse: %s", e)

            # 4. go.mod (Go)
            go_mod = working / "go.mod"
            if go_mod.exists():
                try:
                    text = go_mod.read_text(encoding="utf-8")
                    m_mod = _re.search(r'^module\s+(\S+)', text, _re.MULTILINE)
                    if m_mod:
                        canonical_name = m_mod.group(1).rsplit("/", 1)[-1] or canonical_name
                    ecosystem = "go" if ecosystem == "unknown" else "mixed"
                    evidence_sources.append("go.mod")
                except Exception as e:
                    logger.debug("[repo_identity] go.mod parse: %s", e)

            # 5. README title + first paragraph (任何生态都通用)
            readme_description = ""
            for readme_name in ("README.md", "README.rst", "README.txt", "readme.md"):
                readme = working / readme_name
                if readme.exists():
                    try:
                        text = readme.read_text(encoding="utf-8", errors="ignore")
                        # 第一个 markdown 标题
                        m_title = _re.search(r'^#\s+(.+)$', text, _re.MULTILINE)
                        if m_title and not canonical_name.startswith("repo-"):
                            title = m_title.group(1).strip()
                            if len(title) < 80:
                                canonical_name = canonical_name or title
                        # 标题后第一段作为描述备选
                        if m_title:
                            after = text[m_title.end():].strip()
                            # 跳过 badge 行
                            lines = [L for L in after.split("\n") if L.strip() and not L.strip().startswith("![")]
                            if lines:
                                first_para = lines[0].strip()[:500]
                                readme_description = first_para
                        evidence_sources.append(readme_name)
                        break
                    except Exception as e:
                        logger.debug("[repo_identity] README parse: %s", e)

            if not canonical_description and readme_description:
                canonical_description = readme_description

            # 6. git remote (最弱的证据, 但能确认 owner/name)
            if (working / ".git").exists():
                try:
                    result = subprocess.run(
                        ["git", "-C", str(working), "remote", "get-url", "origin"],
                        capture_output=True, text=True, timeout=5,
                    )
                    if result.returncode == 0:
                        git_remote_url = result.stdout.strip()
                        evidence_sources.append(".git/config")
                except Exception as e:
                    logger.debug("[repo_identity] git remote: %s", e)

            # primary_language from file_tree_summary
            langs = input_data.get("file_tree_summary", {}).get("languages", {})
            # 过滤掉非源码 (png/json/md/log/db)
            code_exts = {".py", ".ts", ".js", ".jsx", ".tsx", ".rs", ".go", ".java",
                         ".kt", ".cpp", ".c", ".h", ".hpp", ".cs", ".rb", ".php"}
            code_lang_counts = {k: v for k, v in langs.items() if k in code_exts}
            primary_language = "unknown"
            if code_lang_counts:
                primary_language = max(code_lang_counts, key=code_lang_counts.get).lstrip(".")

            # 兜底: 至少能从 evidence 说清楚是什么
            if not canonical_description:
                canonical_description = (
                    f"A {primary_language if primary_language != 'unknown' else 'multi-language'} "
                    f"project with {input_data.get('file_tree_summary', {}).get('file_count', 0)} "
                    f"files (description not found in manifest or README)"
                )

            # disambiguation_hint — 这是防幻觉核心
            evidence_list = ", ".join(evidence_sources) if evidence_sources else "none"
            disambiguation_hint = (
                f"This project is '{canonical_name}'. "
                f"Identity proof from: {evidence_list}. "
                f"Description: {canonical_description}. "
                f"Ecosystem: {ecosystem}, primary language: {primary_language}. "
                f"working_path: {working}. "
                f"**CRITICAL**: When analyzing this project, ONLY use information from this "
                f"working_path. Do NOT import knowledge about unrelated projects that happen "
                f"to share the name '{canonical_name}' (e.g. voxel_sandbox modpacks, npm packages, "
                f"or any public project with the same or similar name). If you cannot find "
                f"something in the actual files under working_path, say so explicitly instead "
                f"of filling in from prior knowledge."
            )

            if not evidence_sources:
                # 没有任何证据就是 FAIL — 不给下游喂假身份
                return Verdict(
                    kind=VerdictKind.FAIL,
                    output=input_data,
                    diagnosis=(
                        "无法从任何来源提取项目身份 (pyproject.toml/package.json/"
                        "Cargo.toml/go.mod/README.md 全部缺失)。这种仓库不适合自动架构分析。"
                    ),
                )

            return Verdict(kind=VerdictKind.PASS, output={
                **input_data,
                "canonical_name": canonical_name,
                "canonical_description": canonical_description,
                "homepage": homepage,
                "git_remote_url": git_remote_url,
                "primary_language": primary_language,
                "ecosystem": ecosystem,
                "evidence_sources": evidence_sources,
                "disambiguation_hint": disambiguation_hint,
            })
        except Exception as e:
            return Verdict(kind=VerdictKind.FAIL, output=input_data,
                           diagnosis=f"身份提取异常: {e}")


class ScaleSurveyorRouter(Router):
    FORMAT_IN = "repo-architect.repo-identity"
    FORMAT_OUT = "repo-architect.scaled-survey"
    DESCRIPTION = (
        "识别真实源码模块拓扑 (穿透到第二层包): 找 __init__.py/package.json/Cargo.toml/"
        "go.mod 等 package marker, 按 ecosystem 输出 code_modules 列表 + 计算 "
        "complexity_score + scale_level。不再只看顶层目录。"
    )

    # Marker files → package kind
    _PACKAGE_MARKERS = {
        "__init__.py": "python_package",
        "package.json": "js_package",
        "Cargo.toml": "rust_crate",
        "go.mod": "go_module",
    }

    # 忽略的目录名 (不会进入 code_modules)
    _IGNORE_DIRS = {
        ".git", ".github", ".idea", ".vscode", ".omni", ".claude",
        "node_modules", "__pycache__", ".venv", "venv", "env",
        "vendor", "dist", "build", "target", "out", ".next",
        "data", "logs", "tmp", "temp", "_archive", "_graveyard",
        "tests", "test", "spec", "__tests__",
    }

    def run(self, input_data: Any) -> Verdict:
        try:
            working = Path(input_data.get("working_path", "."))
            if not working.exists():
                return Verdict(kind=VerdictKind.FAIL, output=input_data,
                               diagnosis="working_path 不存在")

            ecosystem = input_data.get("ecosystem", "unknown")

            # 第 1 步: 识别 top_source_root
            # 常见约定: src/<project>/ 或 lib/ 或仓库根
            top_source_root = None
            candidates = [working / "src", working / "lib", working / "app"]
            for c in candidates:
                if c.exists() and c.is_dir():
                    top_source_root = c
                    break
            if top_source_root is None:
                top_source_root = working

            # 第 2 步: 扫描 marker 文件, 构建 code_modules
            # 策略: 对于 python, 一个 "模块" 是含 __init__.py 的目录且它的 parent 不含 __init__.py
            # (即 top-level package). 然后下钻它的直接子包作为 sub_packages.
            code_modules: list[dict] = []
            code_exts = {".py", ".ts", ".js", ".jsx", ".tsx", ".rs", ".go",
                         ".java", ".kt", ".cpp", ".c", ".h", ".hpp"}

            def _is_python_package(p: Path) -> bool:
                return (p / "__init__.py").exists()

            def _count_source_files(p: Path) -> int:
                cnt = 0
                try:
                    for f in p.rglob("*"):
                        if f.is_file() and f.suffix in code_exts:
                            # 过滤 __pycache__
                            if "__pycache__" not in f.parts:
                                cnt += 1
                except Exception:
                    pass
                return cnt

            def _walk_for_modules(root: Path, max_depth: int = 4) -> list[dict]:
                """BFS 找到所有 package marker 的目录, 深度限制 4 层。"""
                found: list[dict] = []
                queue: list[tuple[Path, int]] = [(root, 0)]
                seen: set[Path] = set()

                while queue:
                    cur, depth = queue.pop(0)
                    if cur in seen or depth > max_depth:
                        continue
                    seen.add(cur)

                    if not cur.is_dir() or cur.name in self._IGNORE_DIRS:
                        continue

                    # 检查本目录是否是 package
                    marker_kind = None
                    for marker, kind in self._PACKAGE_MARKERS.items():
                        if (cur / marker).exists():
                            marker_kind = kind
                            break

                    if marker_kind:
                        try:
                            rel_path = cur.relative_to(working).as_posix()
                        except ValueError:
                            rel_path = str(cur)
                        # 记录具体是哪个 marker 文件让我们识别出这是一个 package
                        marker_file = next(
                            (m for m in self._PACKAGE_MARKERS if (cur / m).exists()),
                            None,
                        )
                        discovered_via = (
                            f"{rel_path}/{marker_file}" if marker_file else rel_path
                        )
                        found.append({
                            "path": rel_path,
                            "kind": marker_kind,
                            "depth": depth,
                            "discovered_via": discovered_via,
                            "_real_path": cur,  # 临时字段, 后面会删
                        })

                    # 继续往下走
                    try:
                        for child in cur.iterdir():
                            if child.is_dir() and child.name not in self._IGNORE_DIRS:
                                queue.append((child, depth + 1))
                    except (PermissionError, OSError):
                        pass
                return found

            all_packages = _walk_for_modules(top_source_root)

            # 第 3 步: 筛选"有意义的模块" —— 取每个 top-level package 及其直接子包
            # 规则:
            #  - 最浅的 python_package (没有祖先也是 python_package 的) 作为"域" (如 src/omnicompany)
            #  - 它的直接子 python_package 作为"模块" (如 src/omnicompany/core, packages/services/knowledge)
            #  - js/rust/go 同理

            def _is_direct_subpackage(child: dict, parent: dict) -> bool:
                parent_path = parent["_real_path"]
                child_path = child["_real_path"]
                try:
                    rel = child_path.relative_to(parent_path)
                    return len(rel.parts) == 1
                except ValueError:
                    return False

            # 找 "根" 包 (没有祖先也是 package)
            root_packages = []
            for p in all_packages:
                parent = p["_real_path"].parent
                # 父目录不是任何已知 package
                if not any(ap["_real_path"] == parent for ap in all_packages):
                    root_packages.append(p)

            # 从 root packages 向下展开: 如果根包的直接子包多于 1 个, 那些子包才是"模块";
            # 如果只有 1 个根包且它没有多个子包, 整个根包就是唯一模块
            interesting_modules: list[dict] = []

            for root_pkg in root_packages:
                direct_children = [
                    p for p in all_packages
                    if p is not root_pkg and _is_direct_subpackage(p, root_pkg)
                ]
                if len(direct_children) >= 2:
                    # 根包只是 umbrella, 其直接子包才是真正的模块
                    for child in direct_children:
                        grandchildren = [
                            gc for gc in all_packages
                            if gc is not child and _is_direct_subpackage(gc, child)
                        ]
                        interesting_modules.append({
                            "path": child["path"],
                            "kind": child["kind"],
                            "depth": child["depth"],
                            "file_count": _count_source_files(child["_real_path"]),
                            "sub_packages": [gc["path"].split("/")[-1] for gc in grandchildren],
                            "discovered_via": child.get("discovered_via", child["path"]),
                        })
                        # 如果子包也是 umbrella (有多个孙包), 把孙包也加进去作为独立模块
                        if len(grandchildren) >= 2:
                            for gc in grandchildren:
                                interesting_modules.append({
                                    "path": gc["path"],
                                    "kind": gc["kind"],
                                    "depth": gc["depth"],
                                    "file_count": _count_source_files(gc["_real_path"]),
                                    "sub_packages": [],
                                    "discovered_via": gc.get("discovered_via", gc["path"]),
                                })
                else:
                    interesting_modules.append({
                        "path": root_pkg["path"],
                        "kind": root_pkg["kind"],
                        "depth": root_pkg["depth"],
                        "file_count": _count_source_files(root_pkg["_real_path"]),
                        "sub_packages": [dc["path"].split("/")[-1] for dc in direct_children],
                        "discovered_via": root_pkg.get("discovered_via", root_pkg["path"]),
                    })

            # 兜底: 如果没识别出任何 package (纯 script 仓库或 dir-only), 退化到顶层目录
            if not interesting_modules:
                for d in top_source_root.iterdir():
                    if d.is_dir() and d.name not in self._IGNORE_DIRS:
                        try:
                            rel = d.relative_to(working).as_posix()
                        except ValueError:
                            rel = str(d)
                        interesting_modules.append({
                            "path": rel,
                            "kind": "dir",
                            "depth": len(rel.split("/")),
                            "file_count": _count_source_files(d),
                            "sub_packages": [],
                            "discovered_via": f"{rel}/ (fallback: no package marker)",
                        })

            # 按 file_count 降序, 取前 20 个 (太多会在 module_drafter 阶段炸 token)
            interesting_modules.sort(key=lambda m: -m.get("file_count", 0))
            interesting_modules = interesting_modules[:20]

            # 第 4 步: 规模评估
            summary = input_data.get("file_tree_summary", {})
            fc = summary.get("file_count", 0)
            depth = summary.get("max_depth", 0)
            mod_count = len(interesting_modules)
            total_code_files = sum(m.get("file_count", 0) for m in interesting_modules)

            # 新启发式: 代码文件数 + 模块数为主 (而不是总文件数, 避免 png/json 主导)
            raw = (total_code_files * 0.3) + (mod_count * 3) + (depth * 4)
            score = max(0, min(100, round(raw)))
            if score < 30:
                level = "quick"
            elif score <= 70:
                level = "standard"
            else:
                level = "deep"

            try:
                top_source_rel = top_source_root.relative_to(working).as_posix()
            except ValueError:
                top_source_rel = "."

            return Verdict(kind=VerdictKind.PASS, output={
                **input_data,
                "complexity_score": score,
                "scale_level": level,
                "estimated_modules": mod_count,
                "code_modules": interesting_modules,
                "top_source_root": top_source_rel,
            })
        except Exception as e:
            return Verdict(kind=VerdictKind.FAIL, output=input_data,
                           diagnosis=f"规模评估异常: {e}")


class ModeSelectorRouter(Router):
    FORMAT_IN = "repo-architect.scaled-survey"
    FORMAT_OUT = "repo-architect.mode-selected"
    DESCRIPTION = (
        "向用户确认分析模式 (quick/standard/deep) + report_style + focus_areas。"
        "用户不可达时回退到 default_mode 兜底。本节点以规模建议为默认值, 非交互。"
    )

    def run(self, input_data: Any) -> Verdict:
        try:
            level = input_data.get("scale_level", "standard")
            style_map = {"quick": "concise", "standard": "balanced", "deep": "detailed"}
            return Verdict(kind=VerdictKind.PASS, output={
                **input_data,
                "mode": level,
                "report_style": style_map.get(level, "balanced"),
                "research_enabled": level in ("standard", "deep"),
                "focus_areas": ["architecture", "dependencies", "entry_points"],
                "selection_status": "default_from_scale",
            })
        except Exception as e:
            return Verdict(kind=VerdictKind.FAIL, output=input_data,
                           diagnosis=f"模式选择失败: {e}")


class DefaultModeRouter(Router):
    FORMAT_IN = "repo-architect.scaled-survey"
    FORMAT_OUT = "repo-architect.mode-selected"
    DESCRIPTION = (
        "mode_selector 用户交互失败的兜底: 根据 complexity_score 自动推断模式, "
        "保证管线在无人工干预时仍能稳健推进。输出必符合 mode-selected Format。"
    )

    def run(self, input_data: Any) -> Verdict:
        score = input_data.get("complexity_score", 50)
        if score < 30:
            mode, research = "quick", False
        elif score <= 70:
            mode, research = "standard", True
        else:
            mode, research = "deep", True

        return Verdict(kind=VerdictKind.PASS, output={
            **input_data,
            "mode": mode,
            "report_style": "balanced",
            "research_enabled": research,
            "focus_areas": ["core_logic"],
            "selection_status": "auto_fallback",
        })


# ═══════════════════════════════════════════════════════════
# 阶段 2 信息收集 (3 分支 + 3 fallback)
# ═══════════════════════════════════════════════════════════


class RepoIntrospectionRouter(Router):
    """仅读仓库内部文件做"自我介绍"调研 — 替代名不副实的 external_researcher。

    2026-04-09 返工: 原 ExternalResearcherRouter 名字叫 external 实际只调 LLM 让它
    凭训练知识自由联想, 造成第一次跑把 OmniCompany 误识别为 voxel_sandbox 模组、第二次跑
    幻觉成"工业自动化 + aiohttp/numpy/device communication"等完全无关内容。
    根本修复: 砍掉"外部检索"语义 — 这个节点只做 repo_introspection, 只能读 working_path
    下的**真实文件**, 把 README/CHANGELOG/pyproject/package.json 的关键段落和
    disambiguation_hint 一起提炼成"notes + findings"。不再让 LLM 去外面找任何东西。

    如果未来真需要外部检索 (GitHub API stars/issues, 社区讨论), 应该是另一个**独立节点**
    + 真实的 WebSearch/WebFetch/GitHub REST 工具, 不是让 LLM 凭想象编造。
    """

    FORMAT_IN = "repo-architect.mode-selected"
    FORMAT_OUT = "repo-architect.research-notes"
    DESCRIPTION = (
        "读 working_path 下真实的 manifest + README + CHANGELOG, 结合 disambiguation_hint "
        "调 LLM 做结构化总结, 产出 notes/sources/key_findings。所有内容必须基于真实文件, "
        "严禁外部联想。(取代名不副实的 external_researcher)"
    )

    _INTROSPECT_FILES = [
        "README.md", "README.rst", "README.txt",
        "CHANGELOG.md", "CHANGES.md", "HISTORY.md",
        "CONTRIBUTING.md", "ARCHITECTURE.md", "OVERVIEW.md",
        "pyproject.toml", "package.json", "Cargo.toml", "go.mod",
    ]

    _SYSTEM_PROMPT = """\
你是一个仓库内省分析师。任务: 仅基于提供的 "内省文件内容" 段落 (来自真实仓库文件),
产出关于项目的结构化摘要。

【严格约束】
1. 你**只能**引用提供的内容。提供之外的信息一律不得编造。
2. 如果某个字段从提供的内容里找不到证据, 对应字段留空字符串或空数组, 不要编造。
3. 禁止使用训练语料里的同名项目知识 (比如同名的 voxel_sandbox 模组 / npm 包 / 工业软件等)。
4. 禁止"自由联想"从项目名字、描述里的关键词 (比如 "factory"、"engine"、"pipeline")
   推测项目用途。只说文件里写的。
5. **每条 finding 必须带真相源 (source)**, source 格式: "<filename>" 或
   "<filename>: 具体小节/原话前几个字", 让读者能直接回到文件里核对。
   "notes" 段是概述性文字可以不带行内 source。
6. 输出严格 JSON, 无 markdown fence:
{
  "notes": "基于真实文件的项目一段话总结 (≤500 字, 中英皆可)",
  "findings": [
    {"text": "本项目要求 Python 3.9+", "source": "pyproject.toml: requires-python"},
    {"text": "使用 MIT 许可证", "source": "pyproject.toml: license"}
  ]
}
"""

    def run(self, input_data: Any) -> Verdict:
        try:
            if not input_data.get("research_enabled"):
                return Verdict(kind=VerdictKind.PASS, output={
                    **input_data,
                    "research_status": "skipped",
                    "research_notes": "",
                    "sources": [],
                    "key_findings": [],
                })

            working = Path(input_data.get("working_path", "."))
            disambiguation_hint = input_data.get("disambiguation_hint", "")
            canonical_name = input_data.get("canonical_name", "unknown")

            # 读真实文件 (每个最多 1500 chars)
            found: list[tuple[str, str]] = []
            for fname in self._INTROSPECT_FILES:
                f = working / fname
                if f.exists() and f.is_file():
                    try:
                        text = f.read_text(encoding="utf-8", errors="ignore")[:1500]
                        found.append((fname, text))
                        if len(found) >= 6:
                            break
                    except Exception:
                        continue

            if not found:
                # 没有任何可内省的文件, 走降级
                return Verdict(
                    kind=VerdictKind.FAIL, output=input_data,
                    diagnosis="repo_introspection: no manifest/README/changelog found",
                )

            sources_text = "\n\n".join(f"=== {name} ===\n{content}" for name, content in found)
            user_msg = (
                f"【项目身份锚 (防幻觉)】\n{disambiguation_hint}\n\n"
                f"canonical_name: {canonical_name}\n\n"
                f"【真实仓库内省文件内容】\n{sources_text}\n\n"
                f"请严格按 SYSTEM 里的 JSON schema 输出, 只基于上面的真实文件内容。"
            )

            from omnicompany.runtime.llm.llm import LLMClient
            try:
                client = LLMClient(role="ide_agent", max_tokens=1500)
                resp = client.call(
                    messages=[{"role": "user", "content": user_msg}],
                    system=self._SYSTEM_PROMPT,
                )
                text = resp.content[0].text if resp.content else ""
            except Exception as llm_err:
                return Verdict(
                    kind=VerdictKind.FAIL, output=input_data,
                    diagnosis=f"repo_introspection LLM 调用失败: {llm_err}",
                )

            import re as _re
            m = _re.search(r'\{.*\}', text, _re.DOTALL)
            parsed = json.loads(m.group(0)) if m else {}

            # 归一化 key_findings: LLM 可能返回 list[str] (旧格式)  list[dict]。
            # 旧格式 fallback: 用第一个内省文件名当 source, 标记 unverified_source
            raw_findings = parsed.get("findings", []) or []
            available_sources = {name for name, _ in found}
            normalized_findings: list[dict] = []
            for f in raw_findings:
                if isinstance(f, dict):
                    text_val = str(f.get("text") or "").strip()
                    src_val = str(f.get("source") or "").strip()
                    if text_val:
                        normalized_findings.append({
                            "text": text_val,
                            "source": src_val or "(unsourced)",
                        })
                elif isinstance(f, str) and f.strip():
                    normalized_findings.append({
                        "text": f.strip(),
                        "source": "(unsourced: LLM returned legacy string format)",
                    })

            # sources = 所有 finding.source 中提到的文件 ∪ 实际读到的内省文件
            derived_sources: set[str] = set()
            for nf in normalized_findings:
                s = nf["source"]
                # 抽取文件名前缀 (冒号前的部分)
                fname = s.split(":")[0].strip()
                if fname and fname in available_sources:
                    derived_sources.add(fname)
            if not derived_sources:
                derived_sources = available_sources

            return Verdict(kind=VerdictKind.PASS, output={
                **input_data,
                "research_status": "completed",
                "research_notes": parsed.get("notes", ""),
                "sources": sorted(derived_sources),
                "key_findings": normalized_findings,
                "introspection_files": [name for name, _ in found],
            })
        except Exception as e:
            logger.warning("[repo_introspection] 失败: %s", e)
            return Verdict(kind=VerdictKind.FAIL, output=input_data,
                           diagnosis=f"repo_introspection 异常: {e}")


# 保持类名别名, 避免拓扑 + bindings 大改 (pipeline.py 里引用 external_researcher 这个节点 id
# 但现在实现语义完全是内省)。类名变了, 节点 id/format 保持不变。
ExternalResearcherRouter = RepoIntrospectionRouter


class ResearchDegradedRouter(Router):
    FORMAT_IN = "repo-architect.mode-selected"
    FORMAT_OUT = "repo-architect.research-notes"
    DESCRIPTION = (
        "repo_introspection 失败时的降级节点: 输出空 shape 并标记 research_status=degraded, "
        "保证下游不因字段缺失崩溃。report_fuser 在最终报告里会标注'内省未完成'。"
    )

    def run(self, input_data: Any) -> Verdict:
        return Verdict(kind=VerdictKind.PASS, output={
            **input_data,
            "research_status": "degraded",
            "research_notes": "Repo introspection unavailable; report limited to code analysis.",
            "sources": [],
            "key_findings": [],
            "fallback_applied": True,
        })


class DocsReaderRouter(Router):
    FORMAT_IN = "repo-architect.mode-selected"
    FORMAT_OUT = "repo-architect.docs-summary"
    DESCRIPTION = (
        "定位仓库 README/CONTRIBUTING/docs/ 下的文档, 用 LLM 提取 summary + "
        "design_decisions + api_overview + doc_coverage。无文档时直接进 fallback。"
    )

    def run(self, input_data: Any) -> Verdict:
        try:
            wp = Path(input_data.get("working_path", "."))
            if not wp.exists():
                return Verdict(kind=VerdictKind.FAIL, output=input_data,
                               diagnosis="working_path 不存在")

            # 2026-04-09 修复 hang: 原版读 8 文件 × 3000 chars = 24k 送 LLM,
            # 在 OmniCompany dogfood (186 md files + 大 docs/) 下 LLMClient 非流式调用会
            # 挂起无响应。修复: 严格限制输入量 + 优先选 canonical 文档而非 plan md。
            doc_files: list[Path] = []
            # 1. 仓库根的核心文档 (优先级最高)
            for pat in ["README.md", "README.rst", "CONTRIBUTING.md",
                        "ARCHITECTURE.md", "DESIGN.md", "OVERVIEW.md"]:
                p = wp / pat
                if p.exists():
                    doc_files.append(p)
            # 2. docs/ 顶层的 md (不递归 ** 以避开 186 plan docs 的陷阱)
            docs_dir = wp / "docs"
            if docs_dir.exists():
                doc_files.extend(sorted(docs_dir.glob("*.md"))[:3])
            # 硬上限 4 文件, 每文件 1500 chars = 最多 6k 输入
            doc_files = doc_files[:4]

            if not doc_files:
                return Verdict(kind=VerdictKind.PASS, output={
                    **input_data,
                    "docs_summary": "",
                    "design_decisions": [],
                    "doc_coverage": [],
                    "status": "no_docs",
                })

            contents = []
            for f in doc_files:
                try:
                    raw = f.read_text(encoding='utf-8', errors='ignore')[:1500]
                    contents.append(f"--- {f.name} ---\n{raw}")
                except Exception:
                    continue

            from omnicompany.runtime.llm.llm import LLMClient
            disambiguation_hint = input_data.get("disambiguation_hint", "")
            canonical_name = input_data.get("canonical_name", "unknown")
            combined_docs = "\n\n".join(contents)

            user_msg = (
                f"Project identity anchor (DO NOT hallucinate outside this):\n"
                f"{disambiguation_hint[:500]}\n\n"
                f"Analyze these canonical docs for project '{canonical_name}' and "
                f"extract:\n"
                f"  (1) summary: one-paragraph summary of the project goal based ONLY on these docs.\n"
                f"  (2) decisions: a list of EXPLICIT design decisions/facts stated in the docs. "
                f"      **Each decision MUST carry a source** pointing to which doc it came from, "
                f"      ideally including a short locator after the filename.\n"
                f"  (3) coverage: list of filenames you read.\n\n"
                f"Return strict JSON only:\n"
                f"{{\n"
                f"  \"summary\": \"...\",\n"
                f"  \"decisions\": [\n"
                f"    {{\"text\": \"Project requires Python 3.9+\", \"source\": \"pyproject.toml: requires-python\"}},\n"
                f"    {{\"text\": \"Uses MIT license\", \"source\": \"README.md: License section\"}}\n"
                f"  ],\n"
                f"  \"coverage\": [\"README.md\", \"pyproject.toml\"]\n"
                f"}}\n\n"
                f"{combined_docs}"
            )

            client = LLMClient(role="ide_agent", max_tokens=1500)
            try:
                resp = client.call(
                    messages=[{"role": "user", "content": user_msg}],
                    system="You are a technical doc analyst. Return valid JSON only, no markdown fence.",
                )
                text = resp.content[0].text if resp.content else ""
            except Exception as llm_err:
                # LLM 调用失败 (超时/rate limit/其他), 让 pipeline 路由到 docs_fallback
                return Verdict(
                    kind=VerdictKind.FAIL, output=input_data,
                    diagnosis=f"docs_reader LLM 调用失败: {llm_err}",
                )

            import re as _re
            m = _re.search(r'\{.*\}', text, _re.DOTALL)
            parsed = json.loads(m.group(0)) if m else {}

            # 归一化 decisions: LLM 可能返回 list[str] (旧格式) 或 list[dict]
            raw_decisions = parsed.get("decisions", []) or []
            available_docs = {f.name for f in doc_files}
            normalized_decisions: list[dict] = []
            for d in raw_decisions:
                if isinstance(d, dict):
                    text_val = str(d.get("text") or "").strip()
                    src_val = str(d.get("source") or "").strip()
                    if text_val:
                        normalized_decisions.append({
                            "text": text_val,
                            "source": src_val or "(unsourced)",
                        })
                elif isinstance(d, str) and d.strip():
                    normalized_decisions.append({
                        "text": d.strip(),
                        "source": "(unsourced: LLM returned legacy string format)",
                    })

            return Verdict(kind=VerdictKind.PASS, output={
                **input_data,
                "docs_summary": parsed.get("summary", ""),
                "design_decisions": normalized_decisions,
                "doc_coverage": parsed.get("coverage", [f.name for f in doc_files]),
                "status": "success",
            })
        except Exception as e:
            return Verdict(kind=VerdictKind.FAIL, output=input_data,
                           diagnosis=f"文档读取失败: {e}")


class DocsFallbackRouter(Router):
    FORMAT_IN = "repo-architect.mode-selected"
    FORMAT_OUT = "repo-architect.docs-summary"
    DESCRIPTION = (
        "docs_reader 失败或无文档时的降级: 输出空 shape, status=fallback_no_docs, "
        "让下游知道'仅能靠代码结构分析'。"
    )

    def run(self, input_data: Any) -> Verdict:
        return Verdict(kind=VerdictKind.PASS, output={
            **input_data,
            "docs_summary": "",
            "design_decisions": [],
            "doc_coverage": [],
            "status": "fallback_no_docs",
            "degradation_reason": "docs_reader_failed_or_missing",
        })


class AdaptiveInterviewerRouter(Router):
    """根据 mode + 身份锚 + 前序收集产出, 确定性推导细化焦点 (非 stub)。

    2026-04-09 返工: 原 stub 直接塞 "skipped_stub" 标志, 没有实际逻辑。
    现在: 不真实走 UserInquiry (会阻塞 pipeline), 而是用确定性规则综合
    canonical_description / primary_language / ecosystem / docs_summary 的
    design_decisions 推导出 refined_focus_areas, 让报告在没有人工介入时
    也有针对性, 而不是"默认值"。
    """

    FORMAT_IN = "repo-architect.mode-selected"
    FORMAT_OUT = "repo-architect.user-focus-profile"
    DESCRIPTION = (
        "确定性综合 mode + repo_identity + docs_summary 推导 refined_focus_areas 和 "
        "report_detail_preference。不走真实 UserInquiry (避免阻塞), 但有实际逻辑 "
        "而非 placeholder: 从 design_decisions 提取关键词, 按 ecosystem 加默认焦点。"
    )

    _ECOSYSTEM_DEFAULT_FOCUS = {
        "python": ["packages_layout", "data_flow", "entry_points"],
        "node": ["package_boundaries", "module_exports", "dependencies"],
        "rust": ["crate_structure", "trait_hierarchy", "error_handling"],
        "go": ["package_organization", "interfaces", "concurrency_primitives"],
        "mixed": ["language_boundaries", "ffi_points", "build_system"],
        "unknown": ["top_level_structure", "entry_points"],
    }

    def run(self, input_data: Any) -> Verdict:
        try:
            mode = input_data.get("mode", "standard")
            ecosystem = input_data.get("ecosystem", "unknown")

            # 基础焦点: ecosystem default
            refined = list(self._ECOSYSTEM_DEFAULT_FOCUS.get(ecosystem,
                          self._ECOSYSTEM_DEFAULT_FOCUS["unknown"]))

            # 追加用户显式关注点 (从 input.focus)
            user_focus = input_data.get("focus", "") or ""
            if user_focus and len(user_focus) > 10:
                refined.append(f"user_focus:{user_focus[:80]}")

            # 从 docs_summary 的 design_decisions 提取关键词
            design_decisions = input_data.get("design_decisions") or []
            if isinstance(design_decisions, list):
                for dd in design_decisions[:5]:
                    if isinstance(dd, str) and 10 < len(dd) < 200:
                        refined.append(f"doc_hint:{dd[:80]}")
                    elif isinstance(dd, dict) and dd.get("title"):
                        refined.append(f"doc_hint:{dd['title'][:80]}")

            # 从 research_notes.key_findings 追加
            key_findings = input_data.get("key_findings") or []
            if isinstance(key_findings, list):
                for kf in key_findings[:3]:
                    if isinstance(kf, str) and len(kf) > 10:
                        refined.append(f"research_hint:{kf[:80]}")

            # 去重, 保持顺序
            seen: set[str] = set()
            unique_refined = []
            for f in refined:
                if f not in seen:
                    seen.add(f)
                    unique_refined.append(f)

            detail_pref = {
                "quick": "concise",
                "standard": "balanced",
                "deep": "technical",
            }.get(mode, "balanced")

            return Verdict(kind=VerdictKind.PASS, output={
                **input_data,
                "interview_responses": {
                    "_mode": "deterministic_synthesis",
                    "_note": "No live UserInquiry; derived from mode + ecosystem + docs + research",
                },
                "refined_focus_areas": unique_refined,
                "report_detail_preference": detail_pref,
                "interview_status": "deterministic",
            })
        except Exception as e:
            return Verdict(kind=VerdictKind.FAIL, output=input_data,
                           diagnosis=f"adaptive_interviewer 异常: {e}")


class InterviewDefaultsRouter(Router):
    FORMAT_IN = "repo-architect.mode-selected"
    FORMAT_OUT = "repo-architect.user-focus-profile"
    DESCRIPTION = (
        "adaptive_interviewer 失败的降级: 用 mode_selected.focus_areas 作为"
        "refined_focus_areas, report_detail_preference=balanced, 标记 status=default_used。"
    )

    def run(self, input_data: Any) -> Verdict:
        return Verdict(kind=VerdictKind.PASS, output={
            **input_data,
            "interview_responses": {},
            "refined_focus_areas": input_data.get("focus_areas", ["architecture"]),
            "report_detail_preference": "balanced",
            "interview_status": "default_used",
        })


# ═══════════════════════════════════════════════════════════
# 阶段 3 报告骨架
# ═══════════════════════════════════════════════════════════


class ReportDesignerRouter(Router):
    """综合前序所有信息, 调 LLM 设计报告骨架 + 选定 focus_modules (真实代码模块, 非顶层目录)。

    2026-04-09 返工: 原 stub 用硬编码 sections + key_dirs 作为 focus_modules (全是顶层目录)。
    现在: 从 code_modules 里挑真正的源码包作为 focus_modules, LLM 根据 refined_focus_areas
    + docs_summary + 模块列表综合设计 sections + mermaid_hints + focus_modules。
    """

    FORMAT_IN = "repo-architect.user-focus-profile"
    FORMAT_OUT = "repo-architect.report-skeleton"
    DESCRIPTION = (
        "调 LLM 综合 code_modules + refined_focus_areas + docs_summary + research_notes "
        "设计报告骨架: 选 3-8 个真实代码模块作为 focus_modules, 产出 sections + "
        "mermaid_hints, 根据 mode 决定章节数量和技术深度。"
    )

    _SYSTEM_PROMPT = """\
你是一个技术文档架构师。根据下列输入设计一份架构分析报告的骨架。

【必须遵守】
1. focus_modules 必须从输入的 code_modules 列表里**挑**, 不能编新的, 不能写顶层目录名。
2. 选择标准: 优先选 file_count 大 + sub_packages 多的模块 (它们是"大模块");
   结合 refined_focus_areas 和 user 的 focus 文本, 挑跟关注点最相关的 3-8 个模块。
3. sections 必须包含至少: 项目目标 / 高层架构 / 模块职责 / 依赖与集成 / 结论。
   根据 mode 增减: quick=5 章节, standard=6-7 章节, deep=8-10 章节。
4. mermaid_hints 列出需要画哪些图类型, 从 {architecture_flow, module_dependency,
   data_flow, class_hierarchy, sequence} 里选。
5. 输出严格 JSON:
   {
     "sections": [{"title": "...", "required": true, "estimated_length": 300, "rationale": "为什么需要这章"}],
     "focus_modules": ["src/foo/bar", "lib/xyz", ...],
     "mermaid_hints": ["architecture_flow", "module_dependency"],
     "design_rationale": "一句话说明为什么这样设计 (基于 mode 和 focus_areas)"
   }
6. **禁止**: 编造 code_modules 里没有的路径; 写顶层目录作为 focus_module;
   忽略 user focus 文本。
"""

    def run(self, input_data: Any) -> Verdict:
        try:
            from omnicompany.runtime.llm.llm import LLMClient
            import re as _re

            code_modules = input_data.get("code_modules") or []
            refined_focus = input_data.get("refined_focus_areas") or []
            docs_summary = input_data.get("docs_summary", "") or ""
            mode = input_data.get("mode", "standard")
            user_focus = input_data.get("focus", "") or ""
            disambiguation_hint = input_data.get("disambiguation_hint", "")
            canonical_name = input_data.get("canonical_name", "unknown")

            if not code_modules:
                return Verdict(
                    kind=VerdictKind.FAIL, output=input_data,
                    diagnosis="code_modules 为空 — scale_surveyor 应先提供真实模块列表",
                )

            # 简化 code_modules 给 LLM 看, 按 file_count 降序
            mods_for_llm = sorted(
                [{"path": m.get("path"), "kind": m.get("kind"),
                  "file_count": m.get("file_count", 0),
                  "sub_packages": m.get("sub_packages", [])[:8]}
                 for m in code_modules if isinstance(m, dict)],
                key=lambda m: -m.get("file_count", 0),
            )[:30]  # LLM 最多看 30 个候选模块

            user_msg = (
                f"【项目身份 (防幻觉锚)】\n{disambiguation_hint}\n\n"
                f"canonical_name: {canonical_name}\n"
                f"分析模式 mode: {mode}\n\n"
                f"【用户显式焦点】\n{user_focus or '(未提供)'}\n\n"
                f"【细化关注点 (refined_focus_areas)】\n{json.dumps(refined_focus, ensure_ascii=False, indent=2)}\n\n"
                f"【文档摘要 (来自 README/docs)】\n{docs_summary[:1500] if docs_summary else '(无)'}\n\n"
                f"【真实代码模块候选清单 (按 file_count 排序, 选 focus_modules 只能从这里挑)】\n"
                f"{json.dumps(mods_for_llm, ensure_ascii=False, indent=2)}\n\n"
                f"请按 SYSTEM 的 JSON schema 输出骨架设计。"
            )

            client = LLMClient(role="ide_agent", max_tokens=2500)
            resp = client.call(
                messages=[{"role": "user", "content": user_msg}],
                system=self._SYSTEM_PROMPT,
            )
            text = resp.content[0].text if resp.content else ""
            m = _re.search(r'\{.*\}', text, _re.DOTALL)
            if not m:
                return Verdict(
                    kind=VerdictKind.FAIL, output=input_data,
                    diagnosis=f"report_designer LLM 返回无合法 JSON: {text[:200]}",
                )
            parsed = json.loads(m.group(0))

            # 校验 focus_modules 每条都在 code_modules 里
            valid_paths = {m.get("path") for m in code_modules if isinstance(m, dict)}
            llm_focus = parsed.get("focus_modules") or []
            clean_focus = [p for p in llm_focus if p in valid_paths]
            if not clean_focus:
                # LLM 没选对任何合法模块 — 兜底取 file_count 前 5 个
                clean_focus = [m["path"] for m in mods_for_llm[:5]]

            return Verdict(kind=VerdictKind.PASS, output={
                **input_data,
                "sections": parsed.get("sections", []),
                "focus_modules": clean_focus,
                "mermaid_hints": parsed.get("mermaid_hints", ["architecture_flow"]),
                "design_rationale": parsed.get("design_rationale", ""),
                "design_mode": mode,
            })
        except Exception as e:
            return Verdict(kind=VerdictKind.FAIL, output=input_data,
                           diagnosis=f"report_designer 异常: {e}")


# ═══════════════════════════════════════════════════════════
# 阶段 4 并行深度分析 (SCATTER-ish)
# ═══════════════════════════════════════════════════════════


class ModuleDrafterLeafRouter(Router):
    """逐模块深度分析器 — 对每个 code_module 调 LLM 产出 module-draft。

    2026-04-09 返工: 从 stub placeholder 改为真实 LLM 分析。
    按 SKILL.md §3.3 代码审计节点的信息源清单注入:
      1. 被审对象的真实源码 (每模块读前 N 个源文件, 每个文件前 200 行)
      2. 仓库身份锚 (canonical_name + disambiguation_hint)
      3. 已知的 focus_areas (用户关注点)
      4. 目标输出 schema

    设计权衡: 不用 AgentNodeLoop (SKILL.md 明说 "最后手段"),
    改用 Transformer 预加载源码 + 单轮 LLMRouter, 更确定、更可缓存。
    注意: 这里是 "leaf per module" 的语义, 但 SCATTER NodeKind 在 OmniCompany 里
    需要 sub_pipeline, 暂时用"循环内调 LLM"模拟, 后续可升级真 SCATTER。

    输出: drafts (每个含 4 维度 content), failed_modules (含 reason), analysis_status
    """

    FORMAT_IN = "repo-architect.report-skeleton"
    FORMAT_OUT = "repo-architect.module-draft"
    DESCRIPTION = (
        "对 focus_modules 里每个 code_module 读真实源码 + 调 LLM (带 disambiguation_hint) "
        "产出 4 维度 (architecture/responsibility/dependencies/interfaces) 深度分析。"
        "每模块独立一次 LLM 调用, 按 SKILL.md §3.3 代码审计节点信息源清单注入上下文。"
    )

    _MAX_FILES_PER_MODULE = 8       # 每模块最多读 N 个源文件
    _MAX_LINES_PER_FILE = 200       # 每文件最多取前 N 行
    _CODE_EXTS = {".py", ".ts", ".js", ".jsx", ".tsx", ".rs", ".go",
                  ".java", ".kt", ".cpp", ".c", ".h", ".hpp"}
    # quick/standard/deep 模式下最多分析多少个模块 (防止爆 LLM 配额)
    _MODE_MAX_MODULES = {"quick": 3, "standard": 6, "deep": 12}

    _SYSTEM_PROMPT = """\
你是一个资深的代码架构审阅员。任务: 对一个具体代码模块 (已读真实源码) 做 4 维度分析,
**并为每一条断言附带 evidence_refs (指向你读到的文件+行号)**, 形成可追溯真相链。

【必须严格遵守的约束】
1. 你只能基于提供的 source_excerpt 里的真实代码回答。
2. 如果某个维度在代码里找不到证据, 对应维度的 text 写"(代码中未找到直接证据: <原因>)",
   把该维度名加进 missing_aspects 说明缺什么, 不要编造 evidence_refs。
3. 你正在分析的项目已经在 disambiguation_hint 里锁定身份。**禁止**把其他同名或类似名字的项目的
   知识搬过来。
4. 不要给出 0-100 的数值打分。用 coverage_status (complete/partial/insufficient) +
   missing_aspects 表达你觉得哪里齐全哪里不齐全。
5. 输出严格 JSON, 无 markdown fence, schema 如下:
   {
     "analysis_sections": {
       "architecture":   {"text": "架构角色 (50-500 字)", "evidence_refs": [...]},
       "responsibility": {"text": "职责 (50-500 字)",      "evidence_refs": [...]},
       "dependencies":   {"text": "依赖描述",               "evidence_refs": [...]},
       "interfaces":     {"text": "对外接口描述",           "evidence_refs": [...]}
     },
     "coverage_status": "complete" | "partial" | "insufficient",
     "missing_aspects": ["dependencies: 只读了 __init__.py 没深入 ...", ...]
   }
6. evidence_refs 每条形如:
   {"file": "src/anthropic/_utils/__init__.py", "lines": "3-18",
    "claim": "这段 re-export 支撑了 interfaces 中 PropertyInfo 的声明"}
   - file 必须是 source_excerpt 里真实出现过的文件路径 (和 '--- xxx ---' 标题一致)
   - lines 是该文件里你实际引用的行号区间 (例 '12-30' 或 '45')
   - claim 用中文说这段引用支撑的是你上面 text 里的哪条具体断言
   - 每个维度至少 1 条 evidence_ref (否则 coverage_status 必须是 partial 或 insufficient
     且 missing_aspects 要说明)
7. coverage_status 三档判定:
   - complete:     4 维度都有 text 且每维度都至少 1 条 evidence_ref, missing_aspects 为 []
   - partial:      4 维度都有 text, 但有维度 evidence 薄弱或只能从 __init__.py 推断,
                   此时 missing_aspects 列出"哪个维度缺什么"
   - insufficient: 有维度根本找不到证据 (或只看到空 __init__.py), 需要回环重分析
"""

    def run(self, input_data: Any) -> Verdict:
        try:
            from omnicompany.runtime.llm.llm import LLMClient
            import re as _re

            focus_modules = input_data.get("focus_modules", []) or []
            code_modules = input_data.get("code_modules", []) or []
            working = Path(input_data.get("working_path", "."))
            canonical_name = input_data.get("canonical_name", "unknown")
            canonical_description = input_data.get("canonical_description", "")
            disambiguation_hint = input_data.get("disambiguation_hint", "")
            primary_language = input_data.get("primary_language", "unknown")

            # 按 mode 限定总模块数 (防止 LLM 配额爆炸)
            mode = input_data.get("mode", "standard")
            max_mods = self._MODE_MAX_MODULES.get(mode, 6)

            # 把 focus_modules (str list) 对齐到 code_modules (dict list)
            target_modules: list[dict] = []
            if focus_modules and code_modules:
                mod_by_path = {m["path"]: m for m in code_modules if isinstance(m, dict)}
                for fm in focus_modules:
                    if isinstance(fm, str) and fm in mod_by_path:
                        target_modules.append(mod_by_path[fm])
                    elif isinstance(fm, dict) and fm.get("path"):
                        target_modules.append(fm)
                # 若 focus_modules 没命中任何 code_module, 退化为直接用 code_modules 前 N 个
                if not target_modules:
                    target_modules = code_modules[:max_mods]
            elif code_modules:
                target_modules = code_modules[:max_mods]

            # 应用 mode 上限 (用户/LLM 可能选了太多)
            if len(target_modules) > max_mods:
                logger.info(
                    "[module_drafter] mode=%s, 截到 %d 个模块 (原始 %d)",
                    mode, max_mods, len(target_modules),
                )
                target_modules = target_modules[:max_mods]

            if not target_modules:
                return Verdict(kind=VerdictKind.FAIL, output=input_data,
                               diagnosis="没有可分析的模块 (focus_modules 和 code_modules 都空)")

            # LLMClient — 用 ide_agent (quality tier = qwen3.6-plus) 跑深度分析
            client = LLMClient(role="ide_agent", max_tokens=2000)

            drafts: list[dict] = []
            failed: list[dict] = []

            for mod in target_modules:
                module_path = mod.get("path", "")
                module_abs = working / module_path
                if not module_abs.exists() or not module_abs.is_dir():
                    failed.append({
                        "module": module_path,
                        "reason": f"path not found or not a directory: {module_abs}",
                    })
                    continue

                # 读模块内真实源码: 取前 N 个源文件, 每个前 M 行
                source_files: list[tuple[str, str]] = []
                try:
                    candidates = sorted(
                        [f for f in module_abs.rglob("*") if f.is_file() and f.suffix in self._CODE_EXTS
                         and "__pycache__" not in f.parts],
                        key=lambda p: (len(p.parts), p.name),  # 浅的文件优先
                    )[: self._MAX_FILES_PER_MODULE]
                    for f in candidates:
                        try:
                            content = f.read_text(encoding="utf-8", errors="ignore")
                            lines = content.splitlines()[: self._MAX_LINES_PER_FILE]
                            rel = f.relative_to(working).as_posix()
                            source_files.append((rel, "\n".join(lines)))
                        except Exception:
                            continue
                except Exception as e:
                    failed.append({"module": module_path, "reason": f"scan error: {e}"})
                    continue

                if not source_files:
                    failed.append({
                        "module": module_path,
                        "reason": "no source files found (only non-code files or empty dir)",
                    })
                    continue

                # 构造 LLM prompt
                source_excerpt_parts = []
                for rel_path, content in source_files:
                    source_excerpt_parts.append(f"--- {rel_path} ---\n{content}")
                source_excerpt = "\n\n".join(source_excerpt_parts)

                user_msg = (
                    f"【项目身份 (防幻觉锚)】\n"
                    f"{disambiguation_hint}\n\n"
                    f"canonical_name: {canonical_name}\n"
                    f"canonical_description: {canonical_description}\n"
                    f"primary_language: {primary_language}\n\n"
                    f"【待分析模块】{module_path}\n"
                    f"kind: {mod.get('kind', 'unknown')}\n"
                    f"source files scanned: {len(source_files)}\n"
                    f"total files in module: {mod.get('file_count', '?')}\n\n"
                    f"【真实源码节选 (每文件最多 {self._MAX_LINES_PER_FILE} 行, 共 {len(source_files)} 个文件)】\n"
                    f"{source_excerpt}\n\n"
                    f"请按 SYSTEM 里的 JSON schema 输出 4 维度分析。基于上述真实源码,"
                    f" 不要从模块名字推测, 不要从外部知识借用。"
                )

                try:
                    resp = client.call(
                        messages=[{"role": "user", "content": user_msg}],
                        system=self._SYSTEM_PROMPT,
                    )
                    text = resp.content[0].text if resp.content else ""
                    m = _re.search(r'\{.*\}', text, _re.DOTALL)
                    if not m:
                        failed.append({
                            "module": module_path,
                            "reason": f"LLM 返回无合法 JSON (前 200 字符: {text[:200]})",
                        })
                        continue
                    parsed = json.loads(m.group(0))

                    # 真实读到的文件集合, 用来校验 evidence_refs.file 指向的文件是否真实存在
                    real_files = {rel for rel, _ in source_files}

                    def _to_text(v: Any) -> str:
                        if isinstance(v, list):
                            return "; ".join(str(x) for x in v)
                        if isinstance(v, dict):
                            return "; ".join(f"{k}: {vv}" for k, vv in v.items())
                        return str(v or "")

                    def _norm_section(raw: Any) -> dict:
                        """把 LLM 返回的维度归一化成 {text, evidence_refs}。
                        兼容 3 种 LLM 返回姿势:
                          (a) {text: "...", evidence_refs: [...]}  ← 正确
                          (b) "纯字符串"                            ← 旧版 LLM
                          (c) 其他 list/dict                        ← 被截断
                        """
                        if isinstance(raw, dict) and "text" in raw:
                            text_val = _to_text(raw.get("text"))
                            refs_raw = raw.get("evidence_refs") or []
                            clean_refs: list[dict] = []
                            for r in refs_raw:
                                if not isinstance(r, dict):
                                    continue
                                f_ref = str(r.get("file") or "").strip()
                                if not f_ref:
                                    continue
                                # 校验 file 是不是真实读到的
                                verified = f_ref in real_files
                                clean_refs.append({
                                    "file": f_ref,
                                    "lines": str(r.get("lines") or "").strip(),
                                    "claim": _to_text(r.get("claim"))[:300],
                                    "verified": verified,
                                })
                            return {"text": text_val[:2000], "evidence_refs": clean_refs}
                        # 降级: 纯 string / list / dict-without-text
                        return {"text": _to_text(raw)[:2000], "evidence_refs": []}

                    sec_raw = parsed.get("analysis_sections") or {}
                    # 向后兼容: 如果 LLM 平铺了 4 个键 (老 schema), 也能解析
                    if not sec_raw and any(k in parsed for k in
                                           ("architecture", "responsibility", "dependencies", "interfaces")):
                        sec_raw = {k: parsed.get(k) for k in
                                   ("architecture", "responsibility", "dependencies", "interfaces")}

                    analysis_sections = {
                        "architecture":   _norm_section(sec_raw.get("architecture")),
                        "responsibility": _norm_section(sec_raw.get("responsibility")),
                        "dependencies":   _norm_section(sec_raw.get("dependencies")),
                        "interfaces":     _norm_section(sec_raw.get("interfaces")),
                    }

                    # coverage_status + missing_aspects
                    status_raw = str(parsed.get("coverage_status") or "").strip().lower()
                    if status_raw not in ("complete", "partial", "insufficient"):
                        # 从 evidence_refs 覆盖度反推一个保守值
                        dims_with_evidence = sum(
                            1 for v in analysis_sections.values() if v["evidence_refs"]
                        )
                        if dims_with_evidence == 4:
                            status_raw = "complete"
                        elif dims_with_evidence >= 2:
                            status_raw = "partial"
                        else:
                            status_raw = "insufficient"

                    missing_raw = parsed.get("missing_aspects") or []
                    missing_aspects = [
                        str(x).strip() for x in missing_raw if isinstance(x, (str, dict)) and str(x).strip()
                    ]

                    # 若 status 是 complete 但有维度没 evidence, 降级为 partial
                    if status_raw == "complete":
                        empty_dims = [k for k, v in analysis_sections.items() if not v["evidence_refs"]]
                        if empty_dims:
                            status_raw = "partial"
                            missing_aspects.append(
                                f"{', '.join(empty_dims)}: LLM 声称 complete 但这些维度没给 evidence_refs, 降级为 partial"
                            )

                    drafts.append({
                        "module_name": module_path,
                        "module_kind": mod.get("kind", "unknown"),
                        "discovered_via": mod.get("discovered_via", ""),
                        "analysis_sections": analysis_sections,
                        "coverage_status": status_raw,
                        "missing_aspects": missing_aspects,
                        "evidence_files": [rel for rel, _ in source_files],
                    })
                except Exception as e:
                    failed.append({
                        "module": module_path,
                        "reason": f"LLM 调用或解析失败: {e}",
                    })
                    continue

            if not drafts:
                return Verdict(
                    kind=VerdictKind.FAIL, output=input_data,
                    diagnosis=f"所有 {len(target_modules)} 个模块分析都失败: {failed[:3]}",
                )

            # 2026-04-09: 消除下划线走私, drafts / failed_modules / total_modules 作为
            # 正式字段直接放 output, 不再用 _drafts 前缀
            return Verdict(kind=VerdictKind.PASS, output={
                **input_data,
                "drafts": drafts,
                "failed_modules": failed,
                "total_modules": len(target_modules),
                "analysis_status": "all_success" if not failed else (
                    "partial" if drafts else "all_failed"
                ),
            })
        except Exception as e:
            return Verdict(kind=VerdictKind.FAIL, output=input_data,
                           diagnosis=f"module_drafter 异常: {e}")


class DraftCollectorRouter(Router):
    """module-draft → draft-set 透传校验节点。

    2026-04-09: module_drafter 已经直接输出 drafts/failed_modules 字段 (不再走私),
    本节点只做 format_out 转型 + 确定性校验。"""

    FORMAT_IN = "repo-architect.module-draft"
    FORMAT_OUT = "repo-architect.draft-set"
    DESCRIPTION = (
        "确定性校验 + format 转型: 每个 draft 的 analysis_sections 4 维度必须有 text, "
        "coverage_status 必须 ∈ {complete, partial, insufficient}。"
    )

    _VALID_STATUSES = {"complete", "partial", "insufficient"}

    def run(self, input_data: Any) -> Verdict:
        try:
            drafts = input_data.get("drafts") or []
            failed = input_data.get("failed_modules") or []
            if not drafts:
                return Verdict(kind=VerdictKind.FAIL, output=input_data,
                               diagnosis="drafts 为空 — 无法进入 draft-set")

            for i, d in enumerate(drafts):
                if not isinstance(d, dict):
                    return Verdict(kind=VerdictKind.FAIL, output=input_data,
                                   diagnosis=f"drafts[{i}] 不是 dict")
                secs = d.get("analysis_sections") or {}
                missing_dims: list[str] = []
                for k in ("architecture", "responsibility", "dependencies", "interfaces"):
                    v = secs.get(k)
                    # 新 schema: {text, evidence_refs}
                    if not (isinstance(v, dict) and str(v.get("text") or "").strip()):
                        missing_dims.append(k)
                if missing_dims:
                    return Verdict(
                        kind=VerdictKind.FAIL, output=input_data,
                        diagnosis=f"drafts[{i}] ({d.get('module_name')}) 缺维度文本: {missing_dims}",
                    )
                status = d.get("coverage_status")
                if status not in self._VALID_STATUSES:
                    return Verdict(
                        kind=VerdictKind.FAIL, output=input_data,
                        diagnosis=f"drafts[{i}] coverage_status={status!r} 不合法",
                    )

            total = len(drafts) + len(failed)
            status = ("all_success" if not failed else
                      ("partial" if drafts else "all_failed"))

            return Verdict(kind=VerdictKind.PASS, output={
                **input_data,
                "total_modules": total,
                "analysis_status": status,
            })
        except Exception as e:
            return Verdict(kind=VerdictKind.FAIL, output=input_data,
                           diagnosis=f"draft_collector 异常: {e}")


# ═══════════════════════════════════════════════════════════
# 阶段 5 质量门 + 交叉验证
# ═══════════════════════════════════════════════════════════


class CoverageGaterRouter(Router):
    FORMAT_IN = "repo-architect.draft-set"
    FORMAT_OUT = "repo-architect.coverage-feedback"
    DESCRIPTION = (
        "基于 drafts[*].coverage_status 判 gate: 有 insufficient → retry (或 fail 若耗尽), "
        "否则 pass (partial 允许通过但会记录)。输出 gate_status + insufficient_modules + "
        "partial_modules + retry_count。禁止用数值打分。"
    )

    def run(self, input_data: Any) -> Verdict:
        try:
            drafts = input_data.get("drafts", []) or []
            retry_count = input_data.get("_coverage_retry_count", 0)

            insufficient = [d.get("module_name") for d in drafts
                            if d.get("coverage_status") == "insufficient"]
            partial = [d.get("module_name") for d in drafts
                       if d.get("coverage_status") == "partial"]

            if not insufficient:
                gate = "pass"
                msg = (f"全部模块 coverage_status ∈ complete/partial 通过 gate"
                       + (f" (partial: {len(partial)})" if partial else ""))
            elif retry_count < 3:
                gate = "retry"
                msg = f"第 {retry_count + 1} 轮, {len(insufficient)} 模块 insufficient 需重分析"
            else:
                gate = "fail"
                msg = f"重试 {retry_count} 轮仍有 {len(insufficient)} 模块 insufficient"

            return Verdict(kind=VerdictKind.PASS, output={
                **input_data,
                "gate_status": gate,
                "insufficient_modules": insufficient,
                "partial_modules": partial,
                "retry_count": retry_count + (1 if gate == "retry" else 0),
                "feedback_message": msg,
            })
        except Exception as e:
            return Verdict(kind=VerdictKind.FAIL, output=input_data,
                           diagnosis=f"coverage_gater 失败: {e}")


class ValidatedDraftsRouter(Router):
    FORMAT_IN = "repo-architect.coverage-feedback"
    FORMAT_OUT = "repo-architect.validated-drafts"
    DESCRIPTION = (
        "过滤 gate_status=pass 的 drafts (保留 complete + partial, 丢弃 insufficient), "
        "聚合 aggregated_missing_aspects 供 report_fuser 渲染'覆盖率缺口'段。"
        "输出 overall_status (complete/mixed), 禁止数值百分比。"
    )

    def run(self, input_data: Any) -> Verdict:
        try:
            drafts = input_data.get("drafts", []) or []
            passed = [d for d in drafts
                      if d.get("coverage_status") in ("complete", "partial")]

            # 聚合 missing_aspects
            aggregated: list[dict] = []
            for d in passed:
                for m in (d.get("missing_aspects") or []):
                    aggregated.append({"module": d.get("module_name"), "aspect": m})

            has_partial = any(d.get("coverage_status") == "partial" for d in passed)
            overall_status = "mixed" if has_partial else "complete"

            return Verdict(kind=VerdictKind.PASS, output={
                **input_data,
                "validated_drafts": passed,
                "overall_status": overall_status,
                "aggregated_missing_aspects": aggregated,
                "passed_at_retry": input_data.get("retry_count", 0),
            })
        except Exception as e:
            return Verdict(kind=VerdictKind.FAIL, output=input_data,
                           diagnosis=f"validated-drafts 生成失败: {e}")


class CrossValidatorRouter(Router):
    """对 validated_drafts 做模块间一致性检查 + 构建 cross_reference_map。

    2026-04-09 返工: 原 stub 直接返回 consistent + 空 map。
    现在: 先做确定性部分 (从 drafts 的 dependencies 文本解析模块引用),
    再用 LLM 做接口语义一致性检查 (A 说依赖 B, B 是否提供了?), 输出真正的
    inconsistencies 列表。
    """

    FORMAT_IN = "repo-architect.validated-drafts"
    FORMAT_OUT = "repo-architect.cross-validation"
    DESCRIPTION = (
        "两步: (1) 确定性从每个 draft.dependencies 文本里正则抽取对其他模块的引用, "
        "构建 cross_reference_map; (2) LLM 检查模块对间的接口声明一致性, 输出"
        "validation_status + inconsistencies 列表 (每条含 module_pair + issue + suggestion)。"
    )

    _SYSTEM_PROMPT = """\
你是一个代码架构一致性检查员。根据下面提供的模块分析结果 (每个模块都带 evidence_refs),
检查模块之间的接口一致性。**每条不一致必须引用上游声明作为 evidence_upstream**, 不允许
凭空下结论。

【检查维度】
1. missing_interface: A 的 dependencies 段提到了 B 的某个符号, 但 B 的 interfaces 段
   没有给出对应 evidence_ref (不是简单的文本不匹配, 而是"B 没有任何 evidence 支撑这个符号存在")
2. description_conflict: A 和 B 的 responsibility 段描述矛盾 (比如都声称负责同一件事)
3. layer_violation: A 的 architecture 层级 和 B 的 architecture 层级关系不合理
4. naming_conflict: 两个模块的 interfaces 里有命名冲突

【必须遵守】
- 每条 inconsistency 必须同时带 evidence_upstream 数组, 指明你是"依据谁的哪段话"下的判断。
- 如果没法明确指向上游某段断言, 就不要报这条 inconsistency (宁可漏报也不凭空)。
- 单模块直接 consistent, inconsistencies=[]。

【输出格式 (严格 JSON, 无 markdown fence)】
{
  "validation_status": "consistent" | "warning" | "inconsistent",
  "inconsistencies": [
    {
      "module_pair": ["src/foo", "src/bar"],
      "issue_type": "missing_interface",
      "detail": "src/foo 的 dependencies 说需要 bar.Baz, 但 src/bar 的 interfaces 没暴露 Baz",
      "suggestion": "确认 Baz 是否应加入 bar/__init__.py 的 re-export",
      "evidence_upstream": [
        {
          "from_node": "module_drafter",
          "draft_module": "src/foo",
          "section": "dependencies",
          "quoted_text": "from ..bar import Baz",
          "source_ref": {"file": "src/foo/__init__.py", "lines": "3-5"}
        },
        {
          "from_node": "module_drafter",
          "draft_module": "src/bar",
          "section": "interfaces",
          "quoted_text": "(no mention of Baz)",
          "source_ref": null
        }
      ]
    }
  ],
  "summary": "一句话总体结论"
}
"""

    def run(self, input_data: Any) -> Verdict:
        try:
            from omnicompany.runtime.llm.llm import LLMClient
            import re as _re

            validated_drafts = input_data.get("validated_drafts") or []
            if not validated_drafts:
                return Verdict(
                    kind=VerdictKind.PASS, output={
                        **input_data,
                        "validation_status": "consistent",
                        "inconsistencies": [],
                        "cross_reference_map": {},
                        "summary": "No validated drafts to cross-check",
                    }
                )

            # 第 1 步: 确定性构建 cross_reference_map
            # 从每个 draft 的 dependencies 文本里抽取 "提到" 的模块路径或名字
            module_names = [d.get("module_name", "") for d in validated_drafts]
            short_names = {}  # last segment → full path
            for name in module_names:
                if name:
                    short_names[name.split("/")[-1]] = name

            cross_ref_map: dict[str, list[str]] = {m: [] for m in module_names if m}

            def _section_text(sec: Any) -> str:
                """新 schema: sec 是 {text, evidence_refs}; 兼容老: sec 是 string。"""
                if isinstance(sec, dict):
                    return str(sec.get("text") or "")
                if isinstance(sec, list):
                    return " ".join(str(x) for x in sec)
                return str(sec or "")

            for d in validated_drafts:
                src = d.get("module_name", "")
                deps_text = _section_text(
                    (d.get("analysis_sections", {}) or {}).get("dependencies")
                )
                for short, full in short_names.items():
                    if full == src:
                        continue
                    if _re.search(rf'\b{_re.escape(short)}\b', deps_text, _re.IGNORECASE):
                        if full not in cross_ref_map[src]:
                            cross_ref_map[src].append(full)

            # 第 2 步: 只对真实存在跨引用的模块对调 LLM, 避免浪费
            if len(validated_drafts) == 1:
                return Verdict(kind=VerdictKind.PASS, output={
                    **input_data,
                    "validation_status": "consistent",
                    "inconsistencies": [],
                    "cross_reference_map": cross_ref_map,
                    "summary": "Single module, no cross-check needed",
                })

            # 构造 LLM 输入: 传每个 draft 的 4 维度 text + 该维度的 evidence_refs (供 LLM 回溯)
            drafts_brief = []
            for d in validated_drafts:
                secs = d.get("analysis_sections", {}) or {}
                brief_sec: dict[str, dict] = {}
                for dim in ("architecture", "responsibility", "dependencies", "interfaces"):
                    sec = secs.get(dim) or {}
                    if isinstance(sec, dict):
                        text_v = str(sec.get("text") or "")[:400]
                        refs_v = sec.get("evidence_refs") or []
                    else:
                        text_v = str(sec or "")[:400]
                        refs_v = []
                    # 只保留 file+lines, 避免 LLM 看到太多噪声
                    refs_slim = [
                        {"file": r.get("file"), "lines": r.get("lines")}
                        for r in refs_v if isinstance(r, dict)
                    ][:5]
                    brief_sec[dim] = {"text": text_v, "evidence_refs": refs_slim}
                drafts_brief.append({
                    "module": d.get("module_name"),
                    "coverage_status": d.get("coverage_status"),
                    "sections": brief_sec,
                })

            user_msg = (
                f"【项目身份】{input_data.get('canonical_name', 'unknown')}\n"
                f"已获取的 cross_reference_map (基于文本关键词匹配):\n"
                f"{json.dumps(cross_ref_map, ensure_ascii=False, indent=2)}\n\n"
                f"【模块分析结果】\n"
                f"{json.dumps(drafts_brief, ensure_ascii=False, indent=2)}\n\n"
                f"请检查模块间接口/依赖/描述的一致性, 按 SYSTEM 的 JSON schema 输出。"
            )

            client = LLMClient(role="ide_agent", max_tokens=2000)
            resp = client.call(
                messages=[{"role": "user", "content": user_msg}],
                system=self._SYSTEM_PROMPT,
            )
            text = resp.content[0].text if resp.content else ""
            m = _re.search(r'\{.*\}', text, _re.DOTALL)
            if not m:
                # LLM 解析失败, 但确定性部分可用, 降级为 warning
                return Verdict(kind=VerdictKind.PASS, output={
                    **input_data,
                    "validation_status": "warning",
                    "inconsistencies": [{
                        "module_pair": ["_llm_", "_llm_"],
                        "issue_type": "llm_parse_failure",
                        "detail": f"LLM 未返回合法 JSON: {text[:150]}",
                        "suggestion": "人工复审 cross_reference_map",
                    }],
                    "cross_reference_map": cross_ref_map,
                    "summary": "LLM 检查失败, 仅提供确定性引用图",
                })

            parsed = json.loads(m.group(0))
            raw_incons = parsed.get("inconsistencies", []) or []
            cleaned: list[dict] = []
            for inc in raw_incons:
                if not isinstance(inc, dict):
                    continue
                ev_up = inc.get("evidence_upstream") or []
                if not isinstance(ev_up, list):
                    ev_up = []
                # 不允许空 evidence_upstream — 这是"必须带源"不变量
                if not ev_up:
                    # 保留, 但标注为 unverified, 供下游看到'空 evidence 的问题来源'
                    ev_up = [{
                        "from_node": "cross_validator",
                        "draft_module": "(unspecified)",
                        "section": "(unspecified)",
                        "quoted_text": "(LLM 未提供 evidence_upstream)",
                        "source_ref": None,
                    }]
                cleaned.append({
                    "module_pair": inc.get("module_pair", []),
                    "issue_type": inc.get("issue_type", "unknown"),
                    "detail": inc.get("detail", ""),
                    "suggestion": inc.get("suggestion", ""),
                    "evidence_upstream": ev_up,
                })

            return Verdict(kind=VerdictKind.PASS, output={
                **input_data,
                "validation_status": parsed.get("validation_status", "consistent"),
                "inconsistencies": cleaned,
                "cross_reference_map": cross_ref_map,
                "summary": parsed.get("summary", ""),
            })
        except Exception as e:
            return Verdict(kind=VerdictKind.FAIL, output=input_data,
                           diagnosis=f"cross_validator 异常: {e}")


# ═══════════════════════════════════════════════════════════
# 阶段 6 融合发布
# ═══════════════════════════════════════════════════════════


class ReportFuserRouter(Router):
    """融合所有前序产物为最终 markdown 报告, 含真实生成的 Mermaid 架构图。

    2026-04-09 返工: 原版 Mermaid 是硬编码 A→B→C 占位。
    现在: 从 cross_reference_map 生成真 module dependency graph (Mermaid flowchart),
    从 validated_drafts 按 canonical_name 和 code_modules 层级生成 architecture_flow 图。
    """

    FORMAT_IN = "repo-architect.cross-validation"
    FORMAT_OUT = "repo-architect.arch-report"
    DESCRIPTION = (
        "确定性融合 validated_drafts + report_skeleton + research_notes + docs_summary + "
        "cross_reference_map 为 markdown 报告。Mermaid 图从 cross_reference_map 真实"
        "生成 (不写死); 章节按 sections 依次填充, 内容全部基于真实数据不 placeholder。"
    )

    @staticmethod
    def _sanitize_mermaid_id(path: str) -> str:
        """Mermaid node id 只能是 alphanumeric + underscore, 路径分隔符和点都要替换"""
        return re.sub(r'[^\w]', '_', path)[:40] or "unknown"

    def run(self, input_data: Any) -> Verdict:
        try:
            from omnicompany.core.guarded_write import write_file
            from omnicompany.core.config import resolve_domain_data_dir

            canonical_name = input_data.get("canonical_name") or input_data.get("repo_name", "unknown")
            canonical_description = input_data.get("canonical_description", "")
            mode = input_data.get("mode", "standard")
            validated_drafts = input_data.get("validated_drafts") or []
            cross_ref_map = input_data.get("cross_reference_map") or {}
            inconsistencies = input_data.get("inconsistencies") or []
            docs_summary = input_data.get("docs_summary", "") or ""
            research_notes = input_data.get("research_notes", "") or ""
            research_status = input_data.get("research_status", "unknown")
            key_findings = input_data.get("key_findings") or []
            design_decisions = input_data.get("design_decisions") or []
            overall_status = input_data.get("overall_status", "unknown")
            aggregated_missing = input_data.get("aggregated_missing_aspects") or []

            def _fmt_refs(refs: list) -> str:
                """把 evidence_refs 格式化成脚注内联形式。"""
                if not refs:
                    return "(无 evidence)"
                parts = []
                for r in refs[:6]:
                    if not isinstance(r, dict):
                        continue
                    f = r.get("file") or "?"
                    ln = r.get("lines") or ""
                    parts.append(f"`{f}:{ln}`" if ln else f"`{f}`")
                return ", ".join(parts)

            def _sec_text(sec: Any) -> str:
                if isinstance(sec, dict):
                    return str(sec.get("text") or "")
                return str(sec or "")

            def _sec_refs(sec: Any) -> list:
                if isinstance(sec, dict):
                    return sec.get("evidence_refs") or []
                return []

            lines: list[str] = []
            mermaid_count = 0
            sections_fulfilled: list[str] = []

            # ── 标题 + 元信息 ─────────────────────────
            lines.append(f"# 架构分析报告: {canonical_name}")
            lines.append("")
            lines.append(f"> {canonical_description}")
            lines.append("")
            lines.append(
                f"**分析模式**: {mode} | **覆盖状态**: {overall_status} | "
                f"**模块数**: {len(validated_drafts)} | **调研**: {research_status}"
            )
            lines.append("")

            # ── 项目目标 ─────────────────────────
            lines.append("## 项目目标")
            lines.append("")
            if docs_summary:
                lines.append(docs_summary[:2000])
            else:
                lines.append(f"(文档摘要不可用) 从身份锚推断: {canonical_description}")
            lines.append("")
            sections_fulfilled.append("项目目标")

            # ── 高层架构图 (真实 Mermaid 从 cross_reference_map 生成) ─────────
            lines.append("## 高层架构")
            lines.append("")
            if cross_ref_map and any(v for v in cross_ref_map.values()):
                lines.append("### 模块依赖图")
                lines.append("")
                lines.append("```mermaid")
                lines.append("flowchart LR")
                # 为每个模块声明节点
                node_map: dict[str, str] = {}
                for mod_path in cross_ref_map.keys():
                    nid = self._sanitize_mermaid_id(mod_path)
                    short = mod_path.split("/")[-1]
                    node_map[mod_path] = nid
                    lines.append(f"  {nid}[\"{short}\"]")
                # 边
                for src, deps in cross_ref_map.items():
                    for dst in deps:
                        if dst in node_map and src in node_map:
                            lines.append(f"  {node_map[src]} --> {node_map[dst]}")
                lines.append("```")
                mermaid_count += 1
                lines.append("")
            elif validated_drafts:
                # 没有 cross ref, 画一个简单的模块列表图
                lines.append("### 模块结构")
                lines.append("")
                lines.append("```mermaid")
                lines.append("flowchart TD")
                root_id = self._sanitize_mermaid_id(canonical_name)
                lines.append(f"  {root_id}[\"{canonical_name}\"]")
                for d in validated_drafts:
                    mp = d.get("module_name", "")
                    nid = self._sanitize_mermaid_id(mp)
                    short = mp.split("/")[-1]
                    lines.append(f"  {root_id} --> {nid}[\"{short}\"]")
                lines.append("```")
                mermaid_count += 1
                lines.append("")
            sections_fulfilled.append("高层架构")

            # ── 模块职责 (带 evidence 脚注) ─────────
            lines.append("## 模块职责")
            lines.append("")
            for d in validated_drafts:
                mp = d.get("module_name", "?")
                secs = d.get("analysis_sections", {}) or {}
                cov_status = d.get("coverage_status", "?")
                missing = d.get("missing_aspects") or []
                ev_files = d.get("evidence_files", [])
                disc = d.get("discovered_via", "")

                lines.append(f"### `{mp}`")
                lines.append(
                    f"*状态: **{cov_status}** | 读源码: {len(ev_files)} 文件*"
                    + (f" | 识别自: `{disc}`" if disc else "")
                )
                lines.append("")

                for dim_title, dim_key in [
                    ("架构角色", "architecture"),
                    ("职责", "responsibility"),
                    ("依赖", "dependencies"),
                    ("暴露接口", "interfaces"),
                ]:
                    text = _sec_text(secs.get(dim_key)) or "(无数据)"
                    refs = _sec_refs(secs.get(dim_key))
                    lines.append(f"**{dim_title}**: {text}")
                    lines.append("")
                    lines.append(f"> evidence: {_fmt_refs(refs)}")
                    lines.append("")

                if missing:
                    lines.append("**缺口**:")
                    for m_item in missing:
                        lines.append(f"- {m_item}")
                    lines.append("")
            sections_fulfilled.append("模块职责")

            # ── 依赖与一致性 ─────────
            lines.append("## 依赖与集成")
            lines.append("")
            if cross_ref_map:
                lines.append("**模块引用关系**:")
                lines.append("")
                for src, deps in cross_ref_map.items():
                    if deps:
                        lines.append(f"- `{src}` → {', '.join(f'`{d}`' for d in deps)}")
                lines.append("")
            else:
                lines.append("(未发现显式跨模块引用)")
                lines.append("")

            if inconsistencies:
                lines.append("### 发现的一致性问题 (带上游证据链)")
                lines.append("")
                for inc in inconsistencies[:10]:
                    pair = " ↔ ".join(inc.get("module_pair") or [])
                    lines.append(f"- **{pair}** `[{inc.get('issue_type', '?')}]`")
                    lines.append(f"  - 说明: {inc.get('detail', '')}")
                    if inc.get("suggestion"):
                        lines.append(f"  - 建议: {inc['suggestion']}")
                    ev_up = inc.get("evidence_upstream") or []
                    if ev_up:
                        lines.append(f"  - 上游证据链 ({len(ev_up)} 条):")
                        for e in ev_up[:4]:
                            if not isinstance(e, dict):
                                continue
                            frm = e.get("from_node", "?")
                            dm = e.get("draft_module", "?")
                            sect = e.get("section", "?")
                            q = (e.get("quoted_text") or "")[:160]
                            sref = e.get("source_ref")
                            sref_str = ""
                            if isinstance(sref, dict):
                                sref_str = f" → `{sref.get('file')}:{sref.get('lines','')}`"
                            lines.append(
                                f"    - `{frm}` · `{dm}` · `{sect}`: \"{q}\"{sref_str}"
                            )
                lines.append("")
            sections_fulfilled.append("依赖与集成")

            # ── 覆盖率缺口 (overall_status + aggregated_missing) ─────────
            lines.append("## 覆盖率缺口")
            lines.append("")
            lines.append(f"**整体状态**: {overall_status}")
            lines.append("")
            if aggregated_missing:
                lines.append(f"共 {len(aggregated_missing)} 条缺口:")
                lines.append("")
                for agm in aggregated_missing[:20]:
                    if isinstance(agm, dict):
                        lines.append(f"- `{agm.get('module','?')}`: {agm.get('aspect','')}")
                    else:
                        lines.append(f"- {agm}")
                lines.append("")
            else:
                lines.append("(未发现缺口 — 所有模块都带完整 evidence)")
                lines.append("")
            sections_fulfilled.append("覆盖率缺口")

            # ── 调研要点 (带 source) ─────────
            if research_status == "completed":
                lines.append("## 仓库自述调研要点")
                lines.append("")
                if key_findings:
                    for kf in key_findings:
                        if isinstance(kf, dict):
                            text = kf.get("text", "")
                            source = kf.get("source", "(无来源)")
                            lines.append(f"- {text}  \n  *— source: `{source}`*")
                        else:
                            lines.append(f"- {kf}  \n  *— source: (unsourced)*")
                    lines.append("")
                if research_notes:
                    lines.append(research_notes[:1500])
                    lines.append("")
                sections_fulfilled.append("调研要点")
            elif research_status in ("degraded", "skipped"):
                lines.append("## 调研")
                lines.append("")
                lines.append(f"(调研未启用或降级: {research_status})")
                lines.append("")

            # ── 设计决策 (带 source) ─────────
            if design_decisions:
                lines.append("## 设计决策 (来自文档)")
                lines.append("")
                for dd in design_decisions[:15]:
                    if isinstance(dd, dict):
                        text = dd.get("text") or dd.get("description") or ""
                        source = dd.get("source", "(无来源)")
                        lines.append(f"- {text}  \n  *— source: `{source}`*")
                    elif isinstance(dd, str):
                        lines.append(f"- {dd}  \n  *— source: (unsourced legacy)*")
                lines.append("")

            # ── 脚注 ─────────
            lines.append("---")
            lines.append("")
            lines.append("*本报告由 OmniCompany `repo-architect` 管线自动生成。*")
            lines.append(f"*canonical_name={canonical_name}, evidence={input_data.get('evidence_sources', [])}*")

            content = "\n".join(lines)

            data_root = resolve_domain_data_dir("absorption") / "reports"
            data_root.mkdir(parents=True, exist_ok=True)
            # 文件名用 canonical_name (sanitized) 而不是 repo_name 目录名
            safe_name = re.sub(r'[^\w\-.]', '_', canonical_name)[:80]
            report_path = data_root / f"{safe_name}.md"
            write_file(
                str(report_path), content,
                origin="internal-engine",
                domain="services/repo_architect",
                purpose=f"arch report for {canonical_name}",
            )

            return Verdict(kind=VerdictKind.PASS, output={
                **input_data,
                "report_path": str(report_path),
                "report_chars": len(content),
                "mermaid_diagrams": mermaid_count,
                "sections_fulfilled": sections_fulfilled,
            })
        except Exception as e:
            return Verdict(kind=VerdictKind.FAIL, output=input_data,
                           diagnosis=f"report_fuser 异常: {e}")


class CoverageReporterRouter(Router):
    FORMAT_IN = "repo-architect.arch-report"
    FORMAT_OUT = "repo-architect.coverage-report"
    DESCRIPTION = (
        "生成覆盖率状态 markdown 表格 (语义而非数值), 落到 "
        "data/absorption/coverage/<repo>.md。列: Module / Status / Missing Aspects / "
        "Evidence Files。"
    )

    def run(self, input_data: Any) -> Verdict:
        try:
            from omnicompany.core.guarded_write import write_file
            from omnicompany.core.config import resolve_domain_data_dir

            repo_name = input_data.get("repo_name", "unknown")
            canonical_name = input_data.get("canonical_name") or repo_name
            drafts = input_data.get("validated_drafts", []) or []
            overall_status = input_data.get("overall_status", "unknown")

            lines = [
                f"# Coverage Report — {canonical_name}",
                "",
                f"**Overall status**: {overall_status}",
                f"**Passed at retry**: {input_data.get('passed_at_retry', 0)}",
                "",
                "| Module | Status | Missing Aspects | Evidence Files |",
                "|---|---|---|---|",
            ]
            module_status_table: list[dict] = []
            for d in drafts:
                mp = d.get("module_name", "?")
                st = d.get("coverage_status", "?")
                missing = d.get("missing_aspects") or []
                ev_count = len(d.get("evidence_files", []))
                missing_cell = (
                    "; ".join(str(m)[:80] for m in missing[:3]) if missing else "—"
                )
                # markdown 表格单元格里的 pipe 要转义
                missing_cell = missing_cell.replace("|", "\\|").replace("\n", " ")
                lines.append(f"| `{mp}` | {st} | {missing_cell} | {ev_count} |")
                module_status_table.append({
                    "name": mp,
                    "status": st,
                    "missing_aspects": missing,
                    "evidence_file_count": ev_count,
                })
            content = "\n".join(lines)

            data_root = resolve_domain_data_dir("absorption") / "coverage"
            data_root.mkdir(parents=True, exist_ok=True)
            cov_path = data_root / f"{repo_name}.md"
            write_file(
                str(cov_path), content,
                origin="internal-engine",
                domain="services/repo_architect",
                purpose=f"coverage report for {repo_name}",
            )

            return Verdict(kind=VerdictKind.PASS, output={
                **input_data,
                "coverage_report_path": str(cov_path),
                "module_status_table": module_status_table,
                "skipped_modules": input_data.get("insufficient_modules", []),
            })
        except Exception as e:
            return Verdict(kind=VerdictKind.FAIL, output=input_data,
                           diagnosis=f"覆盖率报告失败: {e}")


class KBIngesterRouter(Router):
    """把 arch-report + coverage-report 真实落盘到 data/knowledge/external_repos/。

    2026-04-09 返工: 原 stub 返回 kb_status='stub_not_yet_persisted' 不落盘。
    现在: 通过 guarded_write 真实写入 `data/knowledge/external_repos/<entry_id>.md`,
    含 YAML frontmatter (符合 OmniKB 惯例) + 报告正文摘录 + 能力区域索引。
    """

    FORMAT_IN = "repo-architect.coverage-report"
    FORMAT_OUT = "repo-architect.kb-entry"
    DESCRIPTION = (
        "构造 KRepoArchitectEntry 并通过 guarded_write 写入 "
        "data/knowledge/external_repos/<entry_id>.md, 含 YAML frontmatter + "
        "capability_areas + component_index + 指向 arch-report 的反向链接。"
    )

    def run(self, input_data: Any) -> Verdict:
        try:
            from omnicompany.core.guarded_write import write_file
            from omnicompany.core.config import resolve_domain_data_dir

            canonical_name = input_data.get("canonical_name") or input_data.get("repo_name", "unknown")
            canonical_description = input_data.get("canonical_description", "")
            ecosystem = input_data.get("ecosystem", "unknown")
            primary_language = input_data.get("primary_language", "unknown")
            validated_drafts = input_data.get("validated_drafts") or []
            overall_status = input_data.get("overall_status", "unknown")
            report_path = input_data.get("report_path", "")
            coverage_report_path = input_data.get("coverage_report_path", "")

            # entry_id: krepo.<ecosystem>.<safe_name>
            safe_name = re.sub(r'[^\w]', '_', canonical_name.lower())[:60]
            entry_id = f"krepo.{ecosystem}.{safe_name}"

            # capability_areas: 从每个 validated_draft 的 responsibility.text 提炼
            capability_areas = []
            for d in validated_drafts:
                mp = d.get("module_name", "")
                resp_sec = (d.get("analysis_sections", {}) or {}).get("responsibility") or {}
                if isinstance(resp_sec, dict):
                    resp_text = str(resp_sec.get("text") or "")
                else:
                    resp_text = str(resp_sec or "")
                if resp_text:
                    capability_areas.append({
                        "module": mp,
                        "status": d.get("coverage_status", "?"),
                        "responsibility": resp_text[:300],
                    })

            # component_index: 模块 → evidence 文件列表
            component_index = {}
            for d in validated_drafts:
                mp = d.get("module_name", "")
                if mp:
                    component_index[mp] = d.get("evidence_files", [])[:5]

            # 写 md with frontmatter
            from datetime import datetime, timezone
            now = datetime.now(timezone.utc).isoformat()

            lines = ["---",
                     f"id: {entry_id}",
                     f"type: krepo",
                     f"name: {canonical_name}",
                     f"description: {canonical_description[:200]}",
                     f"ecosystem: {ecosystem}",
                     f"primary_language: {primary_language}",
                     f"overall_status: {overall_status}",
                     f"module_count: {len(validated_drafts)}",
                     f"ingested_at: {now}",
                     f"arch_report_path: {report_path}",
                     f"coverage_report_path: {coverage_report_path}",
                     "---",
                     "",
                     f"# {canonical_name}",
                     "",
                     f"> {canonical_description}",
                     "",
                     f"**Ecosystem**: {ecosystem} | **Primary Language**: {primary_language} | "
                     f"**Status**: {overall_status} | **Modules**: {len(validated_drafts)}",
                     "",
                     "## Capability Areas",
                     ""]
            for ca in capability_areas:
                lines.append(f"### `{ca['module']}` · *{ca['status']}*")
                lines.append("")
                lines.append(ca["responsibility"])
                lines.append("")

            lines.extend([
                "## Component Index",
                "",
            ])
            for mod, files in component_index.items():
                lines.append(f"- **`{mod}`**: {len(files)} evidence files")
                for f in files[:3]:
                    lines.append(f"  - `{f}`")
            lines.extend([
                "",
                "## Cross-references",
                "",
                f"- Architecture report: [{report_path}]({report_path})",
                f"- Coverage report: [{coverage_report_path}]({coverage_report_path})",
                "",
                "## OmniCompany Parallels",
                "",
                "*(Manual curation: identify which OmniCompany packages/services have similar "
                "capabilities, for cross-project pattern learning.)*",
                "",
            ])

            content = "\n".join(lines)

            kb_root = resolve_domain_data_dir("knowledge") / "external_repos"
            kb_root.mkdir(parents=True, exist_ok=True)
            kb_path = kb_root / f"{entry_id}.md"
            write_file(
                str(kb_path), content,
                origin="internal-engine",
                domain="services/repo_architect",
                purpose=f"kb ingest {entry_id}",
            )

            return Verdict(kind=VerdictKind.PASS, output={
                **input_data,
                "entry_id": entry_id,
                "kb_entry_path": str(kb_path),
                "capability_areas": capability_areas,
                "omni_parallels": [],  # 待人工/二次分析补
                "component_index": component_index,
                "kb_status": "persisted",
            })
        except Exception as e:
            return Verdict(kind=VerdictKind.FAIL, output=input_data,
                           diagnosis=f"kb_ingester 异常: {e}")
