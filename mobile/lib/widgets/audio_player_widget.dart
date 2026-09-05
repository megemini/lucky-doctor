import 'dart:async';
import 'package:flutter/material.dart';
import 'package:just_audio/just_audio.dart';
import '../app_theme.dart';
import '../services/audio_service.dart';

class AudioPlayerWidget extends StatefulWidget {
  final AudioService audioService;
  final String audioPath;

  const AudioPlayerWidget({
    super.key,
    required this.audioService,
    required this.audioPath,
  });

  @override
  State<AudioPlayerWidget> createState() => _AudioPlayerWidgetState();
}

class _AudioPlayerWidgetState extends State<AudioPlayerWidget> {
  StreamSubscription<Duration>? _posSub;
  StreamSubscription<PlayerState>? _stateSub;
  bool _playing = false;
  Duration _position = Duration.zero;
  Duration _duration = Duration.zero;

  @override
  void initState() {
    super.initState();
    _posSub = widget.audioService.positionStream.listen((pos) {
      if (mounted) setState(() => _position = pos);
    });
    _stateSub = widget.audioService.playerStateStream.listen((state) {
      if (mounted) {
        setState(() {
          _playing = state.playing;
          _duration = widget.audioService.duration;
        });
      }
    });
  }

  @override
  void dispose() {
    _posSub?.cancel();
    _stateSub?.cancel();
    super.dispose();
  }

  String _formatDuration(Duration d) {
    final min = d.inMinutes;
    final sec = d.inSeconds % 60;
    return '$min:${sec.toString().padLeft(2, '0')}';
  }

  @override
  Widget build(BuildContext context) {
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        Row(
          children: [
            IconButton(
              iconSize: 64,
              icon: Icon(
                _playing ? Icons.pause_circle_filled : Icons.play_circle_filled,
                color: Theme.of(context).colorScheme.primary,
              ),
              onPressed: () async {
                if (_playing) {
                  await widget.audioService.pause();
                } else {
                  await widget.audioService.play(widget.audioPath);
                }
              },
            ),
            Expanded(
              child: SliderTheme(
                data: SliderTheme.of(context).copyWith(
                  trackHeight: 6,
                  thumbShape: const RoundSliderThumbShape(enabledThumbRadius: 14),
                ),
                child: Slider(
                  value: _duration.inMilliseconds > 0
                      ? _position.inMilliseconds / _duration.inMilliseconds
                      : 0.0,
                  onChanged: (v) {
                    widget.audioService.seek(
                      Duration(milliseconds: (v * _duration.inMilliseconds).toInt()),
                    );
                  },
                ),
              ),
            ),
          ],
        ),
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 48),
          child: Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Text(_formatDuration(_position),
                  style: TextStyle(fontSize: AppText.caption, color: Colors.grey[700])),
              Text(_formatDuration(_duration),
                  style: TextStyle(fontSize: AppText.caption, color: Colors.grey[700])),
            ],
          ),
        ),
      ],
    );
  }
}
