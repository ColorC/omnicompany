# [OMNI] origin=claude-code domain=evolution/workflow ts=2026-04-08T03:23:38Z
# [OMNI] material_id="material:core.evolution.workflow.user_inquiry_system.py"
"""用户询问接口

当进化工作流无法自主判断时（error_category=needs_user_clarification），
将问题提交到询问队列，等待用户通过 CLI/网页/文件回答。

设计原则：
- 问题以 SQLite 持久化，进程重启不丢失
- 每个问题附带完整上下文（board_id, trace_id, 诊断上下文）
- 回答后自动唤醒等待中的进化流程
- CLI: omnicompany inquiry list / answer <id> <text>
"""
from __future__ import annotations

import asyncio
import json
import logging
import sqlite3
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

_DEFAULT_DB = "omnicompany_inquiries.db"


# ── 数据结构 ──

@dataclass
class UserInquiry:
    """单条用户询问"""

    id: str
    board_id: str
    trace_id: str
    pipeline_id: str

    question: str
    """具体向用户提出的问题"""

    context: str
    """诊断上下文（根因节点、已有证据等）"""

    error_category_suspected: str = "needs_user_clarification"
    tags: list[str] = field(default_factory=list)

    status: str = "pending"
    """pending | answered | expired"""

    answer: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    answered_at: str = ""

    @staticmethod
    def new(
        board_id: str,
        trace_id: str,
        pipeline_id: str,
        question: str,
        context: str = "",
        tags: list[str] | None = None,
    ) -> "UserInquiry":
        return UserInquiry(
            id=str(uuid.uuid4())[:8],
            board_id=board_id,
            trace_id=trace_id,
            pipeline_id=pipeline_id,
            question=question,
            context=context,
            tags=tags or [],
        )


# ── 存储层 ──

class UserInquiryStore:
    """SQLite 持久化询问队列"""

    def __init__(self, db_path: str = _DEFAULT_DB):
        self.db_path = db_path
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS inquiries (
                    id TEXT PRIMARY KEY,
                    board_id TEXT,
                    trace_id TEXT,
                    pipeline_id TEXT,
                    question TEXT,
                    context TEXT,
                    status TEXT DEFAULT 'pending',
                    answer TEXT DEFAULT '',
                    created_at TEXT,
                    answered_at TEXT DEFAULT '',
                    tags TEXT DEFAULT '[]',
                    error_category_suspected TEXT DEFAULT 'needs_user_clarification'
                )
            """)
            conn.commit()

    def submit(self, inquiry: UserInquiry) -> str:
        """提交一条询问，返回 inquiry.id"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT OR REPLACE INTO inquiries
                  (id, board_id, trace_id, pipeline_id, question, context,
                   status, answer, created_at, answered_at, tags, error_category_suspected)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                inquiry.id, inquiry.board_id, inquiry.trace_id, inquiry.pipeline_id,
                inquiry.question, inquiry.context,
                inquiry.status, inquiry.answer,
                inquiry.created_at, inquiry.answered_at,
                json.dumps(inquiry.tags, ensure_ascii=False),
                inquiry.error_category_suspected,
            ))
            conn.commit()
        logger.info("[inquiry] Submitted inquiry %s: %s", inquiry.id, inquiry.question[:80])
        return inquiry.id

    def answer(self, inquiry_id: str, answer_text: str) -> bool:
        """回答一条询问，返回是否成功"""
        now = datetime.now(timezone.utc).isoformat()
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.execute(
                "UPDATE inquiries SET status='answered', answer=?, answered_at=? WHERE id=?",
                (answer_text, now, inquiry_id),
            )
            conn.commit()
            if cur.rowcount == 0:
                logger.warning("[inquiry] Inquiry %s not found", inquiry_id)
                return False
        logger.info("[inquiry] Answered inquiry %s", inquiry_id)
        return True

    def get(self, inquiry_id: str) -> UserInquiry | None:
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT * FROM inquiries WHERE id=?", (inquiry_id,)
            ).fetchone()
        if not row:
            return None
        return self._row_to_inquiry(row)

    def list_pending(self) -> list[UserInquiry]:
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT * FROM inquiries WHERE status='pending' ORDER BY created_at DESC"
            ).fetchall()
        return [self._row_to_inquiry(r) for r in rows]

    def list_all(self, limit: int = 50) -> list[UserInquiry]:
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT * FROM inquiries ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [self._row_to_inquiry(r) for r in rows]

    @staticmethod
    def _row_to_inquiry(row: tuple) -> UserInquiry:
        # id, board_id, trace_id, pipeline_id, question, context,
        # status, answer, created_at, answered_at, tags, error_category_suspected
        return UserInquiry(
            id=row[0], board_id=row[1], trace_id=row[2], pipeline_id=row[3],
            question=row[4], context=row[5],
            status=row[6], answer=row[7],
            created_at=row[8], answered_at=row[9],
            tags=json.loads(row[10]) if row[10] else [],
            error_category_suspected=row[11] if len(row) > 11 else "needs_user_clarification",
        )


# ── 异步等待接口 ──

class InquiryAwaiter:
    """轮询等待询问被回答（供 orchestrator 用）

    用法：
        awaiter = InquiryAwaiter(store, inquiry_id)
        answer = await awaiter.wait(timeout=3600)
    """

    def __init__(self, store: UserInquiryStore, inquiry_id: str, poll_interval: float = 5.0):
        self._store = store
        self._id = inquiry_id
        self._poll_interval = poll_interval

    async def wait(self, timeout: float = 3600.0) -> str | None:
        """等待回答，返回 answer 文本。超时返回 None。"""
        elapsed = 0.0
        while elapsed < timeout:
            inq = self._store.get(self._id)
            if inq and inq.status == "answered":
                return inq.answer
            await asyncio.sleep(self._poll_interval)
            elapsed += self._poll_interval
        logger.warning("[inquiry] Timeout waiting for inquiry %s", self._id)
        return None


# ── 文件回答接口（离线模式）──

def write_inquiry_to_file(inquiry: UserInquiry, out_dir: str = ".") -> Path:
    """将询问写到文件，供用户直接编辑 answer 字段后回答"""
    out_path = Path(out_dir) / f"inquiry_{inquiry.id}.json"
    data = {
        "id": inquiry.id,
        "question": inquiry.question,
        "context": inquiry.context,
        "board_id": inquiry.board_id,
        "pipeline_id": inquiry.pipeline_id,
        "answer": "",  # 用户填写这里
        "_instructions": "在 answer 字段填写答案后，运行: omnicompany inquiry answer <id> <answer>",
    }
    out_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("[inquiry] Inquiry file written: %s", out_path)
    return out_path


# ── 全局默认 store 实例（供 orchestrator 直接使用）──

_default_store: UserInquiryStore | None = None


def get_default_store(db_path: str = _DEFAULT_DB) -> UserInquiryStore:
    global _default_store
    if _default_store is None or _default_store.db_path != db_path:
        _default_store = UserInquiryStore(db_path)
    return _default_store
