import 'dart:convert';

import 'package:guess/resources/resources.dart';
import 'package:http/http.dart' as http;

/// HuggingFace repo used by the embedding server as the auto-download fallback
/// when the fine-tuned model is not present locally.
///
/// The server downloads this model on first start:
///   python embedding_server.py
///
/// To use the fine-tuned model instead, set the env var before starting:
///   EMBED_MODEL_DIR=/path/to/bge-m3-finetuned-v27-semreal-anchor python embedding_server.py
///
/// Or, once the fine-tuned model is published on HuggingFace:
///   EMBED_HF_REPO=your-username/bge-m3-finetuned-v27 python embedding_server.py
const String kEmbeddingModelHfRepo = 'BAAI/bge-m3';
const String kEmbeddingServerSetupDoc =
    'https://github.com/xf-wenhe/guess#embedding-server-setup';

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

  /// Returns a human-readable message shown when neither endpoint is reachable.
  /// Instructs the user how to start the local embedding server.
  String get serverUnavailableHint => '未连接到语义模型服务。\n'
      '请在项目目录执行：python embedding_server.py\n'
      '首次运行将自动下载 $kEmbeddingModelHfRepo 模型（约 2 GB）。\n'
      '详见：$kEmbeddingServerSetupDoc';

  void clearCache() {
    _cache.clear();
    _readyChecked.clear();
  }

  Future<EmbeddingFetchResult?> fetch(String text) async {
    final results = await fetchMany([text]);
    return results?[text];
  }

  Future<Map<String, EmbeddingFetchResult>?> fetchMany(
      List<String> texts) async {
    if (texts.isEmpty) {
      return <String, EmbeddingFetchResult>{};
    }
    final uniqueTexts = texts.toSet().toList(growable: false);
    final resolvedOnline =
        onlineUrl.isNotEmpty ? onlineUrl.trim() : onlineEndpoint.trim();
    final endpoints = <_EmbeddingEndpoint>[
      if (resolvedOnline.isNotEmpty)
        _EmbeddingEndpoint(
            label: AppStrings.onlineSourceLabel, url: resolvedOnline),
      _EmbeddingEndpoint(
          label: AppStrings.localSourceLabel, url: localEndpoint),
    ];

    for (final endpoint in endpoints) {
      await _waitReadyIfNeeded(endpoint.url);

      final resolved = <String, EmbeddingFetchResult>{};
      final missingPayloads = <String>[];
      final payloadToText = <String, String>{};
      for (final text in uniqueTexts) {
        final payloadText = _embeddingText(text);
        final cacheKey = '${endpoint.url}|$payloadText';
        final cached = _cache[cacheKey];
        if (cached != null) {
          resolved[text] = EmbeddingFetchResult(
            embedding: cached,
            source: endpoint.label,
          );
        } else {
          missingPayloads.add(payloadText);
          payloadToText[payloadText] = text;
        }
      }

      try {
        if (missingPayloads.isNotEmpty) {
          final fetched = await _fetchBatch(endpoint.url, missingPayloads) ??
              await _fetchIndividually(endpoint.url, missingPayloads);
          if (fetched == null) {
            continue;
          }
          for (final entry in fetched.entries) {
            final text = payloadToText[entry.key];
            if (text == null) {
              continue;
            }
            final cacheKey = '${endpoint.url}|${entry.key}';
            _cache[cacheKey] = entry.value;
            resolved[text] = EmbeddingFetchResult(
              embedding: entry.value,
              source: endpoint.label,
            );
          }
        }
      } catch (_) {
        continue;
      }

      if (resolved.length == uniqueTexts.length) {
        return resolved;
      }
    }

    return null;
  }

  Future<Map<String, List<double>>?> _fetchBatch(
    String url,
    List<String> payloadTexts,
  ) async {
    final uri = Uri.parse(url);
    final batchUri = uri.path.endsWith('/embed')
        ? uri.replace(
            path: uri.path.replaceFirst(RegExp(r'/embed$'), '/embed_batch'))
        : uri;
    try {
      final response = await http
          .post(
            batchUri,
            headers: {'Content-Type': 'application/json'},
            body: jsonEncode({'texts': payloadTexts}),
          )
          .timeout(const Duration(seconds: 8));
      if (response.statusCode != 200) {
        return null;
      }
      final data = jsonDecode(response.body) as Map<String, dynamic>;
      final rawEmbeddings = data['embeddings'] as List<dynamic>?;
      if (rawEmbeddings == null ||
          rawEmbeddings.length != payloadTexts.length) {
        return null;
      }
      final result = <String, List<double>>{};
      for (var i = 0; i < payloadTexts.length; i += 1) {
        final embedding = (rawEmbeddings[i] as List<dynamic>?)
            ?.map((e) => (e as num).toDouble())
            .toList();
        if (embedding == null || embedding.isEmpty) {
          return null;
        }
        result[payloadTexts[i]] = embedding;
      }
      return result;
    } catch (_) {
      return null;
    }
  }

  Future<Map<String, List<double>>?> _fetchIndividually(
    String url,
    List<String> payloadTexts,
  ) async {
    final result = <String, List<double>>{};
    for (final payloadText in payloadTexts) {
      try {
        final response = await http
            .post(
              Uri.parse(url),
              headers: {'Content-Type': 'application/json'},
              body: jsonEncode({'text': payloadText}),
            )
            .timeout(const Duration(milliseconds: 2200));
        if (response.statusCode != 200) {
          return null;
        }
        final data = jsonDecode(response.body) as Map<String, dynamic>;
        final embedding = (data['embedding'] as List<dynamic>?)
            ?.map((e) => (e as num).toDouble())
            .toList();
        if (embedding == null || embedding.isEmpty) {
          return null;
        }
        result[payloadText] = embedding;
      } catch (_) {
        return null;
      }
    }
    return result;
  }

  Future<bool> probe(String url) async {
    final uri = Uri.parse(url);
    if (uri.path.endsWith('/embed')) {
      final healthUri = uri.replace(
          path: uri.path.replaceFirst(RegExp(r'/embed$'), '/health'));
      try {
        final response =
            await http.get(healthUri).timeout(const Duration(seconds: 2));
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

    final readyUri =
        uri.replace(path: uri.path.replaceFirst(RegExp(r'/embed$'), '/ready'));
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
