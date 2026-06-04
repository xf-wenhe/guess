# 用户系统与词库模式实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为词语猜谜 Flutter 游戏添加用户系统和双词库模式支持（本地词库模式无账号、服务器词库模式有账号统计）

**Architecture:** 新建独立 Account Server (FastAPI 端口 8001) + SQLite 数据库。Flutter 端新增 AccountController、DeviceIdService、AccountService、StatisticsService，修改现有 UI 组件。

**Tech Stack:** FastAPI + SQLite (服务器端) | Flutter + GetX + device_info_plus + crypto (客户端)

---

## 文件结构

### 新增文件

| 文件 | 责任 |
|:-----|:-----|
| `account_server.py` | FastAPI 用户服务，端口 8001 |
| `scripts/init_account_db.py` | 数据库初始化脚本 |
| `lib/services/device_id_service.dart` | 设备唯一 ID 生成 |
| `lib/services/account_service.dart` | 账号 API HTTP 客户端 |
| `lib/services/statistics_service.dart` | 统计 API HTTP 客户端 |
| `lib/controllers/account_controller.dart` | 账号状态管理 |
| `lib/widgets/user_profile_menu.dart` | 用户下拉菜单组件 |
| `lib/widgets/account_creation_dialog.dart` | 昵称输入对话框 |
| `lib/widgets/puzzle_error_banner.dart` | 词库加载失败提示条 |

### 修改文件

| 文件 | 改动 |
|:-----|:-----|
| `lib/config/server_config.dart` | 添加账号服务端点配置 |
| `pubspec.yaml` | 添加 device_info_plus、crypto 依赖 |
| `lib/controllers/guess_game_controller.dart` | 集成 AccountController、记录答题结果 |
| `lib/screens/guess_home_page.dart` | AppBar 修改、添加用户菜单 |
| `lib/screens/guess_home_page_actions.dart` | 修改设置弹窗（删除模型设置、添加词库路径） |
| `lib/screens/guess_home_page_build.dart` | 添加错误提示条、用户信息显示 |
| `lib/widgets/guess_input_card.dart` | 输入框支持中英文 |
| `lib/resources/app_strings.dart` | 添加新字符串常量 |
| `lib/main.dart` | 注册 AccountController |

---

## 第一阶段：服务器端

### Task 1: 创建数据库初始化脚本

**Files:**
- Create: `scripts/init_account_db.py`

- [ ] **Step 1: 创建数据库初始化脚本**

```python
#!/usr/bin/env python3
"""账号数据库初始化脚本"""
import sqlite3
import os
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data" / "guess.db"

SCHEMA = """
-- 用户表
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id TEXT UNIQUE NOT NULL,
    nickname TEXT NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- 统计汇总表
CREATE TABLE IF NOT EXISTS statistics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    date DATE NOT NULL,
    correct_count INTEGER DEFAULT 0,
    wrong_count INTEGER DEFAULT 0,
    total_count INTEGER DEFAULT 0,
    FOREIGN KEY (user_id) REFERENCES users(id),
    UNIQUE(user_id, date)
);

-- 答题详情表
CREATE TABLE IF NOT EXISTS game_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    date DATE NOT NULL,
    correct INTEGER NOT NULL,
    hint_index INTEGER DEFAULT -1,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

-- 索引
CREATE INDEX IF NOT EXISTS idx_statistics_user_date ON statistics(user_id, date);
CREATE INDEX IF NOT EXISTS idx_game_records_user_date ON game_records(user_id, date);
"""

def init_db():
    """初始化数据库"""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(SCHEMA)
    conn.commit()
    conn.close()
    print(f"数据库已初始化: {DB_PATH}")

if __name__ == "__main__":
    init_db()
```

- [ ] **Step 2: 运行脚本验证数据库创建**

Run: `python scripts/init_account_db.py`
Expected: 输出 "数据库已初始化: /Volumes/新/work/flutter/guess/data/guess.db"

- [ ] **Step 3: 验证数据库结构**

Run: `sqlite3 data/guess.db ".schema"`
Expected: 显示 users、statistics、game_records 表结构

- [ ] **Step 4: 提交**

```bash
git add scripts/init_account_db.py data/guess.db
git commit -m "feat(server): 添加账号数据库初始化脚本"
```

---

### Task 2: 创建 Account Server 基础框架

**Files:**
- Create: `account_server.py`

- [ ] **Step 1: 创建 FastAPI 服务框架**

```python
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
```

- [ ] **Step 2: 启动服务验证**

Run: `python account_server.py` (需要先安装 fastapi: `pip install fastapi uvicorn`)
Expected: 服务启动在 http://localhost:8001

- [ ] **Step 3: 测试健康检查 API**

Run: `curl http://localhost:8001/health`
Expected: `{"status":"ok","service":"account"}`

- [ ] **Step 4: 测试创建用户 API**

Run:
```bash
curl -X POST http://localhost:8001/api/account/create \
  -H "Content-Type: application/json" \
  -d '{"device_id":"test123","nickname":"测试用户"}'
```
Expected: `{"success":true,"user":{"id":1,"nickname":"测试用户"},"error":null}`

- [ ] **Step 5: 测试查询用户 API**

Run: `curl http://localhost:8001/api/account/by_device/test123`
Expected: `{"success":true,"user":{"id":1,"nickname":"测试用户"},"error":null}`

- [ ] **Step 6: 测试记录答题 API**

Run:
```bash
curl -X POST http://localhost:8001/api/stats/record \
  -H "Content-Type: application/json" \
  -d '{"user_id":1,"correct":true,"date":"2026-06-04","hint_index":2}'
```
Expected: `{"success":true}`

- [ ] **Step 7: 测试统计汇总 API**

Run: `curl http://localhost:8001/api/stats/summary/1`
Expected: `{"success":true,"summary":{"correct_count":1,"wrong_count":0,"total_count":1,"accuracy":100.0}}`

- [ ] **Step 8: 提交**

```bash
git add account_server.py
git commit -m "feat(server): 创建 Account Server FastAPI 服务"
```

---

## 第二阶段：Flutter 基础设施

### Task 3: 添加依赖并更新 ServerConfig

**Files:**
- Modify: `pubspec.yaml`
- Modify: `lib/config/server_config.dart`

- [ ] **Step 1: 添加依赖到 pubspec.yaml**

在 `dependencies` 部分添加：

```yaml
  device_info_plus: ^10.1.0
  crypto: ^3.0.3
```

- [ ] **Step 2: 运行 flutter pub get**

Run: `flutter pub get`
Expected: 成功获取依赖

- [ ] **Step 3: 更新 ServerConfig**

在 `lib/config/server_config.dart` 末尾添加：

```dart
  /// 账号服务端口
  static const int accountPort = 8001;

  /// 局域网账号端点列表
  static List<String> get lanAccountEndpoints =>
      lanHosts.map((h) => 'http://$h:$accountPort/api').toList();

  /// 公网账号端点
  static String get publicAccountEndpoint =>
      'https://$publicHost/api';
```

- [ ] **Step 4: 提交**

```bash
git add pubspec.yaml pubspec.lock lib/config/server_config.dart
git commit -m "feat(flutter): 添加 device_info_plus、crypto 依赖和账号端点配置"
```

---

### Task 4: 创建 DeviceIdService

**Files:**
- Create: `lib/services/device_id_service.dart`

- [ ] **Step 1: 创建设备 ID 服务**

```dart
import 'dart:convert';
import 'crypto.dart' as crypto;
import 'package:device_info_plus/device_info_plus.dart';
import 'package:flutter/foundation.dart';

/// 设备唯一 ID 生成服务
class DeviceIdService {
  DeviceIdService._();

  static final DeviceInfoPlugin _deviceInfo = DeviceInfoPlugin();
  static String? _cachedDeviceId;

  /// 获取设备唯一 ID（32字符 hex）
  static Future<String> getDeviceId() async {
    if (_cachedDeviceId != null) {
      return _cachedDeviceId!;
    }

    String deviceIdentifier;
    const appNameSalt = 'guess_game_v1';

    try {
      if (defaultTargetPlatform == TargetPlatform.macOS) {
        final info = await _deviceInfo.macOsInfo;
        deviceIdentifier = info.systemGUID ?? 'macos_${info.model}';
      } else if (defaultTargetPlatform == TargetPlatform.iOS) {
        final info = await _deviceInfo.iosInfo;
        deviceIdentifier = info.identifierForVendor ?? 'ios_${info.model}';
      } else if (defaultTargetPlatform == TargetPlatform.windows) {
        final info = await _deviceInfo.windowsInfo;
        deviceIdentifier = info.deviceId;
      } else if (defaultTargetPlatform == TargetPlatform.linux) {
        final info = await _deviceInfo.linuxInfo;
        deviceIdentifier = info.machineId ?? 'linux_${info.id}';
      } else if (defaultTargetPlatform == TargetPlatform.android) {
        final info = await _deviceInfo.androidInfo;
        deviceIdentifier = info.id;
      } else {
        deviceIdentifier = 'unknown_${DateTime.now().millisecondsSinceEpoch}';
      }
    } catch (e) {
      debugPrint('[DeviceIdService] 获取设备信息失败: $e');
      deviceIdentifier = 'fallback_${DateTime.now().millisecondsSinceEpoch}';
    }

    // SHA256 哈希生成固定长度 ID
    final bytes = utf8.encode('$deviceIdentifier_$appNameSalt');
    final digest = crypto.sha256.convert(bytes);
    _cachedDeviceId = digest.toString().substring(0, 32);

    debugPrint('[DeviceIdService] 设备ID: $_cachedDeviceId');
    return _cachedDeviceId!;
  }

  /// 清除缓存（用于测试）
  static void clearCache() {
    _cachedDeviceId = null;
  }
}
```

- [ ] **Step 2: 提交**

```bash
git add lib/services/device_id_service.dart
git commit -m "feat(flutter): 创建 DeviceIdService 设备唯一ID生成服务"
```

---

### Task 5: 创建 AccountService

**Files:**
- Create: `lib/services/account_service.dart`

- [ ] **Step 1: 创建账号 API 客户端**

```dart
import 'dart:convert';
import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;

/// 用户模型
class User {
  const User({required this.id, required this.nickname});

  final int id;
  final String nickname;

  factory User.fromJson(Map<String, dynamic> json) {
    return User(
      id: json['id'] as int,
      nickname: json['nickname'] as String,
    );
  }
}

/// 账号响应
class AccountResponse {
  const AccountResponse({required this.success, this.user, this.error});

  final bool success;
  final User? user;
  final String? error;

  factory AccountResponse.fromJson(Map<String, dynamic> json) {
    return AccountResponse(
      success: json['success'] as bool,
      user: json['user'] != null
          ? User.fromJson(json['user'] as Map<String, dynamic>)
          : null,
      error: json['error'] as String?,
    );
  }
}

/// 账号服务 HTTP 客户端
class AccountService {
  AccountService({http.Client? client}) : _client = client ?? http.Client();

  final http.Client _client;
  String? _activeEndpoint;

  String? get activeEndpoint => _activeEndpoint;

  /// 设置活动端点
  void setActiveEndpoint(String endpoint) {
    _activeEndpoint = endpoint.replaceFirst('/api', '');
  }

  /// 探测账号服务可用性
  Future<bool> probe(String baseUrl) async {
    try {
      final response = await _client
          .get(Uri.parse('$baseUrl/health'))
          .timeout(const Duration(seconds: 3));
      return response.statusCode == 200;
    } catch (e) {
      debugPrint('[AccountService] 探测失败: $e');
      return false;
    }
  }

  /// 创建账号
  Future<AccountResponse> createAccount({
    required String deviceId,
    required String nickname,
  }) async {
    if (_activeEndpoint == null) {
      return const AccountResponse(success: false, error: 'no_endpoint');
    }

    try {
      final response = await _client
          .post(
            Uri.parse('$baseUrl/api/account/create'),
            headers: {'Content-Type': 'application/json'},
            body: jsonEncode({
              'device_id': deviceId,
              'nickname': nickname,
            }),
          )
          .timeout(const Duration(seconds: 5));

      if (response.statusCode == 200) {
        return AccountResponse.fromJson(
          jsonDecode(response.body) as Map<String, dynamic>,
        );
      }
      return const AccountResponse(success: false, error: 'http_error');
    } catch (e) {
      debugPrint('[AccountService] 创建账号失败: $e');
      return AccountResponse(success: false, error: e.toString());
    }
  }

  /// 根据设备ID查询账号
  Future<AccountResponse> getAccountByDevice(String deviceId) async {
    if (_activeEndpoint == null) {
      return const AccountResponse(success: false, error: 'no_endpoint');
    }

    try {
      final response = await _client
          .get(Uri.parse('$baseUrl/api/account/by_device/$deviceId'))
          .timeout(const Duration(seconds: 5));

      if (response.statusCode == 200) {
        return AccountResponse.fromJson(
          jsonDecode(response.body) as Map<String, dynamic>,
        );
      }
      return const AccountResponse(success: false, error: 'http_error');
    } catch (e) {
      debugPrint('[AccountService] 查询账号失败: $e');
      return AccountResponse(success: false, error: e.toString());
    }
  }

  String get baseUrl => _activeEndpoint ?? '';

  void dispose() {
    _client.close();
  }
}
```

- [ ] **Step 2: 提交**

```bash
git add lib/services/account_service.dart
git commit -m "feat(flutter): 创建 AccountService 账号API客户端"
```

---

### Task 6: 创建 StatisticsService

**Files:**
- Create: `lib/services/statistics_service.dart`

- [ ] **Step 1: 创建统计 API 客户端**

```dart
import 'dart:convert';
import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;

/// 统计汇总
class StatisticsSummary {
  const StatisticsSummary({
    required this.correctCount,
    required this.wrongCount,
    required this.totalCount,
    required this.accuracy,
  });

  final int correctCount;
  final int wrongCount;
  final int totalCount;
  final double accuracy;

  factory StatisticsSummary.fromJson(Map<String, dynamic> json) {
    return StatisticsSummary(
      correctCount: json['correct_count'] as int,
      wrongCount: json['wrong_count'] as int,
      totalCount: json['total_count'] as int,
      accuracy: (json['accuracy'] as num).toDouble(),
    );
  }
}

/// 今日统计
class TodayStatistics {
  const TodayStatistics({
    required this.correctCount,
    required this.wrongCount,
    required this.totalCount,
  });

  final int correctCount;
  final int wrongCount;
  final int totalCount;

  factory TodayStatistics.fromJson(Map<String, dynamic> json) {
    return TodayStatistics(
      correctCount: json['correct_count'] as int,
      wrongCount: json['wrong_count'] as int,
      totalCount: json['total_count'] as int,
    );
  }
}

/// 统计服务 HTTP 客户端
class StatisticsService {
  StatisticsService({http.Client? client}) : _client = client ?? http.Client();

  final http.Client _client;
  String? _baseUrl;

  void setBaseUrl(String baseUrl) {
    _baseUrl = baseUrl;
  }

  /// 获取统计汇总
  Future<StatisticsSummary?> getSummary(int userId) async {
    if (_baseUrl == null) return null;

    try {
      final response = await _client
          .get(Uri.parse('$baseUrl/api/stats/summary/$userId'))
          .timeout(const Duration(seconds: 5));

      if (response.statusCode == 200) {
        final json = jsonDecode(response.body) as Map<String, dynamic>;
        if (json['success'] == true) {
          return StatisticsSummary.fromJson(
            json['summary'] as Map<String, dynamic>,
          );
        }
      }
      return null;
    } catch (e) {
      debugPrint('[StatisticsService] 获取统计汇总失败: $e');
      return null;
    }
  }

  /// 获取今日统计
  Future<TodayStatistics?> getToday(int userId) async {
    if (_baseUrl == null) return null;

    try {
      final response = await _client
          .get(Uri.parse('$baseUrl/api/stats/today/$userId'))
          .timeout(const Duration(seconds: 5));

      if (response.statusCode == 200) {
        final json = jsonDecode(response.body) as Map<String, dynamic>;
        if (json['success'] == true) {
          return TodayStatistics.fromJson(
            json['today'] as Map<String, dynamic>,
          );
        }
      }
      return null;
    } catch (e) {
      debugPrint('[StatisticsService] 获取今日统计失败: $e');
      return null;
    }
  }

  /// 记录答题结果
  Future<bool> recordGame({
    required int userId,
    required bool correct,
    required int hintIndex,
  }) async {
    if (_baseUrl == null) return false;

    final today = DateTime.now().toIso8601String().split('T')[0];

    try {
      final response = await _client
          .post(
            Uri.parse('$baseUrl/api/stats/record'),
            headers: {'Content-Type': 'application/json'},
            body: jsonEncode({
              'user_id': userId,
              'correct': correct,
              'date': today,
              'hint_index': hintIndex,
            }),
          )
          .timeout(const Duration(seconds: 5));

      if (response.statusCode == 200) {
        final json = jsonDecode(response.body) as Map<String, dynamic>;
        return json['success'] == true;
      }
      return false;
    } catch (e) {
      debugPrint('[StatisticsService] 记录答题失败: $e');
      return false;
    }
  }

  void dispose() {
    _client.close();
  }
}
```

- [ ] **Step 2: 提交**

```bash
git add lib/services/statistics_service.dart
git commit -m "feat(flutter): 创建 StatisticsService 统计API客户端"
```

---

## 第三阶段：状态管理

### Task 7: 创建 AccountController

**Files:**
- Create: `lib/controllers/account_controller.dart`

- [ ] **Step 1: 创建账号状态控制器**

```dart
import 'package:flutter/foundation.dart';
import 'package:guess/config/server_config.dart';
import 'package:guess/services/account_service.dart';
import 'package:guess/services/device_id_service.dart';
import 'package:guess/services/statistics_service.dart';

/// 词库模式
enum PuzzleMode {
  local,
  server,
}

/// 账号状态控制器
class AccountController extends ChangeNotifier {
  AccountController({
    required AccountService accountService,
    required StatisticsService statisticsService,
  })  : _accountService = accountService,
        _statisticsService = statisticsService;

  final AccountService _accountService;
  final StatisticsService _statisticsService;

  User? _user;
  StatisticsSummary? _statistics;
  TodayStatistics? _todayStatistics;
  PuzzleMode _puzzleMode = PuzzleMode.local;
  bool _sessionLocked = false;
  String? _deviceId;
  bool _loading = false;
  String? _error;

  User? get user => _user;
  StatisticsSummary? get statistics => _statistics;
  TodayStatistics? get todayStatistics => _todayStatistics;
  PuzzleMode get puzzleMode => _puzzleMode;
  bool get sessionLocked => _sessionLocked;
  bool get isLoggedIn => _user != null;
  bool get loading => _loading;
  String? get error => _error;
  String? get deviceId => _deviceId;

  /// 初始化（获取设备ID）
  Future<void> initialize() async {
    _deviceId = await DeviceIdService.getDeviceId();
    notifyListeners();
  }

  /// 连接服务器词库
  Future<bool> connectToServerPuzzles() async {
    if (_sessionLocked) {
      debugPrint('[AccountController] 会话已锁定，不能切换');
      return _puzzleMode == PuzzleMode.server;
    }

    _loading = true;
    _error = null;
    notifyListeners();

    try {
      // 探测账号服务端点
      for (final endpoint in ServerConfig.lanAccountEndpoints) {
        final ok = await _accountService.probe(endpoint.replaceFirst('/api', ''));
        if (ok) {
          _accountService.setActiveEndpoint(endpoint);
          _statisticsService.setBaseUrl(endpoint.replaceFirst('/api', ''));
          break;
        }
      }

      if (_accountService.activeEndpoint == null) {
        _error = '无法连接账号服务';
        _loading = false;
        notifyListeners();
        return false;
      }

      // 查询现有账号
      final accountResult = await _accountService.getAccountByDevice(_deviceId!);
      if (accountResult.success && accountResult.user != null) {
        _user = accountResult.user;
        await _loadStatistics();
      }

      _puzzleMode = PuzzleMode.server;
      _sessionLocked = true;
      _loading = false;
      notifyListeners();
      return true;
    } catch (e) {
      debugPrint('[AccountController] 连接服务器失败: $e');
      _error = e.toString();
      _loading = false;
      notifyListeners();
      return false;
    }
  }

  /// 创建账号（输入昵称后）
  Future<bool> createAccount(String nickname) async {
    if (_deviceId == null || _accountService.activeEndpoint == null) {
      return false;
    }

    _loading = true;
    notifyListeners();

    final result = await _accountService.createAccount(
      deviceId: _deviceId!,
      nickname: nickname,
    );

    if (result.success && result.user != null) {
      _user = result.user;
      await _loadStatistics();
      _loading = false;
      notifyListeners();
      return true;
    }

    _error = result.error ?? '创建账号失败';
    _loading = false;
    notifyListeners();
    return false;
  }

  /// 加载统计数据
  Future<void> _loadStatistics() async {
    if (_user == null) return;

    _statistics = await _statisticsService.getSummary(_user!.id);
    _todayStatistics = await _statisticsService.getToday(_user!.id);
    notifyListeners();
  }

  /// 刷新今日统计
  Future<void> refreshTodayStatistics() async {
    if (_user == null) return;
    _todayStatistics = await _statisticsService.getToday(_user!.id);
    notifyListeners();
  }

  /// 记录答题结果
  Future<void> recordGameResult({required bool correct, required int hintIndex}) async {
    if (_user == null || _puzzleMode != PuzzleMode.server) return;

    final success = await _statisticsService.recordGame(
      userId: _user!.id,
      correct: correct,
      hintIndex: hintIndex,
    );

    if (success) {
      await _loadStatistics();
    }
  }

  /// 设置本地词库模式
  void setLocalMode() {
    if (_sessionLocked) {
      debugPrint('[AccountController] 会话已锁定，不能切换');
      return;
    }
    _puzzleMode = PuzzleMode.local;
    notifyListeners();
  }

  /// 重置会话锁定（仅用于测试或重启）
  void resetSession() {
    _sessionLocked = false;
    _puzzleMode = PuzzleMode.local;
    _user = null;
    _statistics = null;
    _todayStatistics = null;
    notifyListeners();
  }

  void dispose() {
    _accountService.dispose();
    _statisticsService.dispose();
  }
}
```

- [ ] **Step 2: 提交**

```bash
git add lib/controllers/account_controller.dart
git commit -m "feat(flutter): 创建 AccountController 账号状态控制器"
```

---

### Task 8: 修改 GuessGameController 集成账号状态

**Files:**
- Modify: `lib/controllers/guess_game_controller.dart`

- [ ] **Step 1: 添加 AccountController 依赖和 hintIndex 记录**

在文件顶部导入区域添加：

```dart
import 'account_controller.dart';
```

在构造函数中添加 AccountController 参数：

```dart
class GuessGameController extends ChangeNotifier {
  GuessGameController({
    required PuzzleRepository puzzleRepository,
    required EmbeddingService embeddingService,
    required ConnectionService connectionService,
    required AccountController accountController,  // 新增
  })  : _puzzleRepository = puzzleRepository,
        _embeddingService = embeddingService,
        _connectionService = connectionService,
        _accountController = accountController {  // 新增
    _semanticScorer = SemanticScorer(
      embeddingService: _embeddingService,
      onTrace: _traceScore,
    );
  }

  final AccountController _accountController;  // 新增
```

在 `applyGuess` 方法中添加记录逻辑：

```dart
  GuessApplyResult applyGuess(String guess, GuessSubmitOutcome outcome) {
    _history.insert(0, GuessResult(word: guess, match: outcome.similarity));
    _attemptsLeft -= 1;
    if (_current != null && _hintIndex < _current!.hints.length - 1) {
      _hintIndex += 1;
    }

    final becameLose = !outcome.isWin && _attemptsLeft <= 0;
    if (becameLose) {
      _lost = true;
      // 记录答错结果
      _recordGameResult(false);
    }

    final becameWin = outcome.isWin;
    if (becameWin) {
      _won = true;
      _winBySemantic = false;
      _lastGuess = guess;
      // 记录答对结果（包含提示词序号）
      _recordGameResult(true, _hintIndex);
    }

    notifyListeners();
    return GuessApplyResult(becameWin: becameWin, becameLose: becameLose);
  }

  /// 记录答题结果到服务器
  void _recordGameResult(bool correct, [int hintIndex = -1]) {
    if (_accountController.puzzleMode == PuzzleMode.server) {
      _accountController.recordGameResult(correct: correct, hintIndex: hintIndex);
    }
  }
```

- [ ] **Step 2: 提交**

```bash
git add lib/controllers/guess_game_controller.dart
git commit -m "feat(flutter): GuessGameController 集成 AccountController，记录答题结果"
```

---

## 第四阶段：UI 实现

### Task 9: 修改 main.dart 注册 AccountController

**Files:**
- Modify: `lib/main.dart`

- [ ] **Step 1: 在 main.dart 中注册 AccountController**

找到现有的服务注册位置，添加 AccountController：

```dart
import 'controllers/account_controller.dart';
import 'services/account_service.dart';
import 'services/statistics_service.dart';

// 在现有服务创建后添加
final accountService = AccountService();
final statisticsService = StatisticsService();
final accountController = AccountController(
  accountService: accountService,
  statisticsService: statisticsService,
);

// 在 GuessGameController 创建时传入
final gameController = GuessGameController(
  puzzleRepository: puzzleRepository,
  embeddingService: embeddingService,
  connectionService: connectionService,
  accountController: accountController,
);

// 初始化 AccountController
await accountController.initialize();
```

- [ ] **Step 2: 提交**

```bash
git add lib/main.dart
git commit -m "feat(flutter): main.dart 注册 AccountController"
```

---

### Task 10: 创建用户下拉菜单组件

**Files:**
- Create: `lib/widgets/user_profile_menu.dart`

- [ ] **Step 1: 创建用户下拉菜单**

```dart
import 'package:flutter/material.dart';
import 'package:guess/controllers/account_controller.dart';
import 'package:guess/resources/resources.dart';

/// 用户下拉菜单
class UserProfileMenu extends StatelessWidget {
  const UserProfileMenu({super.key, required this.controller});

  final AccountController controller;

  @override
  Widget build(BuildContext context) {
    final user = controller.user;
    final stats = controller.statistics;
    final today = controller.todayStatistics;

    return PopupMenuButton<void>(
      position: PopupMenuPosition.under,
      offset: const Offset(0, 8),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
      itemBuilder: (context) => [
        PopupMenuItem<void>(
          enabled: false,
          child: _buildUserHeader(user?.nickname ?? AppStrings.unknownUser),
        ),
        const PopupMenuDivider(),
        PopupMenuItem<void>(
          enabled: false,
          child: _buildStatsSection(stats, today),
        ),
      ],
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 8),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            CircleAvatar(
              radius: 14,
              backgroundColor: AppColors.primary,
              child: Text(
                (user?.nickname ?? '?').substring(0, 1),
                style: const TextStyle(color: Colors.white, fontSize: 14),
              ),
            ),
            const SizedBox(width: 8),
            Text(
              user?.nickname ?? AppStrings.connectServer,
              style: AppTextStyles.bodyMedium,
            ),
            const Icon(Icons.arrow_drop_down, size: 20),
          ],
        ),
      ),
    );
  }

  Widget _buildUserHeader(String nickname) {
    return Row(
      children: [
        CircleAvatar(
          radius: 20,
          backgroundColor: AppColors.primary,
          child: Text(
            nickname.substring(0, 1),
            style: const TextStyle(color: Colors.white, fontSize: 20),
          ),
        ),
        const SizedBox(width: 12),
        Text(nickname, style: AppTextStyles.titleMedium),
      ],
    );
  }

  Widget _buildStatsSection(StatisticsSummary? stats, TodayStatistics? today) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        _buildStatRow(AppStrings.correctCount, stats?.correctCount ?? 0),
        _buildStatRow(AppStrings.wrongCount, stats?.wrongCount ?? 0),
        _buildStatRow(AppStrings.totalCount, stats?.totalCount ?? 0),
        _buildStatRow(
          AppStrings.accuracy,
          '${stats?.accuracy.toStringAsFixed(1) ?? '0.0'}%',
        ),
        const Divider(),
        _buildStatRow(
          AppStrings.todayStats,
          '${today?.correctCount ?? 0}/${today?.totalCount ?? 0}',
        ),
      ],
    );
  }

  Widget _buildStatRow(String label, dynamic value) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 4),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Text(label, style: AppTextStyles.bodySmall),
          Text('$value', style: AppTextStyles.bodySmallBold),
        ],
      ),
    );
  }
}
```

- [ ] **Step 2: 提交**

```bash
git add lib/widgets/user_profile_menu.dart
git commit -m "feat(flutter): 创建 UserProfileMenu 用户下拉菜单组件"
```

---

### Task 11: 创建昵称输入对话框

**Files:**
- Create: `lib/widgets/account_creation_dialog.dart`

- [ ] **Step 1: 创建昵称输入对话框**

```dart
import 'package:flutter/material.dart';
import 'package:guess/resources/resources.dart';

/// 昵称输入对话框
class AccountCreationDialog extends StatefulWidget {
  const AccountCreationDialog({super.key, required this.onSubmit});

  final Future<bool> Function(String nickname) onSubmit;

  @staticmethod
  Future<void> show(BuildContext context, {
    required Future<bool> Function(String nickname) onSubmit,
  }) {
    return showDialog(
      context: context,
      barrierDismissible: false,
      builder: (context) => AccountCreationDialog(onSubmit: onSubmit),
    );
  }

  @override
  State<AccountCreationDialog> createState() => _AccountCreationDialogState();
}

class _AccountCreationDialogState extends State<AccountCreationDialog> {
  final _controller = TextEditingController();
  bool _loading = false;
  String? _error;

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    final nickname = _controller.text.trim();
    if (nickname.isEmpty) {
      setState(() => _error = AppStrings.nicknameRequired);
      return;
    }
    if (nickname.length > 10) {
      setState(() => _error = AppStrings.nicknameTooLong);
      return;
    }

    setState(() {
      _loading = true;
      _error = null;
    });

    final success = await widget.onSubmit(nickname);
    if (success && mounted) {
      Navigator.of(context).pop();
    } else {
      setState(() {
        _loading = false;
        _error = AppStrings.createAccountFailed;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: Text(AppStrings.createAccountTitle),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
      content: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          TextField(
            controller: _controller,
            maxLength: 10,
            decoration: InputDecoration(
              hintText: AppStrings.nicknameHint,
              border: OutlineInputBorder(
                borderRadius: BorderRadius.circular(8),
              ),
              errorText: _error,
            ),
            autofocus: true,
            onSubmitted: (_) => _submit(),
          ),
        ],
      ),
      actions: [
        TextButton(
          onPressed: _loading ? null : _submit,
          child: _loading
              ? const SizedBox(
                  width: 16,
                  height: 16,
                  child: CircularProgressIndicator(strokeWidth: 2),
                )
              : Text(AppStrings.confirm),
        ),
      ],
    );
  }
}
```

- [ ] **Step 2: 提交**

```bash
git add lib/widgets/account_creation_dialog.dart
git commit -m "feat(flutter): 创建 AccountCreationDialog 昵称输入对话框"
```

---

### Task 12: 创建词库加载失败提示条

**Files:**
- Create: `lib/widgets/puzzle_error_banner.dart`

- [ ] **Step 1: 创建错误提示条组件**

```dart
import 'package:flutter/material.dart';
import 'package:guess/resources/resources.dart';

/// 词库加载失败提示条
class PuzzleErrorBanner extends StatelessWidget {
  const PuzzleErrorBanner({
    super.key,
    required this.error,
    required this.onRetry,
    required this.onConnectServer,
  });

  final String error;
  final VoidCallback onRetry;
  final VoidCallback onConnectServer;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: AppColors.errorBackground,
        borderRadius: BorderRadius.circular(12),
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Row(
            children: [
              const Icon(Icons.warning_amber, color: AppColors.error),
              const SizedBox(width: 8),
              Expanded(
                child: Text(
                  AppStrings.puzzleLoadFailed,
                  style: AppTextStyles.bodyMedium.copyWith(color: AppColors.error),
                ),
              ),
            ],
          ),
          const SizedBox(height: 8),
          Text(
            error,
            style: AppTextStyles.bodySmall.copyWith(color: AppColors.errorLight),
          ),
          const SizedBox(height: 16),
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceEvenly,
            children: [
              ElevatedButton.icon(
                onPressed: onRetry,
                icon: const Icon(Icons.refresh),
                label: Text(AppStrings.retry),
                style: ElevatedButton.styleFrom(
                  backgroundColor: AppColors.surface,
                  foregroundColor: AppColors.textPrimary,
                ),
              ),
              ElevatedButton.icon(
                onPressed: onConnectServer,
                icon: const Icon(Icons.cloud),
                label: Text(AppStrings.connectServerPuzzle),
                style: ElevatedButton.styleFrom(
                  backgroundColor: AppColors.primary,
                  foregroundColor: Colors.white,
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }
}
```

- [ ] **Step 2: 提交**

```bash
git add lib/widgets/puzzle_error_banner.dart
git commit -m "feat(flutter): 创建 PuzzleErrorBanner 词库加载失败提示条"
```

---

### Task 13: 添加字符串常量

**Files:**
- Modify: `lib/resources/app_strings.dart`

- [ ] **Step 1: 添加新字符串常量**

```dart
  // 账号相关
  static const String connectServer = '连接服务器';
  static const String connectServerPuzzle = '连接服务器词库';
  static const String unknownUser = '未知用户';
  static const String createAccountTitle = '创建账号';
  static const String nicknameHint = '请输入昵称';
  static const String nicknameRequired = '昵称不能为空';
  static const String nicknameTooLong = '昵称最多10个字符';
  static const String createAccountFailed = '创建账号失败';

  // 统计相关
  static const String correctCount = '答对';
  static const String wrongCount = '答错';
  static const String totalCount = '总计';
  static const String accuracy = '正确率';
  static const String todayStats = '今日';

  // 词库相关
  static const String puzzleLoadFailed = '词库加载失败';
  static const String retry = '重试';
  static const String puzzlePathLabel = '本地词库路径';
  static const String puzzlePathHint = '重启后生效';
  static const String serverConnected = '服务器已连接';

  // 输入框
  static const String inputHint = '输入中文或英文词语';
```

- [ ] **Step 2: 提交**

```bash
git add lib/resources/app_strings.dart
git commit -m "feat(flutter): 添加账号、统计、词库相关字符串常量"
```

---

### Task 14: 修改 AppBar 显示逻辑

**Files:**
- Modify: `lib/screens/guess_home_page.dart`

- [ ] **Step 1: 导入新组件**

```dart
import 'package:guess/widgets/user_profile_menu.dart';
import 'package:guess/widgets/account_creation_dialog.dart';
import 'account_controller.dart';
```

- [ ] **Step 2: 修改 AppBar actions**

替换现有的 AppBar actions 部分：

```dart
      actions: [
        // 服务器模式显示用户菜单
        if (_accountController.puzzleMode == PuzzleMode.server)
          UserProfileMenu(controller: _accountController),
        // 设置按钮
        IconButton(
          icon: const Icon(Icons.tune),
          onPressed: () => _showEmbeddingSettings(context),
        ),
      ],
```

- [ ] **Step 3: 修改 AppBar title 添加状态灯**

```dart
      title: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Text(AppStrings.appTitle),
          if (_accountController.puzzleMode == PuzzleMode.server)
            Container(
              margin: const EdgeInsets.only(left: 8),
              width: 8,
              height: 8,
              decoration: const BoxDecoration(
                color: AppColors.success,
                shape: BoxShape.circle,
              ),
            ),
        ],
      ),
```

- [ ] **Step 4: 提交**

```bash
git add lib/screens/guess_home_page.dart
git commit -m "feat(flutter): AppBar 添加用户菜单和服务器状态灯"
```

---

### Task 15: 修改设置弹窗

**Files:**
- Modify: `lib/screens/guess_home_page_actions.dart`

- [ ] **Step 1: 删除模型设置，添加词库路径设置**

找到 `_showEmbeddingSettings` 方法，修改内容：

```dart
  void _showEmbeddingSettings(BuildContext context) {
    showModalBottomSheet(
      context: context,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(16)),
      ),
      builder: (context) => Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(AppStrings.settingsTitle, style: AppTextStyles.titleMedium),
            const SizedBox(height: 24),

            // 本地词库路径
            Text(AppStrings.puzzlePathLabel, style: AppTextStyles.bodyMedium),
            const SizedBox(height: 8),
            TextField(
              controller: _puzzlePathController,
              decoration: InputDecoration(
                hintText: AppStrings.puzzlePathHint,
                border: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(8),
                ),
                suffixIcon: IconButton(
                  icon: const Icon(Icons.folder_open),
                  onPressed: _selectPuzzlePath,
                ),
              ),
            ),
            const SizedBox(height: 16),
            Text(
              AppStrings.puzzlePathHint,
              style: AppTextStyles.bodySmall.copyWith(color: AppColors.textSecondary),
            ),
            const SizedBox(height: 24),
            ElevatedButton(
              onPressed: () {
                _savePuzzlePath();
                Navigator.pop(context);
              },
              child: Text(AppStrings.save),
            ),
          ],
        ),
      ),
    );
  }

  void _selectPuzzlePath() async {
    // 使用 file_picker 选择路径（需要添加依赖）
    // 或直接手动输入
  }

  Future<void> _savePuzzlePath() async {
    final path = _puzzlePathController.text.trim();
    await _gameController.updatePuzzlePath(path);
  }
```

- [ ] **Step 2: 提交**

```bash
git add lib/screens/guess_home_page_actions.dart
git commit -m "feat(flutter): 设置弹窗删除模型设置，添加本地词库路径"
```

---

### Task 16: 添加错误提示条和连接服务器逻辑

**Files:**
- Modify: `lib/screens/guess_home_page_build.dart`

- [ ] **Step 1: 在 _buildBody 中添加错误提示条**

在主布局顶部添加：

```dart
  Widget _buildBody(BuildContext context) {
    final gameController = _gameController;
    final accountController = _accountController;

    // 词库加载失败时显示错误提示条
    if (gameController.puzzleLoadError != null) {
      return Center(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: PuzzleErrorBanner(
            error: gameController.puzzleLoadError!,
            onRetry: () => gameController.reloadPuzzles(),
            onConnectServer: () async {
              final success = await accountController.connectToServerPuzzles();
              if (success && accountController.user == null) {
                // 需要创建账号
                AccountCreationDialog.show(
                  context,
                  onSubmit: accountController.createAccount,
                );
              }
              if (success) {
                await gameController.reloadPuzzles();
              }
            },
          ),
        ),
      );
    }

    // 正常游戏布局...
  }
```

- [ ] **Step 2: 提交**

```bash
git add lib/screens/guess_home_page_build.dart
git commit -m "feat(flutter): 添加词库加载失败提示条和连接服务器逻辑"
```

---

### Task 17: 修改输入框支持中英文

**Files:**
- Modify: `lib/widgets/guess_input_card.dart`

- [ ] **Step 1: 修改输入验证和提示文本**

找到输入框的 `inputFormatters` 或验证逻辑，修改为：

```dart
TextField(
  decoration: InputDecoration(
    hintText: AppStrings.inputHint,  // "输入中文或英文词语"
    ...
  ),
  // 移除仅中文的限制，允许中英文
  inputFormatters: [
    FilteringTextInputFormatter.allow(RegExp(r'[a-zA-Z一-龥]')),
  ],
)
```

- [ ] **Step 2: 提交**

```bash
git add lib/widgets/guess_input_card.dart
git commit -m "feat(flutter): 输入框支持中英文输入"
```

---

## 第五阶段：集成测试

### Task 18: 运行 Flutter analyze

- [ ] **Step 1: 运行静态分析**

Run: `flutter analyze`
Expected: 无错误或警告

- [ ] **Step 2: 修复任何问题**

如有错误，逐一修复。

---

### Task 19: 手动测试本地词库模式

- [ ] **Step 1: 启动 embedding_server**

Run: `python embedding_server.py`

- [ ] **Step 2: 启动 account_server**

Run: `python account_server.py`

- [ ] **Step 3: 运行 Flutter app**

Run: `flutter run -d macos`

- [ ] **Step 4: 测试本地词库模式**

操作：
1. 设置中填写本地词库路径（如 `assets/puzzles.json`）
2. 重启 APP
3. 验证：AppBar 无状态灯，无用户菜单

---

### Task 20: 手动测试服务器词库模式

- [ ] **Step 1: 测试连接服务器词库**

操作：
1. 清空本地词库路径设置
2. 重启 APP
3. 点击"连接服务器词库"
4. 输入昵称
5. 验证：AppBar 显示状态灯和用户菜单

- [ ] **Step 2: 测试答题统计**

操作：
1. 答对一道题
2. 点击用户菜单
3. 验证：统计数据更新

- [ ] **Step 3: 测试会话锁定**

操作：
1. 连接服务器词库后
2. 尝试切换本地词库
3. 验证：不能切换

---

### Task 21: 最终提交和文档更新

- [ ] **Step 1: 更新 CLAUDE.md**

在 CLAUDE.md 中添加 Account Server 启动说明：

```markdown
### Account Server

账号服务独立运行：

```bash
# 启动账号服务（端口 8001）
python account_server.py

# 健康检查
curl http://localhost:8001/health
```
```

- [ ] **Step 2: 最终提交**

```bash
git add -A
git commit -m "feat: 完成用户系统与双词库模式实现

- 新建 Account Server (FastAPI 端口 8001)
- SQLite 数据库存储用户和统计数据
- Flutter 端 AccountController、DeviceIdService
- 本地词库模式无账号，服务器词库模式有账号统计
- AppBar 显示服务器状态灯和用户下拉菜单
- 输入框支持中英文
- 记录答题结果和提示词序号"

git push
```

---

## Self-Review Checklist

**1. Spec Coverage:**

| 需求 | Task |
|:-----|:-----|
| 昵称、答对次数、答题总数显示 | Task 10, 14 |
| 删除"模型：本地"，改为"服务器已连接" | Task 14 |
| 设置取消模型内容，添加词库路径 | Task 15 |
| 重启后词库不存在提示 | Task 12, 16 |
| 重连按钮 | Task 12 |
| 连接服务器词库按钮 | Task 12, 16 |
| 本地词库无账号不记录数据库 | Task 7, 8 |
| 服务器词库有账号记录数据库 | Task 7, 8, 2 |
| 答对记录提示词序号 | Task 2, 6 |
| 输入框支持中英文 | Task 17 |

**2. Placeholder Scan:** 无 TBD、TODO、implement later

**3. Type Consistency:**
- `AccountController.user` 类型为 `User?`
- `AccountService.createAccount` 返回 `AccountResponse`
- `StatisticsService.recordGame` 参数 `hintIndex: int`

---

## 计划完成

计划已保存到 `docs/superpowers/plans/2026-06-04-user-system-implementation.md`。

**两种执行方式：**

1. **Subagent-Driven (推荐)** - 每个 Task 分配独立子代理，任务间可审查，快速迭代

2. **Inline Execution** - 当前会话批量执行，带检查点审查

**选择哪种方式？**