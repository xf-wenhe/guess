class AppAssets {
  const AppAssets._();

  static const puzzles = 'assets/puzzles.json';
  static const successAnimation = 'assets/images/feedback/success.gif';
  static const failureAnimation = 'assets/images/feedback/fail.gif';

  static const embeddingScript = 'embedding_server.py';
  static const embeddingRequirements = 'requirements.txt';

  static const manualSimilarityOverrides =
      'data/manual_similarity_overrides.json';

  static const semanticCalibrationCandidates = <String>[
    'data/semantic_calibration_v27_semreal_anchor.json',
    'data/semantic_calibration_v21_refine.json',
    'data/semantic_calibration_v19.json',
    'data/semantic_calibration_v18_v3.json',
    'data/semantic_calibration_v18.json',
  ];
}
