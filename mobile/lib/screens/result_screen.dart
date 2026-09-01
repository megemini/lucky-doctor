import 'dart:io';
import 'package:flutter/material.dart';
import '../models/medicine_record.dart';
import '../services/matching_service.dart';
import '../services/audio_service.dart';
import '../widgets/audio_player_widget.dart';

class ResultScreen extends StatefulWidget {
  final MedicineRecord? matchedRecord;
  final String ocrText;
  final String imagePath;
  final List<MatchResult> allMatches;

  const ResultScreen({
    super.key,
    this.matchedRecord,
    required this.ocrText,
    required this.imagePath,
    this.allMatches = const [],
  });

  @override
  State<ResultScreen> createState() => _ResultScreenState();
}

class _ResultScreenState extends State<ResultScreen> {
  final AudioService _audioService = AudioService();
  MedicineRecord? _selectedRecord;
  bool _showOcrText = false;

  @override
  void initState() {
    super.initState();
    _selectedRecord = widget.matchedRecord;
  }

  @override
  void dispose() {
    _audioService.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('识别结果'),
        actions: [
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
            // Image / OCR toggle
            if (_showOcrText)
              Container(
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
              )
            else
              ClipRRect(
                borderRadius: BorderRadius.circular(12),
                child: Image.file(
                  File(widget.imagePath),
                  width: double.infinity,
                  fit: BoxFit.contain,
                  height: 200,
                ),
              ),

            const SizedBox(height: 20),

            // Match result
            if (_selectedRecord != null) ...[
              _buildMatchedInfo(),
            ] else ...[
              _buildNoMatch(),
            ],

            // Other matches
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
        ),
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
              '请通过主页面右上角导入\n由 Lucky Doctor Skill 生成的数据包',
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
