import 'dart:async';
import 'package:flutter/material.dart';
import '../app_theme.dart';
import '../models/medicine_record.dart';
import '../services/audio_service.dart';
import '../widgets/audio_player_widget.dart';
import 'import_screen.dart';

class ResultScreen extends StatefulWidget {
  /// 扫码命中的本地记录；null 表示未导入场景。
  final MedicineRecord? matchedRecord;

  /// 扫码未命中（本地尚未导入该药）时展示的药名。
  final String? expectedName;

  /// 命中后自动播放语音。
  final bool autoPlay;

  /// 未导入场景下"去导入"按钮回调；为空时默认跳到 [ImportScreen]。
  final VoidCallback? onImportRequested;

  const ResultScreen({
    super.key,
    this.matchedRecord,
    this.expectedName,
    this.autoPlay = false,
    this.onImportRequested,
  });

  @override
  State<ResultScreen> createState() => _ResultScreenState();
}

class _ResultScreenState extends State<ResultScreen> {
  final AudioService _audioService = AudioService();
  Timer? _autoPlayTimer;

  @override
  void initState() {
    super.initState();
    if (widget.autoPlay) {
      _scheduleAutoPlay();
    }
  }

  void _scheduleAutoPlay() {
    // 稍作延迟，等页面渲染完成、播放器订阅就绪后再自动播放。
    _autoPlayTimer = Timer(const Duration(milliseconds: 500), () async {
      if (!mounted) return;
      final record = widget.matchedRecord;
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
    final record = widget.matchedRecord;
    return Scaffold(
      appBar: AppBar(
        title: Text(record != null ? '识别结果' : '药品资料'),
      ),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(16),
        child: record != null ? _buildMatchedInfo(record) : _buildQrNotImported(),
      ),
    );
  }

  /// 命中场景：资料 + 自动播放语音。
  Widget _buildMatchedInfo(MedicineRecord record) {
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
                style: const TextStyle(
                  fontSize: AppText.headline,
                  fontWeight: FontWeight.bold,
                ),
              ),
            ),
          ],
        ),
        const SizedBox(height: 16),

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

        _buildInfoCard('适应症', record.indications),
        _buildInfoCard('用法用量', record.usageSummary),
        _buildInfoCard('禁忌', record.contraindications),
        _buildInfoCard('生产厂家', record.manufacturer),
      ],
    );
  }

  /// 未导入场景：药名 + 先去导入数据包。
  Widget _buildQrNotImported() {
    final name = (widget.expectedName ?? '').trim();
    return Column(
      children: [
        const SizedBox(height: 24),
        Card(
          child: Padding(
            padding: const EdgeInsets.all(24),
            child: Column(
              children: [
                Icon(Icons.qr_code_2, size: 56, color: Colors.orange[300]),
                const SizedBox(height: 12),
                Text(
                  name.isEmpty ? '未找到对应的药品资料' : '药盒贴纸已识别',
                  style: const TextStyle(fontSize: 22, fontWeight: FontWeight.bold),
                ),
                if (name.isNotEmpty) ...[
                  const SizedBox(height: 10),
                  Text(
                    '$name\n本地还没有这份药品的资料（语音随数据包保存）。',
                    textAlign: TextAlign.center,
                    style: TextStyle(
                      fontSize: AppText.secondary,
                      height: AppText.secondaryHeight,
                      color: Colors.grey[700],
                    ),
                  ),
                ],
                const SizedBox(height: 24),
                SizedBox(
                  width: double.infinity,
                  child: ElevatedButton.icon(
                    onPressed: () => (widget.onImportRequested ?? _defaultImport)(),
                    icon: const Icon(Icons.file_download),
                    label: const Text('去导入数据包'),
                  ),
                ),
                const SizedBox(height: 12),
                SizedBox(
                  width: double.infinity,
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

  Widget _buildInfoCard(String label, String value) {
    if (value.isEmpty) return const SizedBox.shrink();
    return Card(
      margin: const EdgeInsets.only(bottom: 12),
      child: Padding(
        padding: const EdgeInsets.fromLTRB(18, 16, 18, 18),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              label,
              style: TextStyle(
                fontSize: AppText.sectionLabel,
                fontWeight: FontWeight.w600,
                color: Colors.grey[700],
              ),
            ),
            const SizedBox(height: 8),
            Text(
              value,
              style: const TextStyle(
                fontSize: AppText.body,
                height: AppText.bodyHeight,
              ),
            ),
          ],
        ),
      ),
    );
  }
}
