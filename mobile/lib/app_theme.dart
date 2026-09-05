/// 适老主题：整包统一的大字号与更大的触控目标。
///
/// 本应用主要使用者为 60+ 老人，正文阅读字号不得低于 17（逻辑像素）。
/// 页面业务代码请复用 [AppText] 字号常量，不要在 UI 中再写死小于
/// [AppText.caption] 的 fontSize，以保证全 App 口径一致。
library;

import 'package:flutter/material.dart';

/// 适老字号规范（单位：逻辑像素，建议全 App 统一使用）。
abstract final class AppText {
  /// 药名 / 页面主标题
  static const double headline = 26;

  /// AppBar / 导航栏标题
  static const double appBar = 24;

  /// 分组小标题（如“用法用量”“适应症”）
  static const double sectionLabel = 17;

  /// 正文内容
  static const double body = 19;

  /// 次级说明（引导、未导入提示等）
  static const double secondary = 17;

  /// 极次要信息（播放时间、导入时间、页脚）
  static const double caption = 15;

  /// 按钮 / 可点文字
  static const double button = 18;

  /// 正文行高（中文长文本按 1.6 起步，避免行距过挤）
  static const double bodyHeight = 1.6;

  /// 说明文字行高
  static const double secondaryHeight = 1.5;
}

/// 构建适老主题。亮 / 暗模式共用同一套字号规范。
ThemeData buildAppTheme(Brightness brightness) {
  final scheme = ColorScheme.fromSeed(
    seedColor: Colors.teal,
    brightness: brightness,
  );
  final Color onSurface = scheme.onSurface;
  // 次要文字颜色：亮色用深灰、暗色用浅灰，保证弱光/低龄用户可读。
  final Color muted = brightness == Brightness.light
      ? const Color(0xFF5F6368)
      : const Color(0xFFB6BAC1);

  return ThemeData(
    colorScheme: scheme,
    useMaterial3: true,
    iconTheme: IconThemeData(size: 28, color: onSurface),
    appBarTheme: AppBarTheme(
      centerTitle: true,
      toolbarHeight: 64,
      backgroundColor: scheme.surface,
      foregroundColor: onSurface,
      titleTextStyle: TextStyle(
        fontSize: AppText.appBar,
        fontWeight: FontWeight.w700,
        color: onSurface,
      ),
    ),
    textTheme: TextTheme(
      // 标题层级
      titleLarge: TextStyle(
        fontSize: AppText.appBar,
        fontWeight: FontWeight.w700,
        color: onSurface,
      ),
      titleMedium: TextStyle(
        fontSize: 22,
        fontWeight: FontWeight.w600,
        color: onSurface,
      ),
      // 正文 / 列表（ListTile 标题与副标题走这里）
      bodyLarge: TextStyle(
        fontSize: AppText.body,
        height: AppText.bodyHeight,
        color: onSurface,
      ),
      bodyMedium: TextStyle(
        fontSize: AppText.secondary,
        height: AppText.secondaryHeight,
        color: onSurface,
      ),
      bodySmall: TextStyle(
        fontSize: AppText.caption,
        height: AppText.secondaryHeight,
        color: muted,
      ),
      // 控件 / 按钮文字
      labelLarge: TextStyle(
        fontSize: AppText.button,
        fontWeight: FontWeight.w600,
        color: onSurface,
      ),
      labelMedium: TextStyle(fontSize: 16, color: onSurface),
      labelSmall: TextStyle(fontSize: AppText.caption, color: muted),
    ),
    // 更大、更容易按中的按钮
    elevatedButtonTheme: ElevatedButtonThemeData(
      style: ElevatedButton.styleFrom(
        minimumSize: const Size(64, 52),
        textStyle: const TextStyle(
          fontSize: AppText.button,
          fontWeight: FontWeight.w600,
        ),
      ),
    ),
    textButtonTheme: TextButtonThemeData(
      style: TextButton.styleFrom(
        minimumSize: const Size(64, 48),
        textStyle: const TextStyle(fontSize: AppText.button),
      ),
    ),
  );
}
