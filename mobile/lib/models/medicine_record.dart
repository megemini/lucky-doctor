class MedicineRecord {
  final String id;
  final String medicineName;
  final String genericName;
  final String manufacturer;
  final List<String> keywords;
  final List<String> ingredients;
  final String category;
  final List<String> function;
  final String indications;
  final String contraindications;
  final String usageSummary;
  final String audioPath;
  final String createdAt;
  final String speaker;
  final String language;
  final int version;

  MedicineRecord({
    required this.id,
    required this.medicineName,
    required this.audioPath,
    this.genericName = '',
    this.manufacturer = '',
    this.keywords = const [],
    this.ingredients = const [],
    this.category = '',
    this.function = const [],
    this.indications = '',
    this.contraindications = '',
    this.usageSummary = '',
    this.createdAt = '',
    this.speaker = 'vivian',
    this.language = 'chinese',
    this.version = 1,
  });

  factory MedicineRecord.fromJson(Map<String, dynamic> json) {
    return MedicineRecord(
      id: json['id'] ?? '',
      medicineName: json['medicine_name'] ?? '',
      genericName: json['generic_name'] ?? '',
      manufacturer: json['manufacturer'] ?? '',
      keywords: List<String>.from(json['keywords'] ?? []),
      ingredients: List<String>.from(json['ingredients'] ?? []),
      category: json['category'] ?? '',
      function: List<String>.from(json['function'] ?? []),
      indications: json['indications'] ?? '',
      contraindications: json['contraindications'] ?? '',
      usageSummary: json['usage_summary'] ?? '',
      audioPath: json['audio_path'] ?? '',
      createdAt: json['created_at'] ?? '',
      speaker: json['speaker'] ?? 'vivian',
      language: json['language'] ?? 'chinese',
      version: json['version'] ?? 1,
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'id': id,
      'medicine_name': medicineName,
      'generic_name': genericName,
      'manufacturer': manufacturer,
      'keywords': keywords,
      'ingredients': ingredients,
      'category': category,
      'function': function,
      'indications': indications,
      'contraindications': contraindications,
      'usage_summary': usageSummary,
      'audio_path': audioPath,
      'created_at': createdAt,
      'speaker': speaker,
      'language': language,
      'version': version,
    };
  }

  MedicineRecord copyWith({String? audioPath}) {
    return MedicineRecord(
      id: id,
      medicineName: medicineName,
      genericName: genericName,
      manufacturer: manufacturer,
      keywords: keywords,
      ingredients: ingredients,
      category: category,
      function: function,
      indications: indications,
      contraindications: contraindications,
      usageSummary: usageSummary,
      audioPath: audioPath ?? this.audioPath,
      createdAt: createdAt,
      speaker: speaker,
      language: language,
      version: version,
    );
  }
}
