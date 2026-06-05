import 'dart:math';
import 'package:flutter/material.dart';

/// 极光渐变动画背景
/// 使用多层流动渐变模拟极光效果，营造沉浸式游戏氛围
class AuroraBackground extends StatefulWidget {
  const AuroraBackground({
    super.key,
    required this.child,
    this.speed = 1.0,
    this.intensity = 1.0,
  });

  final Widget child;
  final double speed;
  final double intensity;

  @override
  State<AuroraBackground> createState() => _AuroraBackgroundState();
}

class _AuroraBackgroundState extends State<AuroraBackground>
    with TickerProviderStateMixin {
  late final AnimationController _controller;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(
      vsync: this,
      duration: const Duration(seconds: 20),
    )..repeat();
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: _controller,
      builder: (context, _) {
        final t = _controller.value * widget.speed;
        return Stack(
          children: [
            // 底层暗色背景
            Container(color: const Color(0xFF0A0E21)),
            // 极光层 1 - 紫蓝
            Positioned.fill(
              child: CustomPaint(
                painter: _AuroraLayerPainter(
                  t: t,
                  colors: const [
                    Color(0x40667EEA),
                    Color(0x307647FF),
                    Color(0x20667EEA),
                  ],
                  offsetX: 0.0,
                  offsetY: -0.3,
                  scale: 1.2,
                  blurSigma: 60,
                ),
              ),
            ),
            // 极光层 2 - 青绿
            Positioned.fill(
              child: CustomPaint(
                painter: _AuroraLayerPainter(
                  t: t * 0.7 + 0.3,
                  colors: const [
                    Color(0x350EAAA6),
                    Color(0x2514B8A6),
                    Color(0x150EAAA6),
                  ],
                  offsetX: 0.5,
                  offsetY: 0.2,
                  scale: 1.5,
                  blurSigma: 55,
                ),
              ),
            ),
            // 极光层 3 - 粉紫
            Positioned.fill(
              child: CustomPaint(
                painter: _AuroraLayerPainter(
                  t: t * 0.5 + 0.7,
                  colors: const [
                    Color(0x308B5CF6),
                    Color(0x20EC4899),
                    Color(0x158B5CF6),
                  ],
                  offsetX: -0.3,
                  offsetY: 0.5,
                  scale: 1.8,
                  blurSigma: 65,
                ),
              ),
            ),
            // 极光层 4 - 金橙点缀
            Positioned.fill(
              child: CustomPaint(
                painter: _AuroraLayerPainter(
                  t: t * 0.3 + 0.5,
                  colors: const [
                    Color(0x15F59E0B),
                    Color(0x0AFBBF24),
                    Color(0x05F59E0B),
                  ],
                  offsetX: 0.8,
                  offsetY: -0.1,
                  scale: 1.0,
                  blurSigma: 50,
                ),
              ),
            ),
            // 粒子层
            Positioned.fill(
              child: CustomPaint(
                painter: _ParticlePainter(t: t),
              ),
            ),
            // 渐变暗角遮罩
            Positioned.fill(
              child: Container(
                decoration: BoxDecoration(
                  gradient: RadialGradient(
                    center: Alignment.center,
                    radius: 1.3,
                    colors: [
                      Colors.transparent,
                      const Color(0xFF0A0E21).withOpacity(0.3),
                    ],
                  ),
                ),
              ),
            ),
            // 内容层
            widget.child,
          ],
        );
      },
    );
  }
}

/// 极光层绘制器 — 用多个大椭圆叠加 + 大模糊模拟极光流动
class _AuroraLayerPainter extends CustomPainter {
  _AuroraLayerPainter({
    required this.t,
    required this.colors,
    required this.offsetX,
    required this.offsetY,
    required this.scale,
    required this.blurSigma,
  });

  final double t;
  final List<Color> colors;
  final double offsetX;
  final double offsetY;
  final double scale;
  final double blurSigma;

  @override
  void paint(Canvas canvas, Size size) {
    final paint = Paint()
      ..maskFilter = MaskFilter.blur(BlurStyle.normal, blurSigma);

    final w = size.width;
    final h = size.height;

    for (var i = 0; i < colors.length; i++) {
      paint.color = colors[i];
      final phase = sin(t * 2 * pi + i * 2.1);
      final dx = w * (offsetX + phase * 0.15);
      final dy = h * (offsetY + cos(t * 2 * pi + i * 1.7) * 0.12);
      final rw = w * scale * (0.7 + sin(t * pi + i) * 0.2);
      final rh = h * scale * (0.5 + cos(t * pi + i) * 0.15);
      canvas.drawOval(
        Rect.fromCenter(center: Offset(dx, dy), width: rw, height: rh),
        paint,
      );
    }
  }

  @override
  bool shouldRepaint(covariant _AuroraLayerPainter oldDelegate) =>
      t != oldDelegate.t;
}

/// 粒子绘制器 — 模拟漂浮微光粒子
class _ParticlePainter extends CustomPainter {
  _ParticlePainter({required this.t});

  final double t;

  // 预定义 40 个粒子的属性
  static const int _count = 40;

  @override
  void paint(Canvas canvas, Size size) {
    final rng = Random(42); // 固定种子保证一致性
    final paint = Paint()..style = PaintingStyle.fill;

    for (var i = 0; i < _count; i++) {
      final seed = rng.nextDouble();
      final baseX = rng.nextDouble();
      final baseY = rng.nextDouble();
      final radius = 1.0 + rng.nextDouble() * 2.5;
      final speed = 0.3 + rng.nextDouble() * 0.7;
      final amplitude = 20 + rng.nextDouble() * 40;
      final opacity = 0.15 + rng.nextDouble() * 0.45;

      final x = (baseX * size.width +
          sin(t * 2 * pi * speed + seed * 10) * amplitude) %
          size.width;
      final y = (baseY * size.height +
          cos(t * 2 * pi * speed + seed * 8) * amplitude) %
          size.height;

      paint.color = Colors.white.withOpacity(opacity);

      // 粒子光晕
      canvas.drawCircle(Offset(x, y), radius + 2, paint..color = paint.color.withOpacity(opacity * 0.3));
      // 粒子核心
      canvas.drawCircle(Offset(x, y), radius, paint..color = paint.color.withOpacity(opacity));
    }
  }

  @override
  bool shouldRepaint(covariant _ParticlePainter oldDelegate) =>
      t != oldDelegate.t;
}
