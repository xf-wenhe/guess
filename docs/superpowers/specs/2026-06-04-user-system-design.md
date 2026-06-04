# 词语猜谜 - 用户系统与词库模式设计

## 概述

为词语猜谜 Flutter 游戏添加用户系统和双词库模式支持。用户可选择本地词库模式（无账号、无统计）或服务器词库模式（有账号、有统计）。

## 核心规则

### 两种词库模式

| 模式 | 账号 | 统计 | 数据库记录 |
|------|------|------|-----------|
| 本地词库 | 无 | 无 | 无 |
| 服务器词库 | 有 | 有 | 有 |

### 模式切换逻辑

```
┌─────────────────────────────────────────────────────────────┐
│                       APP 启动                               │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
                    ┌─────────────────┐
                    │ 检查本地词库路径 │
                    └─────────────────┘
                              │
              ┌───────────────┼───────────────┐
              │                               │
              ▼                               ▼
    ┌─────────────────┐             ┌─────────────────┐
    │ 路径有效且存在   │             │ 路径无效或不存在 │
    └─────────────────┘             └─────────────────┘
              │                               │
              ▼                               ▼
    ┌─────────────────┐             ┌─────────────────┐
    │ 本地词库模式     │             │ 显示错误提示     │
    │ 无账号、无统计   │             │ 可重试或连服务器 │
    └─────────────────┘             └─────────────────┘
                                              │
                              ┌───────────────┼───────────────┐
                              │                               │
                              ▼                               ▼
                    ┌─────────────────┐             ┌─────────────────┐
                    │ 重试本地路径     │             │ 连接服务器词库   │
                    └─────────────────┘             └─────────────────┘
                                                              │
                                                              ▼
                                                    ┌─────────────────┐
                                                    │ 检查设备 ID 是否 │
                                                    │ 已注册账号       │
                                                    └─────────────────┘
                                                              │
                                              ┌───────────────┼───────────────┐
                                              │                               │
                                              ▼                               ▼
                                    ┌─────────────────┐             ┌─────────────────┐
                                    │ 已有账号        │             │ 弹出昵称输入框   │
                                    │ 加载统计数据    │             │ 创建新账号       │
                                    └─────────────────┘             └─────────────────┘
                                              │                               │
                                              └───────────────┬───────────────┘
                                                              ▼
                                                    ┌─────────────────┐
                                                    │ 服务器词库模式   │
                                                    │ 会话锁定         │
                                                    └─────────────────┘
```

### 会话锁定规则

- 连接服务器词库成功后，当前 APP 会话锁定为服务器模式
- 即使断网也不能切换回本地词库模式
- 只有重启 APP 才能解除锁定

---

## 架构设计

### 整体架构

```
┌─────────────────────────────────────────────────────────────────┐
│                        Flutter APP                               │
├─────────────────────────────────────────────────────────────────┤
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐  │
│  │ AccountController │  │ StatisticsService │  │ DeviceIdService   │  │
│  └──────────────┘  └──────────────┘  └──────────────────────┘  │
│          │                  │                    │              │
│          └──────────────────┼────────────────────┘              │
│                             │                                   │
│                    ┌────────▼────────┐                          │
│                    │  AccountService  │                          │
│                    │  (HTTP Client)   │                          │
│                    └────────┬────────┘                          │
└─────────────────────────────┼───────────────────────────────────┘
                              │
                              │ HTTP API
                              │
┌─────────────────────────────▼───────────────────────────────────┐
│                    Account Server (FastAPI)                      │
│                    端口: 8001                                    │
├─────────────────────────────────────────────────────────────────┤
│  ┌──────────────────┐  ┌──────────────────┐                    │
│  │ /api/account/*   │  │ /api/stats/*     │                    │
│  └──────────────────┘  └──────────────────┘                    │
│                             │                                   │
│                    ┌────────▼────────┐                          │
│                    │  SQLite Database │                          │
│                    │  data/guess.db   │                          │
│                    └─────────────────┘                          │
└─────────────────────────────────────────────────────────────────┘
```

### 新增文件

#### Flutter 端

| 文件 | 说明 |
|------|------|
| `lib/controllers/account_controller.dart` | 账号状态控制器 |
| `lib/services/account_service.dart` | 账号 API 客户端 |
| `lib/services/statistics_service.dart` | 统计 API 客户端 |
| `lib/services/device_id_service.dart` | 设备 ID 生成服务 |
| `lib/widgets/account_creation_dialog.dart` | 昵称输入对话框 |
| `lib/widgets/user_profile_menu.dart` | 用户下拉菜单组件 |

#### 服务器端

| 文件 | 说明 |
|------|------|
| `account_server.py` | FastAPI 用户服务 |
| `scripts/init_account_db.py` | 数据库初始化脚本 |

---

## UI 设计

### 1. AppBar 设计

**左侧**：
- 本地模式：显示 APP 标题 "词语猜谜"
- 服务器模式：显示 APP 标题 + 服务器连接状态指示灯（绿色圆点）

**右侧**：
- 本地模式：设置按钮（tune 图标）
- 服务器模式：用户头像/昵称按钮（点击弹出下拉菜单）+ 设置按钮

### 2. 用户下拉菜单

```
┌─────────────────────────────────┐
│  [头像] 昵称                     │
│  ─────────────────────────────  │
│  答对：123 次                    │
│  答错：45 次                     │
│  总计：168 次                    │
│  正确率：73.2%                   │
│  ─────────────────────────────  │
│  今日：答对 5 / 总计 8           │
└─────────────────────────────────┘
```

### 3. 设置页面修改

**删除**：
- 本地模型目录输入框
- 在线模型地址输入框

**新增**：
- 本地词库路径输入框（文本输入 + 选择按钮）
- 保存后提示"重启生效"

### 4. 错误提示设计

当本地词库路径无效时，显示：

```
┌─────────────────────────────────────────┐
│  ⚠️ 词库加载失败                         │
│  本地词库路径不存在或无效                 │
│  请检查设置中的词库路径                   │
│                                         │
│  [重试]        [连接服务器词库]           │
└─────────────────────────────────────────┘
```

---

## 数据库设计

### SQLite Schema

```sql
-- 用户表
CREATE TABLE users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id TEXT UNIQUE NOT NULL,
    nickname TEXT NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- 统计表
CREATE TABLE statistics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    date DATE NOT NULL,
    correct_count INTEGER DEFAULT 0,
    wrong_count INTEGER DEFAULT 0,
    total_count INTEGER DEFAULT 0,
    FOREIGN KEY (user_id) REFERENCES users(id),
    UNIQUE(user_id, date)
);

-- 创建索引
CREATE INDEX idx_statistics_user_date ON statistics(user_id, date);
```

---

## API 设计

### Account Server (端口 8001)

#### 用户相关

```
POST /api/account/create
请求: { "device_id": "xxx", "nickname": "昵称" }
响应: { "success": true, "user": { "id": 1, "nickname": "昵称" } }

GET /api/account/by_device/{device_id}
响应: { "success": true, "user": { "id": 1, "nickname": "昵称" } } 或 { "success": false, "error": "not_found" }

PUT /api/account/nickname
请求: { "device_id": "xxx", "nickname": "新昵称" }
响应: { "success": true }
```

#### 统计相关

```
GET /api/stats/summary/{user_id}
响应: {
    "success": true,
    "summary": {
        "correct_count": 123,
        "wrong_count": 45,
        "total_count": 168,
        "accuracy": 73.2
    }
}

GET /api/stats/today/{user_id}
响应: {
    "success": true,
    "today": {
        "correct_count": 5,
        "wrong_count": 3,
        "total_count": 8
    }
}

POST /api/stats/record
请求: { "user_id": 1, "correct": true, "date": "2026-06-04" }
响应: { "success": true }
```

---

## 设备 ID 生成方案

使用 `device_info_plus` 包获取设备信息，结合以下字段生成唯一 ID：

```dart
// macOS
- systemGUID (硬件 UUID)

// iOS
- identifierForVendor

// Windows
- deviceId

// Linux
- machineId

// Android
- androidId
```

生成逻辑：
```dart
String deviceId = sha256(deviceInfo + appNameSalt).substring(0, 32);
```

---

## 配置修改

### ServerConfig 更新

```dart
class ServerConfig {
  // 现有配置
  static const List<String> lanHosts = ['192.168.11.29'];
  static const String publicHost = 'your-domain.com';
  static const int port = 8000;

  // 新增账号服务端口
  static const int accountPort = 8001;

  // 账号服务端点
  static List<String> get lanAccountEndpoints =>
      lanHosts.map((h) => 'http://$h:$accountPort/api').toList();
  static String get publicAccountEndpoint =>
      'https://$publicHost/api';
}
```

### pubspec.yaml 新增依赖

```yaml
dependencies:
  device_info_plus: ^10.1.0
  crypto: ^3.0.3
  http: ^1.2.0  # 如果尚未添加
```

---

## 状态管理

### AccountController

```dart
class AccountController extends GetxController {
  final Rx<User?> user = Rx(null);
  final RxBool isConnectedToServer = false.obs;
  final Rx<StatisticsSummary?> statistics = Rx(null);

  bool get isLoggedIn => user.value != null;

  Future<void> connectToServerPuzzles() async { ... }
  Future<void> createAccount(String nickname) async { ... }
  Future<void> loadStatistics() async { ... }
  Future<void> recordGameResult(bool correct) async { ... }
}
```

---

## 实现步骤概要

### 第一阶段：服务器端

1. 创建 `account_server.py` FastAPI 服务
2. 创建数据库初始化脚本
3. 实现用户和统计 API

### 第二阶段：Flutter 基础设施

1. 添加 `device_info_plus` 依赖
2. 创建 `DeviceIdService`
3. 创建 `AccountService` HTTP 客户端
4. 创建 `StatisticsService`

### 第三阶段：状态管理

1. 创建 `AccountController`
2. 修改 `GuessGameController` 集成账号状态

### 第四阶段：UI 实现

1. 修改 AppBar 显示逻辑
2. 创建用户下拉菜单组件
3. 创建昵称输入对话框
4. 修改设置页面
5. 实现错误提示和重连逻辑

### 第五阶段：集成测试

1. 测试本地词库模式
2. 测试服务器词库模式
3. 测试模式切换逻辑
4. 测试统计数据记录

---

## 验证方案

### 手动测试

1. **本地模式测试**：
   - 设置本地词库路径 → 重启 → 验证本地模式工作
   - 设置无效路径 → 重启 → 验证错误提示显示

2. **服务器模式测试**：
   - 点击"连接服务器词库" → 验证昵称对话框弹出
   - 输入昵称 → 验证账号创建成功
   - 答题 → 验证统计数据更新

3. **模式锁定测试**：
   - 连接服务器词库后断网 → 验证不能切换回本地

### API 测试

```bash
# 健康检查
curl http://localhost:8001/health

# 创建用户
curl -X POST http://localhost:8001/api/account/create \
  -H "Content-Type: application/json" \
  -d '{"device_id":"test123","nickname":"测试用户"}'

# 查询用户
curl http://localhost:8001/api/account/by_device/test123

# 记录统计
curl -X POST http://localhost:8001/api/stats/record \
  -H "Content-Type: application/json" \
  -d '{"user_id":1,"correct":true,"date":"2026-06-04"}'

# 查询统计
curl http://localhost:8001/api/stats/summary/1
```
