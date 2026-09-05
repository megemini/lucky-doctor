import 'package:flutter/material.dart';
import '../app_theme.dart';
import 'scan_screen.dart';
import 'import_screen.dart';
import '../models/medicine_record.dart';
import '../services/import_service.dart';
import '../widgets/medicine_card.dart';

class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key});

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  List<MedicineRecord> _records = [];
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    _loadRecords();
  }

  Future<void> _loadRecords() async {
    setState(() => _loading = true);
    final records = await ImportService.loadRecords();
    setState(() {
      _records = records;
      _loading = false;
    });
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('幸运医生'),
        centerTitle: true,
        actions: [
          IconButton(
            icon: const Icon(Icons.file_upload),
            tooltip: '导入数据包',
            onPressed: () async {
              await Navigator.push(
                context,
                MaterialPageRoute(builder: (_) => const ImportScreen()),
              );
              _loadRecords();
            },
          ),
        ],
      ),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : _records.isEmpty
              ? _buildEmptyState()
              : _buildRecordList(),
      floatingActionButton: FloatingActionButton.extended(
        onPressed: () async {
          await Navigator.push(
            context,
            MaterialPageRoute(builder: (_) => const ScanScreen()),
          );
          _loadRecords();
        },
        icon: const Icon(Icons.qr_code_scanner),
        label: const Text('扫码识别'),
      ),
    );
  }

  Widget _buildEmptyState() {
    return Center(
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Icon(Icons.medication_outlined, size: 80, color: Colors.grey[400]),
          const SizedBox(height: 16),
          Text(
            '暂无药品数据',
            style: TextStyle(
              fontSize: 22,
              fontWeight: FontWeight.w600,
              color: Colors.grey[700],
            ),
          ),
          const SizedBox(height: 12),
          Text(
            '点击下方按钮，对准药盒上的\nLucky Doctor 二维码贴纸扫码；\n或通过右上角导入数据包',
            textAlign: TextAlign.center,
            style: TextStyle(
              fontSize: AppText.secondary,
              height: AppText.secondaryHeight,
              color: Colors.grey[700],
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildRecordList() {
    return RefreshIndicator(
      onRefresh: _loadRecords,
      child: ListView.builder(
        padding: const EdgeInsets.all(8),
        itemCount: _records.length,
        itemBuilder: (context, index) {
          return MedicineCard(
            record: _records[index],
            onTap: () => _showDetail(_records[index]),
            onDelete: () => _deleteRecord(_records[index]),
          );
        },
      ),
    );
  }

  void _showDetail(MedicineRecord record) {
    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      builder: (context) => DraggableScrollableSheet(
        initialChildSize: 0.7,
        minChildSize: 0.3,
        maxChildSize: 0.95,
        expand: false,
        builder: (context, scrollController) {
          return SingleChildScrollView(
            controller: scrollController,
            padding: const EdgeInsets.all(20),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Center(
                  child: Container(
                    width: 40,
                    height: 4,
                    margin: const EdgeInsets.only(bottom: 20),
                    decoration: BoxDecoration(
                      color: Colors.grey[300],
                      borderRadius: BorderRadius.circular(2),
                    ),
                  ),
                ),
                Text(
                  record.medicineName,
                  style: const TextStyle(
                    fontSize: AppText.headline,
                    fontWeight: FontWeight.bold,
                  ),
                ),
                const SizedBox(height: 20),
                _buildInfoTile('适应症', record.indications),
                _buildInfoTile('用法用量', record.usageSummary),
                _buildInfoTile('禁忌', record.contraindications),
                _buildInfoTile('生产厂家', record.manufacturer),
                _buildInfoTile('有效成分', record.ingredients.join('、')),
                _buildInfoTile('分类', record.category),
                _buildInfoTile('功效', record.function.join('、')),
                const SizedBox(height: 16),
                Text(
                  '导入时间: ${record.createdAt}',
                  style: TextStyle(
                    fontSize: AppText.caption,
                    color: Colors.grey[700],
                  ),
                ),
              ],
            ),
          );
        },
      ),
    );
  }

  Widget _buildInfoTile(String label, String value) {
    if (value.isEmpty) return const SizedBox.shrink();
    return Padding(
      padding: const EdgeInsets.only(bottom: 16),
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
          const SizedBox(height: 6),
          Text(
            value,
            style: const TextStyle(fontSize: AppText.body, height: AppText.bodyHeight),
          ),
        ],
      ),
    );
  }

  Future<void> _deleteRecord(MedicineRecord record) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('删除确认'),
        content: Text('确定要删除 "${record.medicineName}" 吗？'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('取消')),
          TextButton(
            onPressed: () => Navigator.pop(context, true),
            child: const Text('删除', style: TextStyle(color: Colors.red)),
          ),
        ],
      ),
    );
    if (confirmed == true) {
      await ImportService.deleteRecord(record.id);
      _loadRecords();
    }
  }
}
