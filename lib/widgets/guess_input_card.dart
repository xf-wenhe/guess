import 'package:flutter/material.dart';
import 'package:guess/resources/resources.dart';

class GuessInputCard extends StatefulWidget {
  const GuessInputCard({
    super.key,
    required this.controller,
    required this.focusNode,
    required this.inputDisabled,
    required this.submitting,
    required this.submitDisabled,
    required this.onSubmit,
  });

  final TextEditingController controller;
  final FocusNode focusNode;
  final bool inputDisabled;
  final bool submitting;
  final bool submitDisabled;
  final VoidCallback onSubmit;

  @override
  State<GuessInputCard> createState() => _GuessInputCardState();
}

class _GuessInputCardState extends State<GuessInputCard>
    with SingleTickerProviderStateMixin {
  late final AnimationController _pulseController;
  bool _isFocused = false;

  @override
  void initState() {
    super.initState();
    _pulseController = AnimationController(
      vsync: this,
      duration: const Duration(seconds: 2),
    )..repeat(reverse: true);
    widget.focusNode.addListener(_onFocusChange);
  }

  void _onFocusChange() {
    setState(() {
      _isFocused = widget.focusNode.hasFocus;
    });
  }

  @override
  void dispose() {
    _pulseController.dispose();
    widget.focusNode.removeListener(_onFocusChange);
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: _pulseController,
      builder: (context, _) {
        final glowOpacity = (_isFocused ? 0.8 : 0.3) * _pulseController.value;

        return Container(
          width: double.infinity,
          padding: const EdgeInsets.all(2),
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(20),
            gradient: LinearGradient(
              colors: _isFocused
                  ? [
                      AppColors.neonPurple.withOpacity(0.5 + glowOpacity * 0.3),
                      AppColors.neonCyan.withOpacity(0.5 + glowOpacity * 0.3),
                    ]
                  : [
                      Colors.white.withOpacity(0.08),
                      Colors.white.withOpacity(0.05),
                    ],
            ),
            boxShadow: _isFocused
                ? [
                    BoxShadow(
                      color: AppColors.neonPurple.withOpacity(0.2),
                      blurRadius: 20,
                      spreadRadius: 2,
                    ),
                  ]
                : null,
          ),
          child: Container(
            padding: const EdgeInsets.fromLTRB(8, 8, 8, 8),
            decoration: BoxDecoration(
              color: AppColors.inputBackground,
              borderRadius: BorderRadius.circular(18),
            ),
            child: Row(
              children: [
                Expanded(
                  child: TextField(
                    controller: widget.controller,
                    focusNode: widget.focusNode,
                    maxLength: 5,
                    enabled: !widget.inputDisabled,
                    textInputAction: TextInputAction.done,
                    minLines: 1,
                    maxLines: 1,
                    style: const TextStyle(
                      fontFamily: AppFonts.primaryFamily,
                      color: AppColors.textPrimary,
                      fontSize: 16,
                    ),
                    cursorColor: AppColors.neonCyan,
                    onSubmitted: (_) {
                      if (!widget.submitDisabled) {
                        widget.onSubmit();
                      }
                    },
                    decoration: InputDecoration(
                      hintText: AppStrings.inputHint,
                      hintStyle: const TextStyle(
                        fontFamily: AppFonts.primaryFamily,
                        color: AppColors.textSecondary,
                        fontSize: 15,
                      ),
                      counterText: '',
                      filled: true,
                      fillColor: AppColors.inputFill,
                      contentPadding: const EdgeInsets.symmetric(
                        horizontal: 14,
                        vertical: 11,
                      ),
                      border: OutlineInputBorder(
                        borderRadius: BorderRadius.circular(14),
                        borderSide: BorderSide(
                          color: Colors.white.withOpacity(0.1),
                        ),
                      ),
                      enabledBorder: OutlineInputBorder(
                        borderRadius: BorderRadius.circular(14),
                        borderSide: BorderSide(
                          color: Colors.white.withOpacity(0.1),
                        ),
                      ),
                      focusedBorder: OutlineInputBorder(
                        borderRadius: BorderRadius.circular(14),
                        borderSide: const BorderSide(
                          color: AppColors.neonCyan,
                          width: 1.5,
                        ),
                      ),
                      disabledBorder: OutlineInputBorder(
                        borderRadius: BorderRadius.circular(14),
                        borderSide: BorderSide(
                          color: Colors.white.withOpacity(0.05),
                        ),
                      ),
                    ),
                  ),
                ),
                const SizedBox(width: 8),
                // 发送按钮 — 霓虹渐变
                Container(
                  decoration: BoxDecoration(
                    gradient: LinearGradient(
                      colors: widget.submitDisabled
                          ? [
                              Colors.white.withOpacity(0.05),
                              Colors.white.withOpacity(0.03),
                            ]
                          : [
                              AppColors.neonPurple,
                              AppColors.neonCyan,
                            ],
                      begin: Alignment.topLeft,
                      end: Alignment.bottomRight,
                    ),
                    borderRadius: BorderRadius.circular(16),
                    boxShadow: widget.submitDisabled
                        ? null
                        : [
                            BoxShadow(
                              color: AppColors.neonPurple.withOpacity(0.4),
                              blurRadius: 12,
                              offset: const Offset(0, 4),
                            ),
                          ],
                  ),
                  child: ElevatedButton(
                    onPressed:
                        widget.submitDisabled ? null : widget.onSubmit,
                    style: ElevatedButton.styleFrom(
                      minimumSize: const Size(90, 44),
                      backgroundColor: Colors.transparent,
                      foregroundColor: Colors.white,
                      shadowColor: Colors.transparent,
                      disabledBackgroundColor: Colors.transparent,
                      disabledForegroundColor: AppColors.textMuted,
                      shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(16),
                      ),
                    ),
                    child: widget.submitting
                        ? const SizedBox(
                            width: 20,
                            height: 20,
                            child: CircularProgressIndicator(
                              strokeWidth: 2.2,
                              valueColor:
                                  AlwaysStoppedAnimation<Color>(Colors.white),
                            ),
                          )
                        : const Text(AppStrings.inputSend),
                  ),
                ),
              ],
            ),
          ),
        );
      },
    );
  }
}
