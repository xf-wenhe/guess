import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:guess/services/embedding_service.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

void main() {
  test('falls back to individual embed requests when batch fails', () async {
    var individualCalls = 0;
    final client = MockClient((request) async {
      if (request.url.path.endsWith('/ready')) {
        return http.Response(jsonEncode({'ready': true}), 200);
      }
      if (request.url.path.endsWith('/embed_batch')) {
        return http.Response('batch disabled', 500);
      }
      if (request.url.path.endsWith('/embed')) {
        individualCalls += 1;
        final payload = jsonDecode(request.body) as Map<String, dynamic>;
        return http.Response(
          jsonEncode({
            'embedding': [
              (payload['text'] as String).length.toDouble(),
              1.0,
            ],
          }),
          200,
        );
      }
      return http.Response('not found', 404);
    });

    final service = EmbeddingService(
      localEndpoint: 'http://local.test/embed',
      onlineEndpoint: '',
      embeddingPrefix: '',
      client: client,
    );

    final result = await service.fetchMany(['甲', '乙']);

    expect(result, isNotNull);
    expect(result!.keys, unorderedEquals(['甲', '乙']));
    expect(individualCalls, 2);
  });

  test('uses endpoint and payload as cache key', () async {
    var batchCalls = 0;
    final client = MockClient((request) async {
      if (request.url.path.endsWith('/ready')) {
        return http.Response(jsonEncode({'ready': true}), 200);
      }
      if (request.url.path.endsWith('/embed_batch')) {
        batchCalls += 1;
        final payload = jsonDecode(request.body) as Map<String, dynamic>;
        final texts = payload['texts'] as List<dynamic>;
        return http.Response(
          jsonEncode({
            'embeddings': [
              for (final text in texts) [(text as String).length.toDouble()]
            ],
          }),
          200,
        );
      }
      return http.Response('not found', 404);
    });

    final service = EmbeddingService(
      localEndpoint: 'http://local.test/embed',
      onlineEndpoint: '',
      embeddingPrefix: '前缀：',
      client: client,
    );

    final first = await service.fetchMany(['太阳']);
    final second = await service.fetchMany(['太阳']);

    expect(first, isNotNull);
    expect(second, isNotNull);
    expect(first!['太阳']!.embedding, second!['太阳']!.embedding);
    expect(batchCalls, 1);
  });
}
