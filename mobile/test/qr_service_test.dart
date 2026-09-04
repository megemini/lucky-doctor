import 'package:flutter_test/flutter_test.dart';
import 'package:lucky_doctor/models/medicine_record.dart';
import 'package:lucky_doctor/services/qr_service.dart';

void main() {
  group('QrPayload.parse', () {
    test('parses a valid Lucky Doctor payload', () {
      const raw = 'LD|1|3f2c9a1e-b7d2-4c6e-9a10-8d5e2f1a4b3c|阿莫西林胶囊';
      final p = QrService.parse(raw);
      expect(p, isNotNull);
      expect(p!.id, '3f2c9a1e-b7d2-4c6e-9a10-8d5e2f1a4b3c');
      expect(p.medicineName, '阿莫西林胶囊');
    });

    test('allows an empty medicine name (id-only payload)', () {
      const raw = 'LD|1|3f2c9a1e-b7d2-4c6e-9a10-8d5e2f1a4b3c|';
      final p = QrService.parse(raw);
      expect(p, isNotNull);
      expect(p!.medicineName, isEmpty);
    });

    test('rejects a foreign QR code (different prefix)', () {
      expect(QrService.parse('https://example.com/foo'), isNull);
      expect(QrService.parse('WE|1|some-id|药'), isNull);
    });

    test('rejects an unsupported payload version', () {
      expect(QrService.parse('LD|2|some-id|药'), isNull);
    });

    test('rejects a malformed payload (missing id or fields)', () {
      expect(QrService.parse('LD|1||药'), isNull); // empty id
      expect(QrService.parse('LD|1'), isNull); // too few fields
      expect(QrService.parse(''), isNull);
      expect(QrService.parse('| | |'), isNull);
    });

    test('keeps a medicine name that accidentally contains a separator', () {
      const raw = 'LD|1|id-123|A|B';
      final p = QrService.parse(raw);
      expect(p, isNotNull);
      expect(p!.id, 'id-123');
      expect(p.medicineName, 'A|B');
    });
  });

  group('QrService.findById', () {
    final records = <MedicineRecord>[
      MedicineRecord(
        id: '3f2c9a1e-b7d2-4c6e-9a10-8d5e2f1a4b3c',
        medicineName: '阿莫西林胶囊',
        audioPath: '/audio/1.wav',
      ),
      MedicineRecord(
        id: 'aabbccdd-0000-0000-0000-000000000001',
        medicineName: '感冒灵颗粒',
        audioPath: '',
      ),
    ];

    test('returns the matching record by exact id', () {
      final hit = QrService.findById(records, '3f2c9a1e-b7d2-4c6e-9a10-8d5e2f1a4b3c');
      expect(hit?.medicineName, '阿莫西林胶囊');
    });

    test('returns null when no record carries the scanned id', () {
      expect(QrService.findById(records, 'not-exist-id'), isNull);
      expect(QrService.findById(records, '3f2c9a1e-b7d2-4c6e-9a10-8d5e2f1a4b3c '), isNull);
    });
  });
}
