"""Small diagnostic using the unchanged deployed provider, not a benchmark."""
import base64
import csv
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from app.providers.trained import TrainedProvider
from app.schemas import LiveInput

metadata = Path('/Users/liu/Desktop/FYP-In-Cabin-Driver-Assessment-/eda_outputs/processed/vision/vision_metadata_with_split.csv')
provider = TrainedProvider()
samples = []
with metadata.open() as stream:
    rows = list(csv.DictReader(stream))
for class_id in provider.labels:
    index = provider.labels.index(class_id)
    selected = [r for r in rows if r['split'] == 'test' and r['class_id'] == f'c{index}'][:3]
    for i, row in enumerate(selected):
        raw = Path(row['image_path']).read_bytes()
        result, provenance = provider.infer(LiveInput(
            request_id=f'probe_c{index}_{i}',
            image_base64=base64.b64encode(raw).decode(),
            captured_at=datetime.now(timezone.utc).isoformat(),
        ))
        top = max(result.visual_top_classes, key=lambda p: p.probability)
        samples.append({'source_filename': row['filename'], 'split': row['split'],
                        'truth': class_id, 'prediction': top.label,
                        'top_probability': top.probability,
                        'source_image_sha256': hashlib.sha256(raw).hexdigest(),
                        'visual_probabilities': [p.model_dump() for p in result.visual_top_classes]})
report = {'purpose': 'Check whether the deployed provider is globally constant on known source-domain inputs; 3 first test rows per class, not a representative accuracy estimate.',
          'models': provider.info, 'samples': samples,
          'correct': sum(r['truth'] == r['prediction'] for r in samples),
          'total': len(samples), 'predicted_labels': sorted(set(r['prediction'] for r in samples))}
Path(__file__).with_name('source_class_probe.json').write_text(json.dumps(report, indent=2)+'\n')
print(json.dumps({k: report[k] for k in ['purpose', 'correct', 'total', 'predicted_labels']}, indent=2))
