import os
import shutil
import argparse
import re
from pathlib import Path

# Configuration
SOURCE_REPO = r"/workspace\omnicompany"
TARGET_REPO = r"/workspace\omnicompany-public"

# Exact directory names to completely ignore
IGNORE_DIRS = {
    "docs", "data", "logs", ".pytest_cache", "__pycache__", 
    "venv", ".worktrees", ".omni", "plans", ".git", "node_modules", ".next", "dist", "build", ".vite"
}

# Substrings that must not appear in any path or filename (case-insensitive)
BANNED_PATH_KEYWORDS = ["gameplay_system", "excel", "csv", "unity"]
# Substrings that must not appear in any file contents (case-insensitive)
BANNED_CONTENT_KEYWORDS = [
    "gameplay_system", "excel", "csv", "unity",
    "the_company", "sk-", "secret"
]
# 2026-04-26 注: 关键词黑名单是反模式 (feedback_no_regex_for_language_work).
# 此脚本本身的核心策略已不可用 — 改用 agent 多轮 LLM 复审 (按 desensitization_matrix.yaml 矩阵).
# 此处保留原状作过渡; 真发布走 repo_exporter / privacy_publish 真实现 (Phase B 待做) 或 agent 直接复审.

def _contains_banned_keywords(text: str, keywords: list) -> bool:
    text_lower = text.lower()
    for kw in keywords:
        if kw.lower() in text_lower:
            return True
    return False

def _find_keyword_matches(text: str, keywords: list) -> list:
    """Returns a list of (line_num, match_word, line_text)"""
    matches = []
    lines = text.splitlines()
    for i, line in enumerate(lines, 1):
        line_lower = line.lower()
        for kw in keywords:
            if kw.lower() in line_lower:
                matches.append((i, kw, line.strip()[:100]))
    return matches

def is_path_allowed(path_relative: Path) -> bool:
    # Check parts for exact ignore dirs
    for part in path_relative.parts:
        if part in IGNORE_DIRS:
            return False
    
    # Check full relative path for banned substrings
    path_str = str(path_relative).lower()
    for kw in BANNED_PATH_KEYWORDS:
        if kw.lower() in path_str:
            return False
            
    return True

def sync_repos(dry_run=True):
    source_path = Path(SOURCE_REPO)
    target_path = Path(TARGET_REPO)
    
    if not source_path.exists():
        print(f"Error: Source repo {source_path} does not exist.")
        return
        
    print(f"Starting sync from {source_path} to {target_path}")
    print(f"Mode: {'REVIEW (Dry Run)' if dry_run else 'SYNC (Copy)'}")
    print("-" * 50)
    
    files_to_copy = []
    files_blocked_by_content = []
    files_blocked_by_path = []
    
    for root, dirs, files in os.walk(source_path):
        # Filter directories immediately to prune walk
        dirs[:] = [d for d in dirs if is_path_allowed(Path(root).relative_to(source_path) / d)]
        
        for file in files:
            full_file_path = Path(root) / file
            rel_path = full_file_path.relative_to(source_path)
            
            if not is_path_allowed(rel_path):
                files_blocked_by_path.append(str(rel_path))
                continue
                
            # Check content
            is_text = True
            content = ""
            try:
                # Attempt to read as utf-8 text text
                with open(full_file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
            except UnicodeDecodeError:
                # Not a standard text file or requires binary copy without inspection
                # Assuming all plaintext must be checked, binary can bypass text check
                # Note: We might want to verify if binary files shouldn't be copied.
                # Since task said "所有明文都必须经过关键词筛选", binaries don't have plaintext.
                is_text = False
            except Exception as e:
                print(f"Warning: Could not read {rel_path}: {e}")
                continue
                
            if is_text:
                matches = _find_keyword_matches(content, BANNED_CONTENT_KEYWORDS)
                if matches:
                    files_blocked_by_content.append({
                        'path': str(rel_path),
                        'matches': matches
                    })
                    continue
            
            # If we reach here, it's allowed
            files_to_copy.append(full_file_path)

    # Reporting
    print(f"\n--- SYNCHRONIZATION REPORT ---")
    print(f"Files blocked by PATH exclusions: {len(files_blocked_by_path)}")
    print(f"Files blocked by CONTENT keywords: {len(files_blocked_by_content)}")
    print(f"Files ready to copy: {len(files_to_copy)}")
    
    # 2026-04-08 (S3b.1): 不再写到仓库根（OMNI-015 forbidden-root-file 拦截）
    # 改写到 docs/reports/sync/ 下，按时间戳命名避免被覆盖
    from datetime import datetime as _dt
    report_dir = source_path / "docs" / "reports" / "sync"
    report_dir.mkdir(parents=True, exist_ok=True)
    ts = _dt.now().strftime("%Y%m%d-%H%M%S")
    report_file = report_dir / f"sync_review_report_{ts}.txt"
    with open(report_file, 'w', encoding='utf-8') as f:
        f.write("=== OMNICOMPANY PUBLIC SYNC REVIEW REPORT ===\n\n")
        f.write("FILES BLOCKED BY CONTENT KEYWORDS (Needs Manual Review/Redaction):\n")
        for item in files_blocked_by_content:
            f.write(f"\n- {item['path']}\n")
            for m in item['matches']:
                f.write(f"  Line {m[0]} (matched '{m[1]}'): {m[2]}\n")
                
        f.write("\n\nFILES BLOCKED BY PATH EXCLUSIONS:\n")
        for p in files_blocked_by_path:
            f.write(f"- {p}\n")
            
        f.write("\n\nFILES READY TO COPY:\n")
        for p in files_to_copy:
            f.write(f"- {p.relative_to(source_path)}\n")
            
    print(f"-> Detailed review report written to {report_file}")

    if not dry_run:
        print("\nExecuting copy...")
        copied_count = 0
        for src_file in files_to_copy:
            rel_path = src_file.relative_to(source_path)
            dst_file = target_path / rel_path
            
            dst_file.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src_file, dst_file)
            copied_count += 1
            
        print(f"Successfully copied {copied_count} files to {target_path}")
    else:
        print("\nDry run completed. No files were copied.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Sync omnicompany to public repository")
    parser.add_argument('--sync', action='store_true', help="Execute the file copying. Default is review ONLY (dry run).")
    args = parser.parse_args()
    
    sync_repos(dry_run=not args.sync)
