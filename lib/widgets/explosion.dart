import 'dart:math';

import 'package:flutter/material.dart';
import 'package:guess/resources/resources.dart';

class Explosion extends StatelessWidget {
  const Explosion({super.key, required this.animation});

  final Animation<double> animation;

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: animation,
      builder: (context, child) {
        final scale = 0.5 + 2.2 * animation.value;
        final opacity = 0.8 - animation.value;
        return Opacity(
          opacity: opacity.clamp(0, 1),
          child: Transform.scale(
            scale: scale,
            child: CustomPaint(
              painter: _ExplosionPainter(animation.value),
            ),
          ),
        );
      },
    );
  }
}

class _ExplosionPainter extends CustomPainter {
  _ExplosionPainter(this.t);

  final double t;

  @override
  void paint(Canvas canvas, Size size) {
    final center = Offset(size.width / 2, size.height / 2);
    const colors = AppColors.explosionPalette;
    final paint = Paint()..style = PaintingStyle.fill;

    final flash = Paint()
      ..color = AppColors.white.withOpacity((1 - t).clamp(0, 1) * 0.8)
      ..style = PaintingStyle.fill;
    canvas.drawCircle(center, size.shortestSide * (0.12 + 0.28 * t), flash);

    final maxRadius = size.shortestSide * 0.45;
    for (var i = 0; i < 28; i++) {
      final angle = (pi * 2 / 28) * i + t * 2.5;
      final radius = maxRadius * (0.25 + 0.75 * t);
      final jitter = (i % 3) * 6 * (1 - t);
      final dx = center.dx + cos(angle) * (radius + jitter);
      final dy = center.dy + sin(angle) * (radius + jitter);
      paint.color = colors[i % colors.length].withOpacity(1 - t * 0.7);
      final sizeFactor = 10 + (i % 5) * 4;
      canvas.drawCircle(Offset(dx, dy), sizeFactor * (1 - t * 0.35), paint);
    }

    final ringPaint = Paint()
      ..color = AppColors.white.withOpacity((1 - t).clamp(0, 1) * 0.5)
      ..style = PaintingStyle.stroke
      ..strokeWidth = 6 * (1 - t * 0.6);
    canvas.drawCircle(center, maxRadius * (0.2 + 0.8 * t), ringPaint);
  }

  @override
  bool shouldRepaint(covariant _ExplosionPainter oldDelegate) {
    return oldDelegate.t != t;
  }
}
