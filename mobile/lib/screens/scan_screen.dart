import 'dart:io';
import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';
import '../services/import_service.dart';
import '../services/matching_service.dart';
import '../services/ocr_service.dart';
import '../services/qr_service.dart';
import 'result_screen.dart';

enum RecognizeMode { qr, ocr }

class ScanScreen extends StatefulWidget {
  const ScanScreen({super.key});

  @override
  State<ScanScreen> createState() => _ScanScreenState();
}

class _ScanScreenState extends State<ScanScreen> {
  bool _processing = false;
  String? _imagePath;
  RecognizeMode _mode = RecognizeMode.qr;

  Future<void> _pick(ImageSource source, RecognizeMode mode) async {
    final picker = ImagePicker();
    final picked = await picker.pickImage(source: source, maxWidth: 2048);
    if (picked == null) return;

    setState(() {
      _processing = true;
      _imagePath = picked.path;
      _mode = mode;
    });

    try {
      if (mode == RecognizeMode.qr) {
        await _handleQrImage(picked.path);
      } else {
        await _handleOcrImage(picked.path);
      }
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('识别失败: $e')),
      );
    } finally {
      if (mounted) setState(() => _processing = false);
    }
  }

  /// 扫码主路径：解码贴纸二维码 → 按 id 精确命中本地药库 → 结果页并自动播放。
  Future<void> _handleQrImage(String imagePath) async {
    final payload = await QrService.decodePayload(imagePath);
    if (!mounted) return;

    if (payload == null) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('未识别到 Lucky Doctor 二维码。\n请确认贴纸完整、拍清晰；若是普通药盒文字，可改用下方"文字识别"。'),
        ),
      );
      return; // 留在扫码页，可重新选择
    }

    final records = await ImportService.loadRecords();
    if (!mounted) return;

    final matched = QrService.findById(records, payload.id);
    if (matched != null) {
      // 命中本地记录：展示资料并自动播放语音
      Navigator.pushReplacement(
        context,
        MaterialPageRoute(
          builder: (_) => ResultScreen(
            matchedRecord: matched,
            ocrText: '',
            imagePath: imagePath,
            autoPlay: true,
          ),
        ),
      );
    } else {
      // 贴纸属于尚未导入的药：给出药名并引导导入数据包
      Navigator.pushReplacement(
        context,
        MaterialPageRoute(
          builder: (_) => ResultScreen(
            ocrText: '',
            imagePath: imagePath,
            expectedName: payload.medicineName,
          ),
        ),
      );
    }
  }

  /// OCR 兜底路径：无贴纸药盒，拍照 → 文字识别 → 关键词模糊匹配（行为保持原样）。
  Future<void> _handleOcrImage(String imagePath) async {
    final ocrText = await OcrService.recognizeFromFile(imagePath);
    final records = await ImportService.loadRecords();
    final matches = MatchingService.findMatch(ocrText, records);
    if (!mounted) return;

    if (matches.isNotEmpty && matches.first.score > 100) {
      Navigator.pushReplacement(
        context,
        MaterialPageRoute(
          builder: (_) => ResultScreen(
            matchedRecord: matches.first.record,
            ocrText: ocrText,
            imagePath: imagePath,
            allMatches: matches.take(5).toList(),
          ),
        ),
      );
    } else {
      Navigator.pushReplacement(
        context,
        MaterialPageRoute(
          builder: (_) => ResultScreen(
            ocrText: ocrText,
            imagePath: imagePath,
            allMatches: matches,
          ),
        ),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('识别药品')),
      body: _processing
          ? _buildProcessing()
          : _buildModePicker(),
    );
  }

  Widget _buildProcessing() {
    final isQr = _mode == RecognizeMode.qr;
    return Center(
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          if (_imagePath != null) ...[
            ClipRRect(
              borderRadius: BorderRadius.circular(12),
              child: Image.file(
                File(_imagePath!),
                height: 200,
                fit: BoxFit.cover,
              ),
            ),
            const SizedBox(height: 24),
          ],
          const CircularProgressIndicator(),
          const SizedBox(height: 16),
          Text(isQr ? '正在识别二维码...' : '正在识别文字...',
              style: const TextStyle(fontSize: 16)),
          const SizedBox(height: 8),
          Text(
            isQr ? '二维码解码 → 药品匹配' : 'OCR 文字识别 → 药品匹配',
            style: TextStyle(color: Colors.grey[500]),
          ),
          if (isQr) ...[
            const SizedBox(height: 4),
            Text(
              '首次识别需下载识别模型，稍慢属正常',
              style: TextStyle(fontSize: 12, color: Colors.grey[400]),
            ),
          ],
        ],
      ),
    );
  }

  Widget _buildModePicker() {
    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        // ---- 主入口：扫码 ----
        _buildModeCard(
          title: '扫码识别药盒贴纸',
          subtitle: '对准药盒上的 Lucky Doctor 二维码贴纸，拍清即可自动识别',
          icon: Icons.qr_code_scanner,
          highlight: true,
          onCamera: () => _pick(ImageSource.camera, RecognizeMode.qr),
          onGallery: () => _pick(ImageSource.gallery, RecognizeMode.qr),
        ),
        const SizedBox(height: 24),
        Center(
          child: Text('没有二维码贴纸？',
              style: TextStyle(color: Colors.grey[500], fontSize: 13)),
        ),
        const SizedBox(height: 12),
        // ---- 兜底入口：OCR ----
        _buildModeCard(
          title: '文字识别（兜底）',
          subtitle: '药盒没有贴二维码时，可拍药盒/说明书文字识别',
          icon: Icons.document_scanner_outlined,
          highlight: false,
          onCamera: () => _pick(ImageSource.camera, RecognizeMode.ocr),
          onGallery: () => _pick(ImageSource.gallery, RecognizeMode.ocr),
        ),
      ],
    );
  }

  Widget _buildModeCard({
    required String title,
    required String subtitle,
    required IconData icon,
    required bool highlight,
    required VoidCallback onCamera,
    required VoidCallback onGallery,
  }) {
    final scheme = Theme.of(context).colorScheme;
    final color = highlight ? scheme.primary : scheme.onSurfaceVariant;
    return Card(
      elevation: highlight ? 2 : 0,
      color: highlight
          ? scheme.primaryContainer.withValues(alpha: 0.35)
          : scheme.surfaceContainerLow,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
      child: Padding(
        padding: const EdgeInsets.all(20),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Icon(icon, size: 40, color: color),
                const SizedBox(width: 14),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(title,
                          style: TextStyle(
                              fontSize: 18,
                              fontWeight: FontWeight.bold,
                              color: color)),
                      const SizedBox(height: 4),
                      Text(subtitle,
                          style: TextStyle(
                              fontSize: 13, color: Colors.grey[600])),
                    ],
                  ),
                ),
              ],
            ),
            const SizedBox(height: 18),
            Row(
              children: [
                Expanded(
                  child: SizedBox(
                    height: 44,
                    child: ElevatedButton.icon(
                      onPressed: onCamera,
                      icon: const Icon(Icons.camera_alt),
                      label: const Text('拍照'),
                    ),
                  ),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: SizedBox(
                    height: 44,
                    child: OutlinedButton.icon(
                      onPressed: onGallery,
                      icon: const Icon(Icons.photo_library),
                      label: const Text('从相册选择'),
                    ),
                  ),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}
