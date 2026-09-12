```bash
# Import psaumes with MP3 audio files
python scripts/import_psaumes.py --dossier "/path/to/chants" --dry-run
python scripts/import_psaumes.py --dossier "/path/to/chants"
python scripts/import_psaumes.py --dossier "/path/to/chants" --force

# Import Fonsalas with MXL files
python scripts/import_fonsalas.py --dossier "/path/to/fonsalas" --dry-run
python scripts/import_fonsalas.py --dossier "/path/to/fonsalas"
python scripts/import_fonsalas.py --dossier "/path/to/fonsalas" --force
```

**Requirements:**
- `GEMMA_API_KEY` environment variable or `--api-key` argument
- google-generativeai and PyPDF2 packages
