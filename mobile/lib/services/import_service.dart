import 'dart:convert';
import 'dart:io';
import 'package:archive/archive.dart';
import 'package:path_provider/path_provider.dart';
import 'package:path/path.dart' as p;
import 'package:shared_preferences/shared_preferences.dart';
import '../models/medicine_record.dart';

class ImportService {
  static const _storageKey = 'medicine_records';
  static const _audioDir = 'audio';

  static Future<String> get _appDir async {
    final dir = await getApplicationDocumentsDirectory();
    return dir.path;
  }

  static Future<String> get _audioPath async {
    final dir = await _appDir;
    final audioDir = Directory(p.join(dir, _audioDir));
    if (!await audioDir.exists()) {
      await audioDir.create(recursive: true);
    }
    return audioDir.path;
  }

  static Future<List<MedicineRecord>> loadRecords() async {
    final prefs = await SharedPreferences.getInstance();
    final jsonStr = prefs.getString(_storageKey);
    if (jsonStr == null) return [];
    final List<dynamic> jsonList = json.decode(jsonStr);
    return jsonList.map((e) => MedicineRecord.fromJson(e)).toList();
  }

  static Future<void> _saveRecords(List<MedicineRecord> records) async {
    final prefs = await SharedPreferences.getInstance();
    final jsonStr = json.encode(records.map((e) => e.toJson()).toList());
    await prefs.setString(_storageKey, jsonStr);
  }

  static Future<ImportResult> importPackage(String zipPath) async {
    final bytes = await File(zipPath).readAsBytes();
    final archive = ZipDecoder().decodeBytes(bytes);

    // Extract metadata.json
    final metadataFile = archive.firstWhere(
      (f) => f.name == 'metadata.json',
      orElse: () => throw Exception('Invalid package: missing metadata.json'),
    );
    final metadataJson = json.decode(String.fromCharCodes(metadataFile.content as List<int>));

    // Extract audio.wav
    final audioFile = archive.firstWhere(
      (f) => f.name == 'audio.wav',
      orElse: () => throw Exception('Invalid package: missing audio.wav'),
    );

    final audioDirPath = await _audioPath;
    final audioOutPath = p.join(audioDirPath, '${metadataJson['id']}.wav');
    await File(audioOutPath).writeAsBytes(audioFile.content as List<int>);

    final record = MedicineRecord.fromJson({
      ...metadataJson,
      'audio_path': audioOutPath,
    });

    final records = await loadRecords();

    // Check duplicate by medicine_name
    final existingIndex = records.indexWhere(
      (r) => r.medicineName == record.medicineName,
    );

    if (existingIndex >= 0) {
      // Delete old audio file
      final oldRecord = records[existingIndex];
      if (oldRecord.audioPath.isNotEmpty) {
        final oldFile = File(oldRecord.audioPath);
        if (await oldFile.exists()) await oldFile.delete();
      }
      records[existingIndex] = record;
      await _saveRecords(records);
      return ImportResult(
        status: 'updated',
        medicineName: record.medicineName,
      );
    }

    records.add(record);
    await _saveRecords(records);
    return ImportResult(
      status: 'imported',
      medicineName: record.medicineName,
    );
  }

  static Future<void> deleteRecord(String id) async {
    final records = await loadRecords();
    final record = records.firstWhere((r) => r.id == id);
    if (record.audioPath.isNotEmpty) {
      final file = File(record.audioPath);
      if (await file.exists()) await file.delete();
    }
    records.removeWhere((r) => r.id == id);
    await _saveRecords(records);
  }
}

class ImportResult {
  final String status;
  final String medicineName;

  ImportResult({required this.status, required this.medicineName});
}
