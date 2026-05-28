import 'dart:math';

import 'package:flutter/material.dart';

/// 金色庆典动效
/// 中心辐射 + 星光粒子 + 金色光环旋转 + 彩色碎屑飘落
class StarBurst extends StatelessWidget {
  const StarBurst({super.key, required this.animation});

  final Animation<double> animation;

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: animation,
      builder: (context, child) {
        final t = animation.value;
        return SizedBox.expand(
          child: CustomPaint(
            painter: _CelebrationPainter(t),
          ),
        );
      },
    );
  }
}

class _CelebrationPainter extends CustomPainter {
  _CelebrationPainter(this.t);

  final double t;
  static final _rand = Random(777);
  // 星光
  static final _starAngles = List.generate(24, (_) => _rand.nextDouble() * pi * 2);
  static final _starSpeeds = List.generate(24, (_) => 0.4 + _rand.nextDouble() * 1.0);
  static final _starSizes = List.generate(24, (_) => 6.0 + _rand.nextDouble() * 10);
  static final _starDelays = List.generate(24, (_) => _rand.nextDouble() * 0.25);
  // 彩带
  static final _confettiX = List.generate(20, (_) => _rand.nextDouble());
  static final _confettiDelay = List.generate(20, (_) => _rand.nextDouble() * 0.6);
  static final _confettiSpeed = List.generate(20, (_) => 0.5 + _rand.nextDouble() * 0.8);
  static final _confettiAngle = List.generate(20, (_) => (_rand.nextDouble() - 0.5) * 0.6);

  static const _gold = <Color>[
    Color(0xFFFFD54F),
    Color(0xFFFFF59D),
    Color(0xFFFFC107),
    Color(0xFFFFE082),
    Color(0xFFFFB300),
    Color(0xFFFFECB3),
  ];
  static const _confettiColors = <Color>[
    Color(0xFFFFD54F),
    Color(0xFFFF8A65),
    Color(0xFF81C784),
    Color(0xFF64B5F6),
    Color(0xFFCE93D8),
    Color(0xFFFFF176),
  ];

  @override
  void paint(Canvas canvas, Size size) {
    final center = Offset(size.width / 2, size.height / 2);
    final maxR = size.shortestSide * 0.55;
    final paint = Paint()..style = PaintingStyle.fill;

    // ---- 中心光晕脉冲 ----
    final pulse = 1.0 + sin(t * pi * 3) * 0.15;
    for (var layer = 3; layer >= 0; layer--) {
      final glowPaint = Paint()
        ..color = _gold[layer % _gold.length].withOpacity((0.15 + layer * 0.12) * pulse)
        ..style = PaintingStyle.fill
        ..maskFilter = MaskFilter.blur(BlurStyle.normal, 6 + layer * 6);
      canvas.drawCircle(center, maxR * (0.04 + layer * 0.05) * pulse, glowPaint);
    }

    // ---- 旋转光环 ----
    final ringAngle = t * pi * 2;
    for (var ring = 0; ring < 2; ring++) {
      final ringR = maxR * (0.15 + ring * 0.18) * (0.6 + 0.4 * t);
      final ringOpacity = (t < 0.1 ? t / 0.1 : (1.0 - t).clamp(0.0, 1.0)) * 0.5;
      if (ringOpacity <= 0) continue;

      // 旋转的不完整光环 (弧线)
      for (var seg = 0; seg < 4; seg++) {
        final segStart = ringAngle + seg * pi / 2;
        final segSweep = pi / 3;
        final ringPaint = Paint()
          ..color = _gold[ring].withOpacity(ringOpacity)
          ..style = PaintingStyle.stroke
          ..strokeWidth = 2.5 * ringOpacity
          ..strokeCap = StrokeCap.round;
        canvas.drawArc(
          Rect.fromCircle(center: center, radius: ringR),
          segStart,
          segSweep,
          false,
          ringPaint,
        );
      }
    }

    // ---- 24个星光粒子 ----
    for (var i = 0; i < 24; i++) {
      final starT = ((t - _starDelays[i]) / 0.6).clamp(0.0, 1.0);
      if (starT <= 0) continue;
      final alpha = (1.0 - starT).clamp(0.0, 1.0);
      if (alpha <= 0.03) continue;

      final distance = maxR * _starSpeeds[i] * starT;
      final angle = _starAngles[i] + starT * 1.8;
      final dx = center.dx + cos(angle) * distance;
      final dy = center.dy + sin(angle) * distance * 0.85; // 稍微压扁

      paint.color = _gold[i % _gold.length].withOpacity(alpha);
      final starSize = _starSizes[i] * alpha;
      _drawStarShape(canvas, Offset(dx, dy), starSize, paint, 5);

      // 辉光
      final glowPaint = Paint()
        ..color = _gold[i % _gold.length].withOpacity(alpha * 0.35)
        ..maskFilter = const MaskFilter.blur(BlurStyle.normal, 3);
      canvas.drawCircle(Offset(dx, dy), starSize * 0.6, glowPaint);
    }

    // ---- 彩带飘落 (从上方) ----
    for (var i = 0; i < 20; i++) {
      final confT = ((t - _confettiDelay[i]) / 0.8).clamp(0.0, 1.0);
      if (confT <= 0) continue;
      final confAlpha = (1.0 - confT * 0.4).clamp(0.0, 1.0);
      if (confAlpha <= 0.05) continue;

      final cx = size.width * (_confettiX[i] + confT * _confettiAngle[i]).clamp(0.05, 0.95);
      final cy = size.height * (-0.05 + confT * _confettiSpeed[i] * 1.1).clamp(0.0, 1.2);
      if (cy > size.height) continue;

      final confSize = 5 + (i % 3) * 3;
      final confPaint = Paint()
        ..color = _confettiColors[i % _confettiColors.length].withOpacity(confAlpha)
        ..style = PaintingStyle.fill;

      // 旋转小矩形
      canvas.save();
      canvas.translate(cx, cy);
      canvas.rotate(confT * 5 + i * 0.8);
      canvas.drawRect(
        Rect.fromCenter(center: Offset.zero, width: confSize * 1.6, height: confSize * 0.6),
        confPaint,
      );
      canvas.restore();

      // 额外的圆形碎屑
      if (i % 3 == 1) {
        final dotPaint = Paint()
          ..color = _gold[i % _gold.length].withOpacity(confAlpha * 0.7);
        canvas.drawCircle(Offset(cx + 2, cy + 2), 2, dotPaint);
      }
    }

    // ---- 底部光芒溢出 ----
    if (t > 0.3) {
      final bottomGlow = (t - 0.3).clamp(0.0, 1.0);
      final bottomPaint = Paint()
        ..color = _gold[0].withOpacity(bottomGlow * 0.15)
        ..maskFilter = const MaskFilter.blur(BlurStyle.normal, 20);
      canvas.drawCircle(
        Offset(center.dx, center.dy + maxR * 0.3),
        maxR * 0.4 * bottomGlow,
        bottomPaint,
      );
    }
  }

  void _drawStarShape(Canvas canvas, Offset center, double radius, Paint paint, int points) {
    final path = Path();
    final inner = radius * 0.4;
    for (var i = 0; i < points * 2; i++) {
      final r = i.isEven ? radius : inner;
      final angle = (pi / points) * i - pi / 2;
      final x = center.dx + cos(angle) * r;
      final y = center.dy + sin(angle) * r;
      if (i == 0) {
        path.moveTo(x, y);
      } else {
        path.lineTo(x, y);
      }
    }
    path.close();
    canvas.drawPath(path, paint);
  }

  @override
  bool shouldRepaint(covariant _CelebrationPainter oldDelegate) {
    return oldDelegate.t != t;
  }
}
