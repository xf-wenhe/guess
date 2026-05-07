import 'dart:convert';

import 'package:guess/resources/resources.dart';
import 'package:http/http.dart' as http;

class EmbeddingFetchResult {
  const EmbeddingFetchResult({required this.embedding, required this.source});

  final List<double> embedding;
  final String source;
}

class EmbeddingService {
  EmbeddingService({
    required this.localEndpoint,
    required this.onlineEndpoint,
    required this.embeddingPrefix,
  });

  final String localEndpoint;
  final String onlineEndpoint;
  final String embeddingPrefix;

  final Map<String, List<double>> _cache = {};
  final Set<String> _readyChecked = <String>{};
  String onlineUrl = '';

  String _embeddingText(String text) => '$embeddingPrefix$text';

  void clearCache() {
    _cache.clear();
  }

  Future<EmbeddingFetchResult?> fetch(String text) async {
    final payloadText = _embeddingText(text);
    final resolvedOnline =
        onlineUrl.isNotEmpty ? onlineUrl.trim() : onlineEndpoint.trim();
    final endpoints = <_EmbeddingEndpoint>[
      if (resolvedOnline.isNotEmpty)
        _EmbeddingEndpoint(label: AppStrings.onlineSourceLabel, url: resolvedOnline),
      _EmbeddingEndpoint(label: AppStrings.localSourceLabel, url: localEndpoint),
    ];

    for (final endpoint in endpoints) {
      await _waitReadyIfNeeded(endpoint.url);

      final cacheKey = '${endpoint.url}|$payloadText';
      final cached = _cache[cacheKey];
      if (cached != null) {
        return EmbeddingFetchResult(embedding: cached, source: endpoint.label);
      }
      try {
        final response = await http.post(
          Uri.parse(endpoint.url),
          headers: {'Content-Type': 'application/json'},
          body: jsonEncode({'text': payloadText}),
        ).timeout(const Duration(milliseconds: 2200));
        if (response.statusCode != 200) {
          continue;
        }
        final data = jsonDecode(response.body) as Map<String, dynamic>;
        final embedding = (data['embedding'] as List<dynamic>?)
            ?.map((e) => (e as num).toDouble())
            .toList();
        if (embedding == null || embedding.isEmpty) {
          continue;
        }
        _cache[cacheKey] = embedding;
        return EmbeddingFetchResult(embedding: embedding, source: endpoint.label);
      } catch (_) {
        continue;
      }
    }

    return null;
  }

  Future<bool> probe(String url) async {
    final uri = Uri.parse(url);
    if (uri.path.endsWith('/embed')) {
      final healthUri = uri.replace(path: uri.path.replaceFirst(RegExp(r'/embed$'), '/health'));
      try {
        final response = await http
            .get(healthUri)
            .timeout(const Duration(seconds: 2));
        if (response.statusCode == 200) {
          return true;
        }
      } catch (_) {
        // Ignore health probe errors and fall back to embed probe.
      }
    }
    try {
      final response = await http
          .post(
            uri,
            headers: {'Content-Type': 'application/json'},
            body: jsonEncode({'text': _embeddingText(AppStrings.probeText)}),
          )
          .timeout(const Duration(seconds: 8));
      if (response.statusCode != 200) {
        return false;
      }
      final data = jsonDecode(response.body) as Map<String, dynamic>;
      final embedding = (data['embedding'] as List<dynamic>?)
          ?.map((e) => (e as num).toDouble())
          .toList();
      return embedding != null && embedding.isNotEmpty;
    } catch (_) {
      return false;
    }
  }

  Future<void> _waitReadyIfNeeded(String url) async {
    final uri = Uri.parse(url);
    if (!uri.path.endsWith('/embed')) {
      return;
    }

    final endpointKey = uri.toString();
    if (_readyChecked.contains(endpointKey)) {
      return;
    }

    final readyUri = uri.replace(path: uri.path.replaceFirst(RegExp(r'/embed$'), '/ready'));
    final deadline = DateTime.now().add(const Duration(milliseconds: 1600));
    var readySupported = true;
    while (DateTime.now().isBefore(deadline)) {
      try {
        final response = await http
            .get(readyUri)
            .timeout(const Duration(milliseconds: 1200));
        if (response.statusCode == 404) {
          readySupported = false;
          break;
        }
        if (response.statusCode != 200) {
          break;
        }
        final payload = jsonDecode(response.body);
        if (payload is! Map<String, dynamic>) {
          _readyChecked.add(endpointKey);
          return;
        }
        final ready = payload['ready'];
        if (ready is bool) {
          if (ready) {
            _readyChecked.add(endpointKey);
            return;
          }
          await Future<void>.delayed(const Duration(milliseconds: 150));
          continue;
        }
        _readyChecked.add(endpointKey);
        return;
      } catch (_) {
        break;
      }
    }

    if (!readySupported) {
      _readyChecked.add(endpointKey);
      return;
    }
  }
}

class _EmbeddingEndpoint {
  const _EmbeddingEndpoint({required this.label, required this.url});

  final String label;
  final String url;
}
