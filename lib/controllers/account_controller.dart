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

  @override
  void dispose() {
    _accountService.dispose();
    _statisticsService.dispose();
    super.dispose();
  }
}