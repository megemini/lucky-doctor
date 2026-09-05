import 'dart:io';
import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';
import '../services/import_service.dart';
import '../services/qr_service.dart';
import 'result_screen.dart';

class ScanScreen extends StatefulWidget {
  const ScanScreen({super.key});

  @override
  State<ScanScreen> createState() => _ScanScreenState();
}

class _ScanScreenState extends State<ScanScreen> {
  bool _processing = false;
  String? _imagePath;

  Future<void> _pick(ImageSource source) async {
    final picker = ImagePicker();
    final picked = await picker.pickImage(source: source, maxWidth: 2048);
    if (picked == null) return;

    setState(() {
      _processing = true;
      _imagePath = picked.path;
    });

    try {
      await _handleQrImage(picked.path);
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('识别失败: $e')),
      );
    } finally {
      if (mounted) setState(() => _processing = false);
    }
  }

  /// 扫码路径：解码贴纸二维码 → 按 payload 中的记录 id 精确命中本地药库。
  Future<void> _handleQrImage(String imagePath) async {
    final payload = await QrService.decodePayload(imagePath);
    if (!mounted) return;

    if (payload == null) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('未识别到 Lucky Doctor 二维码。\n请对准完整清晰的贴纸重拍；无贴纸可联系照护者导入数据包。'),
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
            expectedName: payload.medicineName,
          ),
        ),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('扫码识别')),
      body: _processing ? _buildProcessing() : _buildScanEntry(),
    );
  }

  Widget _buildProcessing() {
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
          const Text('正在识别二维码...', style: TextStyle(fontSize: 16)),
          const SizedBox(height: 8),
          Text(
            '二维码解码 → 按记录号精确匹配药品',
            style: TextStyle(color: Colors.grey[500]),
          ),
          const SizedBox(height: 4),
          Text(
            '首次识别需下载识别模型，稍慢属正常',
            style: TextStyle(fontSize: 12, color: Colors.grey[400]),
          ),
        ],
      ),
    );
  }

  Widget _buildScanEntry() {
    final scheme = Theme.of(context).colorScheme;
    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        const SizedBox(height: 8),
        Card(
          elevation: 2,
          color: scheme.primaryContainer.withValues(alpha: 0.35),
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
          child: Padding(
            padding: const EdgeInsets.all(24),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Icon(Icons.qr_code_scanner, size: 40, color: scheme.primary),
                    const SizedBox(width: 14),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text('扫描药盒贴纸',
                              style: TextStyle(
                                  fontSize: 18,
                                  fontWeight: FontWeight.bold,
                                  color: scheme.primary)),
                          const SizedBox(height: 4),
                          Text(
                            '对准药盒上的 Lucky Doctor 二维码贴纸，拍清即可',
                            style: TextStyle(fontSize: 13, color: Colors.grey[600]),
                          ),
                        ],
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 20),
                Row(
                  children: [
                    Expanded(
                      child: SizedBox(
                        height: 48,
                        child: ElevatedButton.icon(
                          onPressed: () => _pick(ImageSource.camera),
                          icon: const Icon(Icons.camera_alt, size: 22),
                          label: const Text('拍照扫码'),
                        ),
                      ),
                    ),
                    const SizedBox(width: 12),
                    Expanded(
                      child: SizedBox(
                        height: 48,
                        child: OutlinedButton.icon(
                          onPressed: () => _pick(ImageSource.gallery),
                          icon: const Icon(Icons.photo_library, size: 22),
                          label: const Text('相册扫码'),
                        ),
                      ),
                    ),
                  ],
                ),
              ],
            ),
          ),
        ),
        const SizedBox(height: 24),
        Card(
          color: scheme.surfaceContainerLow,
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
          child: Padding(
            padding: const EdgeInsets.all(16),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Icon(Icons.info_outline, size: 20, color: Colors.grey[500]),
                const SizedBox(width: 12),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        '没有贴纸怎么办？',
                        style: TextStyle(
                            fontSize: 14, fontWeight: FontWeight.bold),
                      ),
                      const SizedBox(height: 6),
                      Text(
                        '扫码读取的是确定的"记录号"，不会认错药。\n'
                        '贴纸由照护者整理药品资料后打印，请先通过右上角导入数据包。',
                        style: TextStyle(
                            fontSize: 13,
                            color: Colors.grey[600],
                            height: 1.6),
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),
        ),
      ],
    );
  }
}
