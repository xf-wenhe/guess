/// 服务端配置
///
/// 模型和词库服务地址固定，按优先级探测
class ServerConfig {
  ServerConfig._();

  /// 局域网IP列表（按优先级排序）
  /// 注意：这些是运行 embedding_server 的服务器地址，不是客户端地址
  static const List<String> lanHosts = [
    '192.168.11.29', // 主局域网服务器
  ];

  /// 公网服务地址
  static const String publicHost = 'your-domain.com';

  /// 服务端口
  static const int port = 8000;

  /// 连接超时（秒）
  static const int connectTimeoutSeconds = 3;

  /// 探测超时（秒）
  static const int probeTimeoutSeconds = 5;

  /// 局域网模型端点列表
  static List<String> get lanEmbedEndpoints =>
      lanHosts.map((h) => 'http://$h:$port/embed').toList();

  /// 公网模型端点
  static String get publicEmbedEndpoint => 'https://$publicHost/embed';

  /// 局域网词库端点列表
  static List<String> get lanPuzzleEndpoints =>
      lanHosts.map((h) => 'http://$h:$port/puzzles').toList();

  /// 公网词库端点
  static String get publicPuzzleEndpoint => 'https://$publicHost/puzzles';

  /// 默认词库路径（本地开发用）
  static const String defaultPuzzlesPath = 'assets/puzzles.json';
}
