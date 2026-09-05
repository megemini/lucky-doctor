import 'package:flutter/material.dart';
import 'package:file_picker/file_picker.dart';
import '../app_theme.dart';
import '../services/import_service.dart';

class ImportScreen extends StatefulWidget {
  const ImportScreen({super.key});

  @override
  State<ImportScreen> createState() => _ImportScreenState();
}

class _ImportScreenState extends State<ImportScreen> {
  bool _importing = false;
  String? _lastMessage;
  ImportResult? _lastResult;

  Future<void> _importPackage() async {
    final result = await FilePicker.platform.pickFiles(
      type: FileType.custom,
      allowedExtensions: ['zip'],
    );
    if (result == null || result.files.isEmpty) return;

    setState(() {
      _importing = true;
      _lastMessage = null;
    });

    try {
      final importResult = await ImportService.importPackage(result.files.single.path!);
      setState(() {
        _lastResult = importResult;
        _lastMessage = importResult.status == 'imported'
            ? '导入成功: ${importResult.medicineName}'
            : '已更新: ${importResult.medicineName}';
      });
    } catch (e) {
      setState(() {
        _lastMessage = '导入失败: $e';
      });
    } finally {
      setState(() => _importing = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('导入数据包')),
      body: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Card(
              child: Padding(
                padding: const EdgeInsets.all(24),
                child: Column(
                  children: [
                    Icon(
                      Icons.file_upload_outlined,
                      size: 64,
                      color: Colors.blue[200],
                    ),
                    const SizedBox(height: 16),
                    const Text(
                      '导入药品数据包',
                      style: TextStyle(fontSize: 22, fontWeight: FontWeight.bold),
                    ),
                    const SizedBox(height: 10),
                    Text(
                      '选择由 Lucky Doctor Skill 生成的 .zip 文件',
                      style: TextStyle(
                        fontSize: AppText.secondary,
                        height: AppText.secondaryHeight,
                        color: Colors.grey[700],
                      ),
                      textAlign: TextAlign.center,
                    ),
                    const SizedBox(height: 24),
                    SizedBox(
                      width: double.infinity,
                      child: ElevatedButton.icon(
                        onPressed: _importing ? null : _importPackage,
                        icon: _importing
                            ? const SizedBox(
                                width: 24,
                                height: 24,
                                child: CircularProgressIndicator(strokeWidth: 3),
                              )
                            : const Icon(Icons.file_upload),
                        label: Text(_importing ? '导入中...' : '选择文件'),
                      ),
                    ),
                  ],
                ),
              ),
            ),
            const SizedBox(height: 24),
            if (_lastMessage != null)
              Card(
                color: _lastResult?.status == 'imported' || _lastResult?.status == 'updated'
                    ? Colors.green[50]
                    : Colors.red[50],
                child: Padding(
                  padding: const EdgeInsets.all(16),
                  child: Row(
                    children: [
                      Icon(
                        _lastResult != null ? Icons.check_circle : Icons.error,
                        color: _lastResult != null ? Colors.green : Colors.red,
                      ),
                      const SizedBox(width: 12),
                      Expanded(child: Text(_lastMessage!)),
                    ],
                  ),
                ),
              ),
            const Spacer(),
            Text(
              '数据包格式: .zip (包含 metadata.json + audio.wav)',
              style: TextStyle(fontSize: AppText.caption, color: Colors.grey[600]),
              textAlign: TextAlign.center,
            ),
          ],
        ),
      ),
    );
  }
}
