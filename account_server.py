#!/usr/bin/env python3
"""账号服务 - FastAPI"""
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI(title="Guess Account Server", version="1.0.0")

DB_PATH = Path(__file__).parent / "data" / "guess.db"


@contextmanager
def get_db():
    """数据库连接上下文管理器"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


# --- 请求/响应模型 ---

class CreateAccountRequest(BaseModel):
    device_id: str
    nickname: str


class UpdateNicknameRequest(BaseModel):
    device_id: str
    nickname: str


class RecordGameRequest(BaseModel):
    user_id: int
    correct: bool
    date: str
    hint_index: int = -1


class UserResponse(BaseModel):
    id: int
    nickname: str


class AccountResponse(BaseModel):
    success: bool
    user: Optional[UserResponse] = None
    error: Optional[str] = None


class SummaryResponse(BaseModel):
    success: bool
    summary: dict


class TodayResponse(BaseModel):
    success: bool
    today: dict


class RecordResponse(BaseModel):
    success: bool


# --- 健康检查 ---

@app.get("/health")
async def health():
    return {"status": "ok", "service": "account"}


# --- 用户 API ---

@app.post("/api/account/create")
async def create_account(req: CreateAccountRequest) -> AccountResponse:
    """创建新用户"""
    with get_db() as conn:
        try:
            cursor = conn.execute(
                "INSERT INTO users (device_id, nickname) VALUES (?, ?)",
                (req.device_id, req.nickname)
            )
            conn.commit()
            user_id = cursor.lastrowid
            return AccountResponse(
                success=True,
                user=UserResponse(id=user_id, nickname=req.nickname)
            )
        except sqlite3.IntegrityError:
            # 设备ID已存在，返回现有用户
            row = conn.execute(
                "SELECT id, nickname FROM users WHERE device_id = ?",
                (req.device_id,)
            ).fetchone()
            return AccountResponse(
                success=True,
                user=UserResponse(id=row["id"], nickname=row["nickname"])
            )


@app.get("/api/account/by_device/{device_id}")
async def get_account(device_id: str) -> AccountResponse:
    """根据设备ID查询用户"""
    with get_db() as conn:
        row = conn.execute(
            "SELECT id, nickname FROM users WHERE device_id = ?",
            (device_id,)
        ).fetchone()
        if row:
            return AccountResponse(
                success=True,
                user=UserResponse(id=row["id"], nickname=row["nickname"])
            )
        return AccountResponse(success=False, error="not_found")


@app.put("/api/account/nickname")
async def updateNickname(req: UpdateNicknameRequest) -> AccountResponse:
    """更新昵称"""
    with get_db() as conn:
        conn.execute(
            "UPDATE users SET nickname = ?, updated_at = ? WHERE device_id = ?",
            (req.nickname, datetime.now().isoformat(), req.device_id)
        )
        conn.commit()
        return AccountResponse(success=True)


# --- 统计 API ---

@app.get("/api/stats/summary/{user_id}")
async def get_summary(user_id: int) -> SummaryResponse:
    """获取用户统计汇总"""
    with get_db() as conn:
        row = conn.execute(
            """
            SELECT
                COALESCE(SUM(correct_count), 0) as correct_count,
                COALESCE(SUM(wrong_count), 0) as wrong_count,
                COALESCE(SUM(total_count), 0) as total_count
            FROM statistics WHERE user_id = ?
            """,
            (user_id,)
        ).fetchone()

        total = row["total_count"]
        correct = row["correct_count"]
        accuracy = (correct / total * 100) if total > 0 else 0.0

        return SummaryResponse(
            success=True,
            summary={
                "correct_count": correct,
                "wrong_count": row["wrong_count"],
                "total_count": total,
                "accuracy": round(accuracy, 1)
            }
        )


@app.get("/api/stats/today/{user_id}")
async def get_today(user_id: int) -> TodayResponse:
    """获取今日统计"""
    today_str = date.today().isoformat()
    with get_db() as conn:
        row = conn.execute(
            """
            SELECT correct_count, wrong_count, total_count
            FROM statistics WHERE user_id = ? AND date = ?
            """,
            (user_id, today_str)
        ).fetchone()

        if row:
            return TodayResponse(
                success=True,
                today={
                    "correct_count": row["correct_count"],
                    "wrong_count": row["wrong_count"],
                    "total_count": row["total_count"]
                }
            )
        return TodayResponse(
            success=True,
            today={"correct_count": 0, "wrong_count": 0, "total_count": 0}
        )


@app.post("/api/stats/record")
async def record_game(req: RecordGameRequest) -> RecordResponse:
    """记录答题结果"""
    with get_db() as conn:
        # 插入答题详情
        correct_val = 1 if req.correct else 0
        conn.execute(
            """
            INSERT INTO game_records (user_id, date, correct, hint_index)
            VALUES (?, ?, ?, ?)
            """,
            (req.user_id, req.date, correct_val, req.hint_index)
        )

        # 更新统计汇总（使用 UPSERT）
        conn.execute(
            """
            INSERT INTO statistics (user_id, date, correct_count, wrong_count, total_count)
            VALUES (?, ?, ?, ?, 1)
            ON CONFLICT(user_id, date) DO UPDATE SET
                correct_count = correct_count + ?,
                wrong_count = wrong_count + ?,
                total_count = total_count + 1
            """,
            (req.user_id, req.date, correct_val, 1 - correct_val,
             correct_val, 1 - correct_val)
        )

        conn.commit()
        return RecordResponse(success=True)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
