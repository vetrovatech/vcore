# Glass Image Generation Guide

## Overview
This guide helps you generate high-quality images for 5 glass types for the glassy.in website using Replicate AI.

## Glass Types
1. **Acid Etched Glass** - Smooth frosted finish, translucent privacy glass
2. **Designed Etched Glass** - Decorative patterns, artistic motifs
3. **Sandblasted Etched Glass** - Uniform matte texture, privacy glass
4. **Clear Float Glass** - Crystal clear, transparent glass
5. **Fluted Glass** - Vertical ribbed texture, light diffusion

## Recommended Models

### Option 1: Flux Pro (Recommended)
- **Model**: `black-forest-labs/flux-pro`
- **Quality**: Best for architectural visualization
- **Cost**: ~$0.05 per image
- **Total Cost**: ~$1.00 for all 20 images
- **Speed**: ~30-60 seconds per image

### Option 2: SDXL (Budget-friendly)
- **Model**: `stability-ai/sdxl`
- **Quality**: Good for product photography
- **Cost**: ~$0.002 per image
- **Total Cost**: ~$0.04 for all 20 images
- **Speed**: ~10-20 seconds per image

## Setup Instructions

### 1. Install Dependencies
```bash
pip install replicate requests
```

### 2. Get Replicate API Token
1. Sign up at https://replicate.com
2. Go to https://replicate.com/account/api-tokens
3. Create a new token
4. Set environment variable:
```bash
export REPLICATE_API_TOKEN='your-token-here'
```

### 3. Run the Script
```bash
python generate_glass_images.py
```

## Output Structure
```
glass_images/
├── Acid_Etched_Glass/
│   ├── Acid_Etched_Glass_1.png
│   ├── Acid_Etched_Glass_2.png
│   ├── Acid_Etched_Glass_3.png
│   └── Acid_Etched_Glass_4.png
├── Designed_Etched_Glass/
│   ├── Designed_Etched_Glass_1.png
│   └── ...
├── Sandblasted_Etched_Glass/
├── Clear_Float_Glass/
└── Fluted_Glass/
```

## Prompt Engineering Tips

### Key Elements in Prompts:
1. **Context**: "Modern luxury apartment interior"
2. **Glass Type**: Specific glass characteristics
3. **Setting**: Living room, bathroom, office, etc.
4. **Lighting**: Natural daylight, ambient lighting
5. **Style**: Professional architectural photography, 8k, ultra realistic

### Example Prompt Structure:
```
[Setting] with [Glass Type] [Application], [Glass Characteristics], 
[Interior Style], [Lighting], professional architectural photography, 
8k, ultra realistic
```

## Customization

### Modify Prompts
Edit the `GLASS_TYPES` dictionary in `generate_glass_images.py` to customize prompts for your specific needs.

### Change Image Dimensions
For Flux Pro:
```python
"aspect_ratio": "16:9"  # Options: "1:1", "16:9", "21:9", "3:2", "4:5", "9:16"
```

For SDXL:
```python
"width": 1024,
"height": 768
```

## Upload to S3
After generation, you can upload to S3 using the existing S3 uploader:

```python
from utils.s3_upload import S3Uploader

uploader = S3Uploader()
# Upload images to S3
```

## Cost Estimation

### Flux Pro (20 images)
- 20 images × $0.05 = **$1.00**

### SDXL (20 images)
- 20 images × $0.002 = **$0.04**

## Troubleshooting

### API Token Error
```bash
export REPLICATE_API_TOKEN='r8_...'  # Your token
```

### Rate Limiting
If you hit rate limits, add delays between requests:
```python
import time
time.sleep(2)  # Wait 2 seconds between images
```

### Image Quality Issues
- Use Flux Pro for best quality
- Increase `num_inference_steps` for SDXL (50-100)
- Adjust `guidance_scale` (7-8 for realistic images)

## Next Steps
1. Generate images using the script
2. Review and select best images
3. Upload to S3 bucket
4. Update product catalog in VCore
