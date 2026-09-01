import 'dart:io';
import 'package:google_mlkit_text_recognition/google_mlkit_text_recognition.dart';

class OcrService {
  static final _textRecognizer = TextRecognizer(script: TextRecognitionScript.chinese);

  static Future<String> recognizeFromFile(String imagePath) async {
    final inputImage = InputImage.fromFilePath(imagePath);
    final recognizedText = await _textRecognizer.processImage(inputImage);
    return recognizedText.text;
  }

  static void dispose() {
    _textRecognizer.close();
  }
}
