import 'package:google_mlkit_barcode_scanning/google_mlkit_barcode_scanning.dart';
import '../models/medicine_record.dart';

/// Lucky Doctor 药盒贴纸 payload 解析 + 二维码解码服务。
///
/// Payload 规范必须与 skill 端 `scripts/create_sticker.py` 保持一致：
///
///     LD|1|<record_id>|<medicine_name>
///
/// `record_id` 与数据包 metadata.json 中的 `id` 完全一致，
/// App 导入该数据包后即可通过该 id 在本地药库中精确命中记录。
class QrPayload {
  static const String prefix = 'LD';
  static const String version = '1';
  static const String separator = '|';

  final String id;
  final String medicineName;

  const QrPayload({required this.id, required this.medicineName});

  @override
  String toString() => 'QrPayload(id: $id, medicineName: $medicineName)';
}

class QrService {
  static final BarcodeScanner _barcodeScanner = BarcodeScanner(
    formats: [BarcodeFormat.qrCode],
  );

  /// 从图片解码出所有候选二维码原始文本（非 Lucky Doctor 码也会返回，
  /// 是否合法由 [QrPayload] 解析决定）。
  static Future<List<String>> decodeRawValues(String imagePath) async {
    final inputImage = InputImage.fromFilePath(imagePath);
    final barcodes = await _barcodeScanner.processImage(inputImage);
    return barcodes
        .map((b) => b.rawValue)
        .whereType<String>()
        .toList();
  }

  /// 解析 payload 文本；非本应用二维码 / 版本不匹配 / id 缺失时返回 null。
  static QrPayload? parse(String raw) {
    final parts = raw.split(QrPayload.separator);
    if (parts.length < 4) return null;
    if (parts[0] != QrPayload.prefix) return null;
    if (parts[1] != QrPayload.version) return null;
    final id = parts[2].trim();
    if (id.isEmpty) return null;
    // 药名可能包含分隔符（生成端会清洗，这里仍然容错拼接）。
    final name = parts.sublist(3).join(QrPayload.separator);
    return QrPayload(id: id, medicineName: name);
  }

  /// 解码图片并返回第一个合法 Lucky Doctor payload；没有则返回 null。
  static Future<QrPayload?> decodePayload(String imagePath) async {
    final raws = await decodeRawValues(imagePath);
    for (final raw in raws) {
      final payload = parse(raw);
      if (payload != null) return payload;
    }
    return null;
  }

  /// 在本地药库中按记录 id 精确查找（返回首个匹配，药库规模小，O(n) 足够）。
  static MedicineRecord? findById(List<MedicineRecord> records, String id) {
    for (final record in records) {
      if (record.id == id) return record;
    }
    return null;
  }

  static void dispose() {
    _barcodeScanner.close();
  }
}
