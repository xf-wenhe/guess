class AppStrings {
  const AppStrings._();

  static const appMaterialTitle = 'AI猜词';
  static const homeTitle = 'AI 猜词';
  static const tooltipCheckConnection = '检测连接';
  static const tooltipModelSettings = '模型设置';

  static const inputHint = '请输入你的猜测';
  static const inputSubmitting = '计算中…';
  static const inputSend = '发送';

  static const winStageTitle = 'Victory Moment';
  static const winStageSubtitle = '语义与答案高度一致';
  static const loseStageTitle = 'Round Over';
  static const loseStageSubtitle = '再调整一次思路，下一把更接近';
  static const roundSummary = '本轮总结';
  static const hitAnswer = '命中答案';
  static const missAnswer = '本轮未命中';
  static const playAgain = '再来一局';
  static const retry = '再试一次';

  static const historyTitle = '猜测记录';
  static const hintTitle = '提示线索';
  static const waitingInput = '等待输入';

  static const attemptsLeft = '剩余机会';
  static const attemptsUnit = '次';
  static const totalAttempts = '本局共有 6 次机会';
  static const answerInfo = '答案信息';
  static const unlockMoreHints = '继续猜测可解锁更多提示';

  static const connectionInProgress = '正在连接本地模型，请稍候…';
  static const initialDownloadHint = '首次启动需要下载本地模型，可能需要几分钟，请保持网络连接。';
  static const loadPuzzleFailed = '词库获取失败，请检查网络后重试';
  static const reload = '重新获取';

  static const resultBarrierLabel = 'result';
  static const cancel = '取消';
  static const save = '保存';
  static const localModelDir = '本地模型目录';
  static const localModelDirHint = '/path/to/model (包含 config.json)';
  static const localModelDirCaption = '填写本地模型目录将跳过下载。留空则自动下载。';
  static const onlineModelUrl = '在线模型地址';
  static const onlineModelUrlHint = 'https://your-embedding-endpoint';
  static const onlineModelUrlCaption = '留空将仅使用本地模型。';

  static const invalidGuess = '请输入 2-5 个中文字';
  static const duplicatedGuess = '该词已猜过，换一个吧';
  static const semanticFallback = '语义服务不可用，已使用简化匹配';
  static const almostThere = '哇，马上就可以猜到了！';
  static const submitFailed = '提交失败，请稍后重试';
  static const localModelNotReady = '本地模型尚未就绪，请稍候…';
  static const localModelStartFailed = '本地模型启动失败';
  static const localModelPortNotReady = '未连接到本地模型（端口 8000 未就绪）';
  static const localModelTimeout = '连接超时，模型可能仍在下载或未就绪，请稍后重试。';
  static const localModelCurrentPrefix = '当前模型：';

  static const localSourceLabel = '本地';
  static const onlineSourceLabel = '在线';
  static const disconnectedSourceLabel = '未连接';
  static const probeText = '测试';

  static const semanticAngles = <String>[
    '从含义角度看：',
    '从用途角度看：',
    '从场景角度看：',
    '从特征角度看：',
    '从关联角度看：',
  ];

  static const functionWords = <String>{
    '你',
    '我',
    '他',
    '她',
    '它',
    '们',
    '是',
    '的',
    '了',
    '在',
    '有',
    '为',
  };

  static const genericHints = <String>[
    '从意象入手',
    '联想一种场景',
    '抓住氛围感',
    '想到一种情绪',
    '想想自然元素',
    '联系一种动作',
    '试试抽象概念',
    '换个角度联想',
    '找同类词做比较',
    '想想反义或相邻概念',
    '把词拆成部件联想',
    '聚焦核心意象',
    '锁定主要用途',
    '再缩小到具体物/动作',
  ];

  static const defaultPos = '名词';
  static const defaultCategory = '其他';

  static String answerIs(String answer) => '答案是：$answer';
  static String correctAnswer(String answer) => '正确答案：$answer';
  static String semanticMatch(String guess) => '“$guess” 与答案语义一致。';

  static String guessedCount(int count) => '已猜 $count 次';
  static String bestMatch(int score) => '最高 $score%';
  static String rangeLabel(String category) => '范围：$category';
  static String lengthLabel(int length) => '长度：$length 字';
  static String posLabel(String pos) => '词性：$pos';
  static String modelLabel(String label) => '模型：$label';
  static String relationPercent(int value) => '$value% 关联度';
  static String relationDetail(String label) => '$label · 非正确率';
  static String guessFeedback(String guess, int similarity) =>
      '“$guess” 与答案关联度 $similarity%';
  static String localModelPrepareFailed(Object error) => '本地模型脚本准备失败：$error';
  static String localModelPrepareFailedToast = '本地模型脚本准备失败';
  static String modelConfigMissing = '未在该目录找到 config.json，请选择包含模型文件的目录';
  static String currentModelLabel(String label) => '$localModelCurrentPrefix$label';

  static const runnerSandboxed = '当前应用启用了沙盒，无法启动本地模型。请关闭 App Sandbox 后重试。';
  static const runnerScriptMissing = '本地模型脚本不存在';
  static const runnerPythonMissing = '未找到可用的 Python 解释器';
  static const runnerManagedVenvFailed = '本地模型虚拟环境创建失败';
  static const runnerSandboxedProcess = '应用处于沙盒环境，无法启动本地模型。请关闭 App Sandbox 后重试。';
  static const runnerPortBusy = '本地模型端口 8000 被占用，请关闭占用进程后重试。';
  static const runnerNoResponse = '本地模型未能响应，请检查 Python 与依赖是否安装完成。';
  static const runnerCannotRunPython = '无法运行 Python，请检查环境配置';
  static const runnerDependencyMissing = '依赖未安装，且未找到 requirements.txt';
  static const runnerInstallingDependencies = '正在安装依赖，请稍候…';
  static const runnerCannotRunPip = '无法运行 pip，请检查 Python 环境';
  static const runnerDependencyInstallFailed = '依赖安装失败';
  static const runnerNoSystemPython = '未找到系统 Python 用于修复环境';
  static const runnerRepairingEnvironment = '正在修复本地模型环境，请稍候…';
  static const runnerRepairFailed = '环境修复失败';

  static String runnerStartFailedWithCode(int code) => '本地模型启动失败（退出码 $code）';
  static String runnerStartFailedWithError(Object error) => '本地模型启动失败：$error';

  static String historyAssociationLabel(int value) {
    if (value >= 85) return '极高关联';
    if (value >= 70) return '相关但未命中';
    if (value >= 40) return '中等关联';
    return '弱关联';
  }

  static String resultAssociationLabel(int value) {
    if (value >= 85) return '极高关联（仍可能错误）';
    if (value >= 70) return '相关较高（未命中）';
    if (value >= 40) return '有一定关联';
    return '关联较弱';
  }

  // 账号相关
  static const connectServer = '连接服务器';
  static const connectServerPuzzle = '连接服务器词库';
  static const unknownUser = '未知用户';
  static const createAccountTitle = '创建账号';
  static const nicknameHint = '请输入昵称';
  static const nicknameRequired = '昵称不能为空';
  static const nicknameTooLong = '昵称最多10个字符';
  static const createAccountFailed = '创建账号失败';
  static const confirm = '确认';

  // 统计相关
  static const correctCount = '答对';
  static const wrongCount = '答错';
  static const totalCount = '总计';
  static const accuracy = '正确率';
  static const todayStats = '今日';

  // 词库相关
  static const puzzleLoadFailed = '词库加载失败';
  static const puzzlePathLabel = '本地词库路径';
  static const puzzlePathHint = '重启后生效';
  static const serverConnected = '服务器已连接';
  static const settingsTitle = '设置';
}