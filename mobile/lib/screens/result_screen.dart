import 'dart:async';
import 'dart:io';
import 'package:flutter/material.dart';
import '../models/medicine_record.dart';
import '../services/audio_service.dart';
import '../services/matching_service.dart';
import '../widgets/audio_player_widget.dart';
import 'import_screen.dart';

class ResultScreen extends StatefulWidget {
  final MedicineRecord? matchedRecord;

  /// OCR 路径的原文；扫码路径传空（空时隐藏"查看OCR"切换与原文预览）。
  final String ocrText;

  /// 用户拍摄/选择的原始图片。
  final String imagePath;

  /// OCR 模糊匹配的候选列表。
  final List<MatchResult> allMatches;

  /// 扫码命中后自动播放语音（默认 false，OCR 手动播放路径不受影响）。
  final bool autoPlay;

  /// 扫码未命中（本地尚未导入该药）时展示的药名；null 表示非扫码场景。
  final String? expectedName;

  /// 未导入场景下"去导入"按钮回调；为空时默认跳到 [ImportScreen]。
  final VoidCallback? onImportRequested;

  const ResultScreen({
    super.key,
    this.matchedRecord,
    required this.ocrText,
    required this.imagePath,
    this.allMatches = const [],
    this.autoPlay = false,
    this.expectedName,
    this.onImportRequested,
  });

  @override
  State<ResultScreen> createState() => _ResultScreenState();
}

class _ResultScreenState extends State<ResultScreen> {
  final AudioService _audioService = AudioService();
  MedicineRecord? _selectedRecord;
  bool _showOcrText = false;
  Timer? _autoPlayTimer;

  /// 扫码到了尚未导入的药品（非 OCR 未匹配场景）。
  bool get _qrNotImported => widget.expectedName != null && _selectedRecord == null;

  @override
  void initState() {
    super.initState();
    _selectedRecord = widget.matchedRecord;
    if (widget.autoPlay) {
      _scheduleAutoPlay();
    }
  }

  void _scheduleAutoPlay() {
    // 稍作延迟，等页面渲染完成、播放器订阅就绪后再自动播放。
    _autoPlayTimer = Timer(const Duration(milliseconds: 500), () async {
      if (!mounted) return;
      final record = _selectedRecord;
      if (record == null || record.audioPath.isEmpty) return;
      try {
        await _audioService.play(record.audioPath);
      } catch (e) {
        if (!mounted) return;
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('语音播放失败，音频文件可能缺失，请重新导入数据包')),
        );
      }
    });
  }

  @override
  void dispose() {
    _autoPlayTimer?.cancel();
    _audioService.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Text(_qrNotImported ? '药品资料' : '识别结果'),
        actions: [
          if (widget.ocrText.isNotEmpty)
            IconButton(
              icon: Icon(_showOcrText ? Icons.image : Icons.text_snippet),
              tooltip: _showOcrText ? '查看图片' : '查看OCR文字',
              onPressed: () => setState(() => _showOcrText = !_showOcrText),
            ),
        ],
      ),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            if (_qrNotImported)
              _buildQrNotImported()
            else ...[
              _buildImageOrOcr(),
              const SizedBox(height: 20),
              if (_selectedRecord != null)
                _buildMatchedInfo()
              else
                _buildNoMatch(),
              if (widget.allMatches.length > 1) ...[
                const SizedBox(height: 20),
                const Text(
                  '其他可能匹配:',
                  style: TextStyle(fontWeight: FontWeight.bold),
                ),
                const SizedBox(height: 8),
                ...widget.allMatches.skip(1).take(3).map(
                  (m) => Card(
                    child: ListTile(
                      title: Text(m.record.medicineName),
                      subtitle: Text('匹配度: ${m.score.toStringAsFixed(0)}'),
                      trailing: const Icon(Icons.chevron_right),
                      onTap: () => setState(() => _selectedRecord = m.record),
                    ),
                  ),
                ),
              ],
            ],
          ],
        ),
      ),
    );
  }

  /// 扫码未命中引导：药名 + 先去导入数据包。
  Widget _buildQrNotImported() {
    final name = (widget.expectedName ?? '').trim();
    return Column(
      children: [
        ClipRRect(
          borderRadius: BorderRadius.circular(12),
          child: Image.file(
            File(widget.imagePath),
            width: double.infinity,
            fit: BoxFit.contain,
            height: 160,
          ),
        ),
        const SizedBox(height: 20),
        Card(
          child: Padding(
            padding: const EdgeInsets.all(20),
            child: Column(
              children: [
                Icon(Icons.qr_code_2, size: 56, color: Colors.orange[300]),
                const SizedBox(height: 12),
                Text(
                  name.isEmpty ? '未找到对应的药品资料' : '药盒贴纸已识别',
                  style: const TextStyle(fontSize: 18, fontWeight: FontWeight.bold),
                ),
                if (name.isNotEmpty) ...[
                  const SizedBox(height: 8),
                  Text(
                    '$name\n本地还没有这份药品的资料（语音随数据包保存）。',
                    textAlign: TextAlign.center,
                    style: TextStyle(color: Colors.grey[600], height: 1.5),
                  ),
                ],
                const SizedBox(height: 20),
                SizedBox(
                  width: double.infinity,
                  height: 48,
                  child: ElevatedButton.icon(
                    onPressed: () => (widget.onImportRequested ?? _defaultImport)(),
                    icon: const Icon(Icons.file_download),
                    label: const Text('去导入数据包', style: TextStyle(fontSize: 16)),
                  ),
                ),
                const SizedBox(height: 8),
                SizedBox(
                  width: double.infinity,
                  height: 44,
                  child: TextButton(
                    onPressed: () => Navigator.of(context).maybePop(),
                    child: const Text('稍后再导入，返回首页'),
                  ),
                ),
              ],
            ),
          ),
        ),
      ],
    );
  }

  Future<void> _defaultImport() async {
    await Navigator.of(context).push(
      MaterialPageRoute(builder: (_) => const ImportScreen()),
    );
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(content: Text('数据包导入后，回到首页再次扫码即可查看资料并自动播放语音')),
    );
  }

  Widget _buildImageOrOcr() {
    if (widget.ocrText.isNotEmpty && _showOcrText) {
      return Container(
        width: double.infinity,
        padding: const EdgeInsets.all(12),
        decoration: BoxDecoration(
          color: Colors.grey[100],
          borderRadius: BorderRadius.circular(8),
        ),
        child: SelectableText(
          widget.ocrText,
          style: const TextStyle(fontSize: 13, fontFamily: 'monospace'),
        ),
      );
    }
    return ClipRRect(
      borderRadius: BorderRadius.circular(12),
      child: Image.file(
        File(widget.imagePath),
        width: double.infinity,
        fit: BoxFit.contain,
        height: 200,
      ),
    );
  }

  Widget _buildMatchedInfo() {
    final record = _selectedRecord!;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            const Icon(Icons.check_circle, color: Colors.green),
            const SizedBox(width: 8),
            Expanded(
              child: Text(
                record.medicineName,
                style: const TextStyle(fontSize: 22, fontWeight: FontWeight.bold),
              ),
            ),
          ],
        ),
        const SizedBox(height: 16),

        // Audio player
        if (record.audioPath.isNotEmpty)
          Card(
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: AudioPlayerWidget(
                audioService: _audioService,
                audioPath: record.audioPath,
              ),
            ),
          ),

        const SizedBox(height: 16),

        // Info cards
        _buildInfoCard('适应症', record.indications),
        _buildInfoCard('用法用量', record.usageSummary),
        _buildInfoCard('禁忌', record.contraindications),
        _buildInfoCard('生产厂家', record.manufacturer),
      ],
    );
  }

  Widget _buildNoMatch() {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(20),
        child: Column(
          children: [
            Icon(Icons.search_off, size: 48, color: Colors.orange[300]),
            const SizedBox(height: 12),
            const Text(
              '未找到匹配的药品',
              style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold),
            ),
            const SizedBox(height: 8),
            Text(
              '可尝试：药盒贴纸用"扫码识别"更准确，\n或在主页面右上角导入数据包后重试',
              textAlign: TextAlign.center,
              style: TextStyle(color: Colors.grey[500]),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildInfoCard(String label, String value) {
    if (value.isEmpty) return const SizedBox.shrink();
    return Card(
      margin: const EdgeInsets.only(bottom: 8),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(label, style: TextStyle(fontSize: 13, color: Colors.grey[500])),
            const SizedBox(height: 6),
            Text(value, style: const TextStyle(fontSize: 15)),
          ],
        ),
      ),
    );
  }
}
