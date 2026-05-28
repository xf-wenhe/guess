import 'dart:math';

import 'package:flutter/material.dart';

/// 炸弹爆炸动效
/// 阶段1: 白色闪光 → 阶段2: 冲击波扩散 → 阶段3: 碎片四散 → 阶段4: 烟雾消散
class Explosion extends StatelessWidget {
  const Explosion({super.key, required this.animation});

  final Animation<double> animation;

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: animation,
      builder: (context, child) {
        final t = animation.value;
        return SizedBox.expand(
          child: CustomPaint(
            painter: _BombExplosionPainter(t),
          ),
        );
      },
    );
  }
}

class _BombExplosionPainter extends CustomPainter {
  _BombExplosionPainter(this.t);

  final double t;
  // 固定的随机种子保证画面一致性
  static final _rand = Random(42);
  static final _angles = List.generate(40, (_) => _rand.nextDouble() * pi * 2);
  static final _speeds = List.generate(40, (_) => 0.3 + _rand.nextDouble() * 1.2);
  static final _sizes = List.generate(40, (_) => 4.0 + _rand.nextDouble() * 14);
  static final _offsets = List.generate(40, (_) => _rand.nextDouble() * 0.3);

  // 爆炸调色板
  static const _core = <Color>[
    Color(0xFFFFF5E0),
    Color(0xFFFFD700),
    Color(0xFFFF8C00),
  ];
  static const _fire = <Color>[
    Color(0xFFFF3B30),
    Color(0xFFFF6B35),
    Color(0xFFFF9500),
    Color(0xFFFFD60A),
  ];
  static const _smoke = <Color>[
    Color(0xFF2C2C3A),
    Color(0xFF1A1A2E),
    Color(0xFF3A3A4A),
    Color(0xFF4A4A5A),
  ];

  @override
  void paint(Canvas canvas, Size size) {
    final center = Offset(size.width / 2, size.height / 2);
    final maxR = size.shortestSide * 0.55;

    // ---- 阶段0: 初始白色闪光 ----
    if (t < 0.15) {
      final flashOpacity = (1.0 - t / 0.15).clamp(0.0, 1.0);
      final flashPaint = Paint()
        ..color = Colors.white.withOpacity(flashOpacity * 0.9)
        ..style = PaintingStyle.fill;
      canvas.drawCircle(center, maxR * 0.5, flashPaint);
    }

    // ---- 冲击波圆环 (2层) ----
    for (var ring = 0; ring < 2; ring++) {
      final ringDelay = ring * 0.08;
      final ringT = ((t - ringDelay) / 0.7).clamp(0.0, 1.0);
      if (ringT <= 0) continue;
      final ringRadius = maxR * (0.05 + ringT * 0.95);
      final ringOpacity = (1.0 - ringT).clamp(0.0, 1.0) * 0.6;
      if (ringOpacity <= 0) continue;

      final ringPaint = Paint()
        ..color = _fire[ring].withOpacity(ringOpacity)
        ..style = PaintingStyle.stroke
        ..strokeWidth = 6 * (1.0 - ringT).clamp(0.3, 1.0);
      canvas.drawCircle(center, ringRadius, ringPaint);

      // 外圈细光环
      final outerRingPaint = Paint()
        ..color = Colors.white.withOpacity(ringOpacity * 0.4)
        ..style = PaintingStyle.stroke
        ..strokeWidth = 2 * (1.0 - ringT).clamp(0.2, 1.0);
      canvas.drawCircle(center, ringRadius + 3, outerRingPaint);
    }

    // ---- 核心火球 ----
    final coreT = (t / 0.5).clamp(0.0, 1.0);
    final coreOpacity = (1.0 - coreT).clamp(0.0, 1.0);
    if (coreOpacity > 0) {
      // 多层光晕核心
      for (var layer = 2; layer >= 0; layer--) {
        final corePaint = Paint()
          ..color = _core[layer].withOpacity(coreOpacity * (0.3 + layer * 0.25))
          ..style = PaintingStyle.fill
          ..maskFilter = const MaskFilter.blur(BlurStyle.normal, 5);
        canvas.drawCircle(center, maxR * (0.03 + layer * 0.06) * coreT, corePaint);
      }
    }

    // ---- 40个爆炸碎片 ----
    for (var i = 0; i < 40; i++) {
      final fragmentT = ((t - _offsets[i] * 0.15) / 0.7).clamp(0.0, 1.0);
      if (fragmentT <= 0) continue;

      final distance = maxR * _speeds[i] * fragmentT;
      final angle = _angles[i] + fragmentT * 0.8; // 略微旋转
      final alpha = (1.0 - fragmentT).clamp(0.0, 1.0);

      if (alpha <= 0.05) continue;

      final dx = center.dx + cos(angle) * distance;
      final dy = center.dy + sin(angle) * distance;
      final particleSize = _sizes[i] * (1.0 - fragmentT * 0.4);

      if (i < 30) {
        // 火焰粒子
        final firePaint = Paint()
          ..color = _fire[i % _fire.length].withOpacity(alpha * 0.9)
          ..style = PaintingStyle.fill;
        canvas.drawCircle(Offset(dx, dy), particleSize, firePaint);

        // 发光尾迹
        final trailPaint = Paint()
          ..color = _fire[i % _fire.length].withOpacity(alpha * 0.3)
          ..style = PaintingStyle.fill
          ..maskFilter = const MaskFilter.blur(BlurStyle.normal, 3);
        final trailDx = center.dx + cos(angle) * (distance * 0.7);
        final trailDy = center.dy + sin(angle) * (distance * 0.7);
        canvas.drawCircle(Offset(trailDx, trailDy), particleSize * 1.8, trailPaint);
      } else {
        // 烟雾/碎片粒子
        final smokePaint = Paint()
          ..color = _smoke[i % _smoke.length].withOpacity(alpha * 0.7)
          ..style = PaintingStyle.fill;
        final smokePath = Path();
        smokePath.addPolygon([
          Offset(dx - particleSize, dy - particleSize * 0.6),
          Offset(dx + particleSize, dy - particleSize * 0.8),
          Offset(dx + particleSize * 1.2, dy + particleSize * 0.5),
          Offset(dx - particleSize * 0.8, dy + particleSize * 0.4),
        ], true);
        canvas.drawPath(smokePath, smokePaint);
      }
    }

    // ---- 后期闪烁 ----
    if (t > 0.4 && t < 0.8) {
      final sparkleCount = 8;
      final sparkleT = ((t - 0.4) / 0.4).clamp(0.0, 1.0);
      final sparkleAlpha = sin(sparkleT * pi).clamp(0.0, 1.0) * 0.7;
      for (var i = 0; i < sparkleCount; i++) {
        final sAngle = (pi * 2 / sparkleCount) * i + sparkleT * 1.5;
        final sDist = maxR * 0.3 * (1 + sparkleT);
        final sx = center.dx + cos(sAngle) * sDist;
        final sy = center.dy + sin(sAngle) * sDist;
        final sparkPaint = Paint()
          ..color = Colors.white.withOpacity(sparkleAlpha * (0.5 + 0.5 * (i % 2)))
          ..style = PaintingStyle.fill
          ..maskFilter = const MaskFilter.blur(BlurStyle.normal, 2);
        canvas.drawCircle(Offset(sx, sy), 2.5, sparkPaint);
      }
    }
  }

  @override
  bool shouldRepaint(covariant _BombExplosionPainter oldDelegate) {
    return oldDelegate.t != t;
  }
}
