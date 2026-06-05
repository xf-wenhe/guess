import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'app.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  FlutterError.onError = (details) {
    final exception = details.exception;
    if (exception is PlatformException &&
        exception.code == 'Clipboard error') {
      // Windows clipboard may be temporarily locked by another process.
      // Silently ignore to prevent crash.
      return;
    }
    FlutterError.presentError(details);
  };
  PlatformDispatcher.instance.onError = (error, stack) {
    if (error is PlatformException && error.code == 'Clipboard error') {
      return true;
    }
    return false;
  };
  runApp(const GuessApp());
}