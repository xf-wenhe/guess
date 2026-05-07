import 'dart:math';

import 'package:flutter/material.dart';
import 'package:guess/resources/resources.dart';

class StarBurst extends StatelessWidget {
  const StarBurst({super.key, required this.animation});

  final Animation<double> animation;

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: animation,
      builder: (context, child) {
        return CustomPaint(
          painter: _StarBurstPainter(animation.value),
        );
      },
    );
  }
}

class _StarBurstPainter extends CustomPainter {
  _StarBurstPainter(this.t);

  final double t;

  @override
  void paint(Canvas canvas, Size size) {
    final center = Offset(size.width / 2, size.height / 2);
    final paint = Paint()..style = PaintingStyle.fill;
    const colors = AppColors.starBurstPalette;
    final maxRadius = size.shortestSide * 0.5;
    for (var i = 0; i < 24; i++) {
      final angle = (pi * 2 / 24) * i + t * 2;
      final radius = maxRadius * (0.15 + 0.85 * t);
      final dx = center.dx + cos(angle) * radius;
      final dy = center.dy + sin(angle) * radius;
      paint.color = colors[i % colors.length].withOpacity((1 - t).clamp(0, 1));
      final starSize = 10 + (i % 4) * 4;
      _drawStar(canvas, Offset(dx, dy), starSize * (1 - t * 0.4), paint);
    }
  }

  void _drawStar(Canvas canvas, Offset center, double radius, Paint paint) {
    final path = Path();
    const points = 5;
    final inner = radius * 0.45;
    for (var i = 0; i < points * 2; i++) {
      final isOuter = i.isEven;
      final r = isOuter ? radius : inner;
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
  bool shouldRepaint(covariant _StarBurstPainter oldDelegate) {
    return oldDelegate.t != t;
  }
}
