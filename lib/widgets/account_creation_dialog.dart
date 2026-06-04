import 'package:flutter/material.dart';
import 'package:guess/resources/resources.dart';

/// 昵称输入对话框
class AccountCreationDialog extends StatefulWidget {
  const AccountCreationDialog({super.key, required this.onSubmit});

  final Future<bool> Function(String nickname) onSubmit;

  static Future<void> show(BuildContext context, {
    required Future<bool> Function(String nickname) onSubmit,
  }) {
    return showDialog(
      context: context,
      barrierDismissible: false,
      builder: (context) => AccountCreationDialog(onSubmit: onSubmit),
    );
  }

  @override
  State<AccountCreationDialog> createState() => _AccountCreationDialogState();
}

class _AccountCreationDialogState extends State<AccountCreationDialog> {
  final _controller = TextEditingController();
  bool _loading = false;
  String? _error;

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    final nickname = _controller.text.trim();
    if (nickname.isEmpty) {
      setState(() => _error = AppStrings.nicknameRequired);
      return;
    }
    if (nickname.length > 10) {
      setState(() => _error = AppStrings.nicknameTooLong);
      return;
    }

    setState(() {
      _loading = true;
      _error = null;
    });

    final success = await widget.onSubmit(nickname);
    if (success && mounted) {
      Navigator.of(context).pop();
    } else {
      setState(() {
        _loading = false;
        _error = AppStrings.createAccountFailed;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: Text(AppStrings.createAccountTitle),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
      content: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          TextField(
            controller: _controller,
            maxLength: 10,
            decoration: InputDecoration(
              hintText: AppStrings.nicknameHint,
              border: OutlineInputBorder(
                borderRadius: BorderRadius.circular(8),
              ),
              errorText: _error,
            ),
            autofocus: true,
            onSubmitted: (_) => _submit(),
          ),
        ],
      ),
      actions: [
        TextButton(
          onPressed: _loading ? null : _submit,
          child: _loading
              ? const SizedBox(
                  width: 16,
                  height: 16,
                  child: CircularProgressIndicator(strokeWidth: 2),
                )
              : Text(AppStrings.confirm),
        ),
      ],
    );
  }
}