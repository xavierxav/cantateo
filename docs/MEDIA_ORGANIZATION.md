# Media File Organization

## Overview

Media files (PDFs, MXL partitions, and audio files) are now organized into subdirectories based on psalm numbers or canticle references for better file management.

## New Structure

### Partitions (PDF & MXL)

Files are stored by format, using a slugified version of the title and composer:
`media/partitions/{format}/{titre}_{compositeur}.{ext}`

**Example:**
```
media/partitions/pdf/psaume-23_anonyme.pdf
media/partitions/mxl/psaume-23_anonyme.mxl
```

### Audio Files

Audio tracks are organized by arrangement (Partition) folder:
`media/audios/{titre}_{compositeur}/{voice}.mp3`

**Example:**
```
media/audios/psaume-23_anonyme/soprano.mp3
media/audios/psaume-23_anonyme/alto.mp3
media/audios/psaume-23_anonyme/tenor.mp3
media/audios/psaume-23_anonyme/basse.mp3
media/audios/psaume-23_anonyme/instrumental.mp3
media/audios/psaume-23_anonyme/mix.mp3
```
## Benefits

1. **Better Organization**: Files grouped by psalm/canticle make it easier to manage large collections
2. **Easier Backup**: Can backup specific psalms/canticles by directory
3. **Clearer Structure**: Directory names clearly indicate what's inside
4. **Scalability**: Avoids thousands of files in a single directory

## Notes

- New uploads automatically use the new structure
- Existing files continue to work at their current location
- The command is idempotent - safe to run multiple times
