# fact-checker

Lightweight Python POC for transcript-based claim extraction and fact-check payload generation for iconik timelines.

## Run

```bash
python3 poc_factcheck_timeline.py --transcript sample_transcript.txt --out factcheck_comments.json
python3 poc_v2_factcheck_service.py --asset-id demo-asset --transcript sample_transcript.txt --out-dir .
```

## Test

```bash
python3 -m unittest discover -s tests -p 'test_*.py'
```
