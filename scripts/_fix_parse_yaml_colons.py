"""扫 prefab_parses/ 下 parse.yaml, 把含未转义 ':' 的字符串值用 "" 包起来.

策略: 简单试 yaml.safe_load; 失败时找到 fail 行 (例 "role: 背包主视图. 绑定 (行 57-152): grid"),
把 ':' 后到行尾的 value 用双引号包 (转义内部 " 跟 \).
"""
import re
import yaml
from pathlib import Path

PARSES = Path("/workspace/omnicompany/data/domains/gameplay_system_ux/prefab_parses")


def try_fix(p: Path) -> tuple[bool, str]:
    txt = p.read_text("utf-8", errors="replace")
    try:
        yaml.safe_load(txt)
        return False, "ok"
    except yaml.YAMLError:
        pass

    # 简单 line-by-line 找含 unquoted ':' 的 value 行
    lines = txt.split("\n")
    fixed_lines = []
    fixed_count = 0
    for line in lines:
        # 匹: indent + key: + value (含 ':') + 不是 list/dict 起头, 不是已 quote
        m = re.match(r"^(\s*[a-zA-Z_][\w_]*:\s+)(?!\s*[\[\{|>])([^\n]+)$", line)
        if not m:
            fixed_lines.append(line)
            continue
        prefix, value = m.group(1), m.group(2)
        # 跳过已 quote, 跳过 list item (有 - 起头实际进不来这分支), 跳过纯数字/bool
        if value[:1] in '"\'':
            fixed_lines.append(line)
            continue
        # 看 value 是否真含 ':' (后跟空格), 且不只是 url path
        if not re.search(r":\s", value):
            fixed_lines.append(line)
            continue
        # 排除 url 形式 (d:/X 这种 drive letter)
        if re.match(r"^[a-zA-Z]:[/\\]", value):
            fixed_lines.append(line)
            continue
        # quote
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        fixed_lines.append(f'{prefix}"{escaped}"')
        fixed_count += 1
    new_txt = "\n".join(fixed_lines)

    # 验证修后可解析
    try:
        yaml.safe_load(new_txt)
    except yaml.YAMLError as e:
        return False, f"still fail after fix: {e}"

    p.write_text(new_txt, "utf-8")
    return True, f"fixed {fixed_count} lines"


if __name__ == "__main__":
    total = 0; ok = 0
    for p in sorted(PARSES.rglob("parse.yaml")):
        total += 1
        fixed, msg = try_fix(p)
        if fixed:
            ok += 1
            print(f"✓ {p.relative_to(PARSES)}: {msg}")
        else:
            print(f"  {p.relative_to(PARSES)}: {msg}")
    print(f"\n{ok}/{total} 修过")
