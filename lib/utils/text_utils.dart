bool isAllChinese(String text) {
  return RegExp(r'^[\u4e00-\u9fff]+$').hasMatch(text);
}
