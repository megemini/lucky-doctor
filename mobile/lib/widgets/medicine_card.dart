import 'package:flutter/material.dart';
import '../models/medicine_record.dart';

class MedicineCard extends StatelessWidget {
  final MedicineRecord record;
  final VoidCallback onTap;
  final VoidCallback onDelete;

  const MedicineCard({
    super.key,
    required this.record,
    required this.onTap,
    required this.onDelete,
  });

  @override
  Widget build(BuildContext context) {
    final subtitle = [record.genericName, record.category]
        .where((s) => s.isNotEmpty)
        .join(' · ');
    return Card(
      margin: const EdgeInsets.symmetric(vertical: 4),
      child: ListTile(
        leading: CircleAvatar(
          backgroundColor: Theme.of(context).colorScheme.primaryContainer,
          child: Icon(
            Icons.medication,
            color: Theme.of(context).colorScheme.primary,
          ),
        ),
        title: Text(
          record.medicineName,
          style: const TextStyle(fontWeight: FontWeight.bold),
        ),
        subtitle: Text(
          subtitle.isEmpty ? '点按查看详情' : subtitle,
          maxLines: 1,
          overflow: TextOverflow.ellipsis,
        ),
        trailing: PopupMenuButton(
          itemBuilder: (context) => [
            const PopupMenuItem(value: 'delete', child: Text('删除')),
          ],
          onSelected: (v) {
            if (v == 'delete') onDelete();
          },
        ),
        onTap: onTap,
      ),
    );
  }
}
