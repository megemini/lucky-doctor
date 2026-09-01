import '../models/medicine_record.dart';

class MatchResult {
  final MedicineRecord record;
  final double score;

  MatchResult({required this.record, required this.score});
}

class MatchingService {
  static int _levenshtein(String a, String b) {
    if (a.isEmpty) return b.length;
    if (b.isEmpty) return a.length;

    final la = a.length;
    final lb = b.length;
    final dp = List.generate(la + 1, (i) => List.filled(lb + 1, 0));

    for (int i = 0; i <= la; i++) dp[i][0] = i;
    for (int j = 0; j <= lb; j++) dp[0][j] = j;

    for (int i = 1; i <= la; i++) {
      for (int j = 1; j <= lb; j++) {
        final cost = a[i - 1] == b[j - 1] ? 0 : 1;
        dp[i][j] = [
          dp[i - 1][j] + 1,
          dp[i][j - 1] + 1,
          dp[i - 1][j - 1] + cost,
        ].reduce((a, b) => a < b ? a : b);
      }
    }
    return dp[la][lb];
  }

  static double _fuzzyMatch(String text, String keyword) {
    if (keyword.isEmpty) return 0.0;
    final textLower = text.toLowerCase();
    final kwLower = keyword.toLowerCase();

    if (textLower.contains(kwLower)) return 1.0;

    final windowSize = (kwLower.length * 2.5).toInt();
    double bestSimilarity = 0.0;

    for (int i = 0; i <= textLower.length - kwLower.length ~/ 2; i++) {
      final end = (i + windowSize).clamp(0, textLower.length);
      final sub = textLower.substring(i, end);
      final dist = _levenshtein(sub, kwLower);
      final similarity = 1.0 - dist / kwLower.length;
      if (similarity > bestSimilarity) {
        bestSimilarity = similarity;
      }
    }
    return bestSimilarity;
  }

  static List<MatchResult> findMatch(String ocrText, List<MedicineRecord> records) {
    final results = <MatchResult>[];

    for (final record in records) {
      double score = 0;

      // Exact name match (highest weight)
      if (ocrText.contains(record.medicineName)) {
        score += 200;
      }

      // Keyword matching
      for (final keyword in record.keywords) {
        if (ocrText.contains(keyword)) {
          // Longer keywords get more weight
          score += 100 + keyword.length * 10;
        } else {
          final similarity = _fuzzyMatch(ocrText, keyword);
          if (similarity > 0.6) {
            score += similarity * 80;
          }
        }
      }

      if (score > 0) {
        results.add(MatchResult(record: record, score: score));
      }
    }

    results.sort((a, b) => b.score.compareTo(a.score));
    return results;
  }
}
