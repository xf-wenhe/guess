import 'package:flutter/material.dart';
import 'package:guess/resources/resources.dart';

class GuessInputCard extends StatelessWidget {
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
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.fromLTRB(8, 8, 8, 8),
      decoration: BoxDecoration(
        color: AppColors.inputBackground,
        borderRadius: BorderRadius.circular(18),
        border: Border.all(color: AppColors.inputBorder),
      ),
      child: Row(
        children: [
          Expanded(
            child: TextField(
              controller: controller,
              focusNode: focusNode,
              maxLength: 5,
              enabled: !inputDisabled,
              textInputAction: TextInputAction.done,
              minLines: 1,
              maxLines: 1,
              onSubmitted: (_) {
                if (!submitDisabled) {
                  onSubmit();
                }
              },
              decoration: InputDecoration(
                hintText: AppStrings.inputHint,
                counterText: '',
                filled: true,
                fillColor: AppColors.inputFill,
                contentPadding: const EdgeInsets.symmetric(
                  horizontal: 14,
                  vertical: 11,
                ),
                border: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(12),
                  borderSide: const BorderSide(color: AppColors.inputOutline),
                ),
                enabledBorder: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(12),
                  borderSide: const BorderSide(color: AppColors.inputOutline),
                ),
                focusedBorder: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(12),
                  borderSide: const BorderSide(color: AppColors.primaryBlueBright, width: 1.4),
                ),
              ),
            ),
          ),
          const SizedBox(width: 8),
          Container(
            decoration: BoxDecoration(
              gradient: const LinearGradient(
                colors: [AppColors.primaryBlue, AppColors.primaryBlueBright],
                begin: Alignment.topLeft,
                end: Alignment.bottomRight,
              ),
              borderRadius: BorderRadius.circular(14),
              boxShadow: const [
                BoxShadow(
                  color: AppColors.primaryBlueShadow,
                  blurRadius: 8,
                  offset: Offset(0, 3),
                ),
              ],
            ),
            child: ElevatedButton(
              onPressed: submitDisabled ? null : onSubmit,
              style: ElevatedButton.styleFrom(
                minimumSize: const Size(90, 44),
                backgroundColor: AppColors.transparent,
                foregroundColor: AppColors.white,
                shadowColor: AppColors.transparent,
                shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(14),
                ),
              ),
              child: submitting
                  ? const SizedBox(
                      width: 20,
                      height: 20,
                      child: CircularProgressIndicator(
                        strokeWidth: 2.2,
                        valueColor: AlwaysStoppedAnimation<Color>(AppColors.white),
                      ),
                    )
                  : Text(AppStrings.inputSend),
            ),
          ),
        ],
      ),
    );
  }
}
