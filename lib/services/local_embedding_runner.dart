import 'dart:convert';
import 'dart:io';

import 'package:guess/resources/resources.dart';

class LocalEmbeddingRunner {
  LocalEmbeddingRunner({
    required this.scriptPath,
    required this.host,
    this.workingDirectory,
    this.envOverrides,
  });

  static const String _managedVenvName = '.embedding_venv';

  final String scriptPath;
  final String host;
  final String? workingDirectory;
  final Map<String, String>? envOverrides;

  Process? _process;
  String? lastError;
  String? _lastStderrLine;
  String? _lastStderr;

  bool get isRunning => _process != null;

  Future<void> start() async {
    if (isRunning) return;
    if (_isSandboxed()) {
      lastError = AppStrings.runnerSandboxed;
      return;
    }
    final script = File(scriptPath);
    if (!script.existsSync()) {
      lastError = AppStrings.runnerScriptMissing;
      return;
    }

    var pythonExe = _resolvePythonExecutable();
    if (pythonExe == null) {
      lastError = AppStrings.runnerPythonMissing;
      return;
    }

    final scriptDir = workingDirectory ?? script.parent.path;
    final depsOk = await _ensureDependencies(pythonExe, scriptDir);
    if (!depsOk) {
      final recovered = await _recoverManagedVenv();
      if (!recovered) {
        return;
      }
      final managedPython = _findVenvPython(Directory(scriptDir));
      if (managedPython == null) {
        lastError = AppStrings.runnerManagedVenvFailed;
        return;
      }
      pythonExe = managedPython;
    }

    final env = Map<String, String>.from(Platform.environment);
    env.remove('PYTHONHOME');
    env.remove('PYTHONPATH');
    if (envOverrides != null && envOverrides!.isNotEmpty) {
      env.addAll(envOverrides!);
    }
    final venvDir = _resolveVenvDir(pythonExe);
    if (venvDir != null) {
      env['VIRTUAL_ENV'] = venvDir;
      final binPath = Platform.isWindows
          ? '$venvDir${Platform.pathSeparator}Scripts'
          : '$venvDir${Platform.pathSeparator}bin';
      final currentPath = env['PATH'] ?? '';
      env['PATH'] = '$binPath${Platform.isWindows ? ';' : ':'}$currentPath';
    }

    final pythonArgs = [scriptPath];
    try {
      _process = await Process.start(
        pythonExe,
        pythonArgs,
        mode: ProcessStartMode.normal,
        workingDirectory: scriptDir,
        environment: env,
      );
      _process?.stdout.transform(const SystemEncoding().decoder).listen((data) {
        final trimmed = data.trim();
        if (trimmed.isNotEmpty) {
          // Keep lastError until a successful health check clears it.
        }
      });
      _process?.stderr.transform(const SystemEncoding().decoder).listen((data) {
        final trimmed = data.trim();
        if (trimmed.isNotEmpty) {
          _lastStderr = trimmed;
          final firstLine = trimmed.split('\n').first;
          _lastStderrLine = firstLine;
          if (firstLine.contains('App Sandbox')) {
            lastError = AppStrings.runnerSandboxedProcess;
          } else if (firstLine.contains('address already in use') ||
              firstLine.contains('Errno 48')) {
            lastError = AppStrings.runnerPortBusy;
          } else {
            lastError = _shortenForToast(trimmed);
          }
        }
      });
      _process?.exitCode.then((code) {
        if (_process == null) {
          return;
        }
        if (code != 0) {
          if (lastError == null || lastError!.isEmpty) {
            if (_lastStderrLine != null && _lastStderrLine!.isNotEmpty) {
              lastError = _lastStderrLine;
            } else {
              lastError = AppStrings.runnerStartFailedWithCode(code);
            }
          }
          _process = null;
        }
      });
    } catch (e) {
      lastError = _shortenForToast(AppStrings.runnerStartFailedWithError(e));
      _process = null;
    }
  }

  Future<void> stop() async {
    final process = _process;
    if (process == null) return;

    _process = null;
    try {
      process.kill(ProcessSignal.sigterm);
    } catch (_) {
      // Ignore stop errors.
    }
  }

  Future<void> restart() async {
    await stop();
    await Future<void>.delayed(const Duration(milliseconds: 200));
    await start();
  }

  Future<bool> restartAndWait({Duration timeout = const Duration(seconds: 25)}) async {
    await stop();
    await Future<void>.delayed(const Duration(milliseconds: 200));
    if (await _checkHealth()) {
      lastError = null;
      return true;
    }
    await start();
    if (_isSandboxed()) {
      return false;
    }
    final ready = await waitForReady(timeout: timeout);
    if (ready) {
      return true;
    }

    if (lastError == null || lastError!.isEmpty) {
      if (_lastStderr != null && _lastStderr!.isNotEmpty) {
        lastError = _shortenForToast(_lastStderr!);
      } else {
        lastError = AppStrings.runnerNoResponse;
      }
    }

    final err = lastError ?? '';
    if (err.contains('address already in use') || err.contains('Errno 48')) {
      if (await _checkHealth()) {
        lastError = null;
        return true;
      }
      return false;
    }
    if (err.contains('init_import_site') || err.contains('site module')) {
      final recovered = await _recoverManagedVenv();
      if (recovered) {
        await stop();
        await Future<void>.delayed(const Duration(milliseconds: 200));
        await start();
        return waitForReady(timeout: timeout);
      }
    }

    return false;
  }

  Future<bool> waitForReady({Duration timeout = const Duration(seconds: 25)}) async {
    final deadline = DateTime.now().add(timeout);
    while (DateTime.now().isBefore(deadline)) {
      final ok = await _checkHealth();
      if (ok) {
        return true;
      }
      if (!isRunning) {
        break;
      }
      await Future<void>.delayed(const Duration(milliseconds: 600));
    }
    return false;
  }

  Future<bool> _checkHealth() async {
    final readyOk = await _checkReady();
    if (readyOk) {
      return true;
    }

    try {
      final uri = Uri.parse('$host/health');
      final client = HttpClient();
      client.connectionTimeout = const Duration(seconds: 2);
      final request = await client.getUrl(uri);
      final response = await request.close();
      final ok = response.statusCode == 200;
      await response.drain();
      client.close();
      return ok;
    } catch (_) {
      return false;
    }
  }

  Future<bool> _checkReady() async {
    try {
      final uri = Uri.parse('$host/ready');
      final client = HttpClient();
      client.connectionTimeout = const Duration(seconds: 2);
      final request = await client.getUrl(uri);
      final response = await request.close();
      final statusCode = response.statusCode;
      final body = await utf8.decoder.bind(response).join();
      client.close();

      if (statusCode == 404) {
        return false;
      }
      if (statusCode != 200) {
        return false;
      }

      final payload = jsonDecode(body);
      if (payload is! Map<String, dynamic>) {
        return true;
      }
      final ready = payload['ready'];
      if (ready is bool) {
        return ready;
      }
      return true;
    } catch (_) {
      return false;
    }
  }

  Future<bool> _ensureDependencies(String pythonExe, String scriptDir) async {
    ProcessResult check;
    try {
      check = await Process.run(
        pythonExe,
        ['-c', 'import fastapi, uvicorn, sentence_transformers, torch, numpy'],
        workingDirectory: scriptDir,
      );
    } catch (_) {
      lastError = AppStrings.runnerCannotRunPython;
      return false;
    }
    if (check.exitCode == 0) {
      return true;
    }

    final requirements = _resolveRequirementsPath(scriptDir);
    if (requirements == null) {
      lastError = AppStrings.runnerDependencyMissing;
      return false;
    }

    lastError = AppStrings.runnerInstallingDependencies;
    ProcessResult install;
    try {
      install = await Process.run(
        pythonExe,
        ['-I', '-m', 'pip', 'install', '-r', requirements],
        workingDirectory: scriptDir,
      );
    } catch (_) {
      lastError = AppStrings.runnerCannotRunPip;
      return false;
    }
    if (install.exitCode != 0) {
      final stderr = (install.stderr is String)
          ? (install.stderr as String).trim()
          : '';
      lastError = stderr.isNotEmpty
        ? _shortenForToast(stderr)
        : AppStrings.runnerDependencyInstallFailed;
      return false;
    }
    return true;
  }

  String? _resolveRequirementsPath(String scriptDir) {
    final sep = Platform.pathSeparator;
    Directory dir = Directory(scriptDir);
    while (true) {
      final candidate = File('${dir.path}${sep}requirements.txt');
      if (candidate.existsSync()) {
        return candidate.path;
      }
      final parent = dir.parent;
      if (parent.path == dir.path) {
        break;
      }
      dir = parent;
    }
    return null;
  }

  String? _resolvePythonExecutable() {
    final env = Platform.environment;
    final override = env['LOCAL_PYTHON_PATH'];
    if (override != null && override.trim().isNotEmpty) {
      return override.trim();
    }
    final baseDir = workingDirectory != null
        ? Directory(workingDirectory!)
        : File(scriptPath).parent;
    final found = _findVenvPython(baseDir);
    if (found != null) {
      return found;
    }

    if (Platform.isMacOS || Platform.isLinux) {
      final candidates = <String>[
        '/opt/homebrew/bin/python3',
        '/usr/local/bin/python3',
        '/usr/bin/python3',
        '/usr/bin/python',
      ];
      for (final candidate in candidates) {
        if (File(candidate).existsSync()) {
          return candidate;
        }
      }
    }

    if (Platform.isWindows) {
      return 'python';
    }
    return 'python3';
  }

  String? _findVenvPython(Directory start) {
    final sep = Platform.pathSeparator;
    Directory dir = start;
    while (true) {
      final managed = Platform.isWindows
          ? '${dir.path}$sep$_managedVenvName${sep}Scripts${sep}python.exe'
          : '${dir.path}$sep$_managedVenvName${sep}bin${sep}python';
      if (File(managed).existsSync()) return managed;

      final venvExe = Platform.isWindows
          ? '${dir.path}$sep.venv${sep}Scripts${sep}python.exe'
          : '${dir.path}$sep.venv${sep}bin${sep}python';
      if (File(venvExe).existsSync()) return venvExe;
      final parent = dir.parent;
      if (parent.path == dir.path) {
        break;
      }
      dir = parent;
    }
    return null;
  }

  String? _resolveVenvDir(String pythonExe) {
    final file = File(pythonExe);
    if (!file.existsSync()) {
      return null;
    }
    final binDir = file.parent;
    final venvDir = binDir.parent;
    if (File('${venvDir.path}${Platform.pathSeparator}pyvenv.cfg').existsSync()) {
      return venvDir.path;
    }
    return null;
  }

  Future<bool> _recoverManagedVenv() async {
    final scriptDir = workingDirectory ?? File(scriptPath).parent.path;
    final requirements = _resolveRequirementsPath(scriptDir);
    if (requirements == null) {
      lastError = AppStrings.runnerDependencyMissing;
      return false;
    }

    final venvPath = '$scriptDir${Platform.pathSeparator}$_managedVenvName';
    final systemPython = await _resolveSystemPython();
    if (systemPython == null) {
      lastError = AppStrings.runnerNoSystemPython;
      return false;
    }

    lastError = AppStrings.runnerRepairingEnvironment;
    final create = await Process.run(
      systemPython,
      ['-m', 'venv', venvPath],
      workingDirectory: scriptDir,
    );
    if (create.exitCode != 0) {
      final stderr = (create.stderr is String)
          ? (create.stderr as String).trim()
          : '';
        lastError = stderr.isNotEmpty
          ? stderr.split('\n').first
          : AppStrings.runnerRepairFailed;
      return false;
    }

    final venvPython = Platform.isWindows
        ? '$venvPath${Platform.pathSeparator}Scripts${Platform.pathSeparator}python.exe'
        : '$venvPath${Platform.pathSeparator}bin${Platform.pathSeparator}python';
    await Process.run(
      venvPython,
      ['-m', 'ensurepip', '--upgrade'],
      workingDirectory: scriptDir,
    );
    await Process.run(
      venvPython,
      ['-m', 'pip', 'install', '--upgrade', 'pip', 'setuptools', 'wheel'],
      workingDirectory: scriptDir,
    );
    final install = await Process.run(
      venvPython,
      ['-m', 'pip', 'install', '-r', requirements],
      workingDirectory: scriptDir,
    );
    if (install.exitCode != 0) {
      final stderr = (install.stderr is String)
          ? (install.stderr as String).trim()
          : '';
      lastError = stderr.isNotEmpty
          ? stderr.split('\n').first
          : AppStrings.runnerDependencyInstallFailed;
      return false;
    }

    return true;
  }

  Future<String?> _resolveSystemPython() async {
    final env = Map<String, String>.from(Platform.environment);
    if (Platform.isMacOS || Platform.isLinux) {
      final current = env['PATH'] ?? '';
      const extra = '/opt/homebrew/bin:/usr/local/bin:/usr/bin';
      env['PATH'] = '$extra:$current';
    }

    final absoluteCandidates = <String>[
      if (Platform.isMacOS || Platform.isLinux) '/usr/bin/python3',
      if (Platform.isMacOS) '/opt/homebrew/bin/python3',
      if (Platform.isMacOS) '/usr/local/bin/python3',
    ];
    for (final candidate in absoluteCandidates) {
      if (File(candidate).existsSync()) {
        return candidate;
      }
    }

    final pathResolved = _findExecutableInPath(
      Platform.isWindows ? 'python.exe' : 'python3',
      env,
    );
    if (pathResolved != null) {
      return pathResolved;
    }
    final pathResolvedAlt = _findExecutableInPath(
      Platform.isWindows ? 'python.exe' : 'python',
      env,
    );
    if (pathResolvedAlt != null) {
      return pathResolvedAlt;
    }

    final candidates = <String>['python3', 'python'];
    for (final candidate in candidates) {
      try {
        final result = await Process.run(candidate, ['-V'], environment: env);
        if (result.exitCode == 0) {
          return candidate;
        }
      } catch (_) {
        // Ignore missing executables.
      }
    }
    return null;
  }

  String? _findExecutableInPath(String name, Map<String, String> env) {
    final path = env['PATH'];
    if (path == null || path.isEmpty) {
      return null;
    }
    final sep = Platform.isWindows ? ';' : ':';
    for (final dir in path.split(sep)) {
      if (dir.trim().isEmpty) {
        continue;
      }
      final candidate = File('${dir.trim()}${Platform.pathSeparator}$name');
      if (candidate.existsSync()) {
        return candidate.path;
      }
    }
    return null;
  }

  bool _isSandboxed() {
    if (!Platform.isMacOS) {
      return false;
    }
    final env = Platform.environment;
    if (env.containsKey('APP_SANDBOX_CONTAINER_ID')) {
      return true;
    }
    final home = env['HOME'] ?? '';
    return home.contains('/Library/Containers/');
  }

  String _shortenForToast(String message, {int max = 240}) {
    final trimmed = message.trim();
    if (trimmed.length <= max) {
      return trimmed;
    }
    return '${trimmed.substring(0, max)}…';
  }
}
