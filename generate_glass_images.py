"""
Generate Glass Product Images using Replicate API
Generates 4 images for each glass type for glassy.in website
"""
import replicate
import os
import requests
from pathlib import Path

# Glass types and their descriptions
GLASS_TYPES = {
    "Acid_Etched_Glass": {
        "prompts": [
            "Modern luxury apartment interior with acid etched glass partition, translucent frosted surface with subtle texture, elegant living room, natural daylight, professional architectural photography, 8k, ultra realistic",
            "Contemporary bathroom with acid etched glass shower enclosure, privacy glass with smooth matte finish, chrome fixtures, marble tiles, soft ambient lighting, interior design photography",
            "Upscale office interior with acid etched glass door, semi-transparent frosted glass, modern minimalist design, corporate environment, professional photography, high detail",
            "Elegant dining room with acid etched glass cabinet doors, sophisticated frosted glass panels, contemporary furniture, warm lighting, architectural digest style photography"
        ]
    },
    "Designed_Etched_Glass": {
        "prompts": [
            "Luxurious apartment entrance with designed etched glass featuring geometric patterns, decorative frosted glass with intricate designs, modern foyer, chandelier lighting, architectural photography, 8k",
            "Premium living room with designed etched glass room divider, artistic floral pattern etching, elegant interior, natural light filtering through, professional interior photography",
            "Contemporary bedroom with designed etched glass wardrobe doors, custom decorative patterns, modern furniture, soft lighting, high-end interior design photography",
            "Sophisticated bathroom with designed etched glass window, ornate privacy glass with artistic motifs, luxury fixtures, spa-like ambiance, professional photography"
        ]
    },
    "Sandblasted_Etched_Glass": {
        "prompts": [
            "Modern apartment with sandblasted etched glass balcony railing, textured frosted glass panels, city view, contemporary architecture, professional photography, 8k, ultra detailed",
            "Upscale kitchen with sandblasted etched glass cabinet fronts, uniform matte finish, sleek modern design, stainless steel appliances, architectural photography",
            "Luxury bathroom with sandblasted etched glass shower partition, smooth frosted surface, minimalist design, chrome fixtures, professional interior photography",
            "Contemporary office with sandblasted etched glass conference room walls, translucent privacy glass, modern workspace, natural daylight, architectural photography"
        ]
    },
    "Clear_Float_Glass": {
        "prompts": [
            "Modern luxury apartment with floor-to-ceiling clear float glass windows, panoramic city skyline view, contemporary interior, natural daylight flooding in, architectural photography, 8k",
            "Minimalist living room with clear float glass coffee table, transparent glass furniture, modern design, bright airy space, professional interior photography",
            "Contemporary apartment with clear float glass balcony railing, unobstructed views, sleek frameless design, urban setting, architectural photography, ultra realistic",
            "Upscale dining area with clear float glass dining table, crystal clear transparency, modern chairs, elegant setting, professional photography, high detail"
        ]
    },
    "Fluted_Glass": {
        "prompts": [
            "Elegant apartment interior with fluted glass partition, vertical ribbed texture, light diffusion effect, modern luxury design, natural daylight, architectural photography, 8k, ultra detailed",
            "Contemporary bathroom with fluted glass shower enclosure, textured vertical grooves, privacy with style, chrome fixtures, professional interior photography",
            "Modern kitchen with fluted glass cabinet doors, ribbed glass panels, sophisticated design, integrated lighting, architectural digest style photography",
            "Luxury bedroom with fluted glass wardrobe doors, vertical ridged pattern, ambient lighting, contemporary furniture, professional interior design photography"
        ]
    }
}

def generate_images_flux_pro(output_dir="glass_images"):
    """
    Generate images using Flux Pro (best quality for architectural visualization)
    """
    # Create output directory
    Path(output_dir).mkdir(exist_ok=True)
    
    print("🎨 Generating glass images using Flux Pro...")
    print("=" * 60)
    
    for glass_type, data in GLASS_TYPES.items():
        print(f"\n📸 Generating images for: {glass_type.replace('_', ' ')}")
        
        # Create subdirectory for this glass type
        glass_dir = Path(output_dir) / glass_type
        glass_dir.mkdir(exist_ok=True)
        
        for idx, prompt in enumerate(data["prompts"], 1):
            print(f"   Image {idx}/4: Generating...")
            
            try:
                # Run Flux Pro model
                output = replicate.run(
                    "black-forest-labs/flux-pro",
                    input={
                        "prompt": prompt,
                        "aspect_ratio": "16:9",  # Good for interior shots
                        "output_format": "png",
                        "output_quality": 100,
                        "safety_tolerance": 2,
                        "prompt_upsampling": True
                    }
                )
                
                # Download the image
                image_url = output if isinstance(output, str) else output[0]
                response = requests.get(image_url)
                
                if response.status_code == 200:
                    filename = f"{glass_type}_{idx}.png"
                    filepath = glass_dir / filename
                    
                    with open(filepath, 'wb') as f:
                        f.write(response.content)
                    
                    print(f"   ✅ Saved: {filepath}")
                else:
                    print(f"   ❌ Failed to download image {idx}")
                    
            except Exception as e:
                print(f"   ❌ Error generating image {idx}: {e}")
    
    print("\n" + "=" * 60)
    print(f"✅ All images generated in '{output_dir}/' directory")

def generate_images_sdxl(output_dir="glass_images_sdxl"):
    """
    Generate images using SDXL (faster, good quality alternative)
    """
    # Create output directory
    Path(output_dir).mkdir(exist_ok=True)
    
    print("🎨 Generating glass images using SDXL...")
    print("=" * 60)
    
    for glass_type, data in GLASS_TYPES.items():
        print(f"\n📸 Generating images for: {glass_type.replace('_', ' ')}")
        
        # Create subdirectory for this glass type
        glass_dir = Path(output_dir) / glass_type
        glass_dir.mkdir(exist_ok=True)
        
        for idx, prompt in enumerate(data["prompts"], 1):
            print(f"   Image {idx}/4: Generating...")
            
            try:
                # Run SDXL model
                output = replicate.run(
                    "stability-ai/sdxl:39ed52f2a78e934b3ba6e2a89f5b1c712de7dfea535525255b1aa35c5565e08b",
                    input={
                        "prompt": prompt,
                        "width": 1024,
                        "height": 768,
                        "num_outputs": 1,
                        "scheduler": "K_EULER",
                        "num_inference_steps": 50,
                        "guidance_scale": 7.5,
                        "refine": "expert_ensemble_refiner",
                        "high_noise_frac": 0.8
                    }
                )
                
                # Download the image
                image_url = output[0] if isinstance(output, list) else output
                response = requests.get(image_url)
                
                if response.status_code == 200:
                    filename = f"{glass_type}_{idx}.png"
                    filepath = glass_dir / filename
                    
                    with open(filepath, 'wb') as f:
                        f.write(response.content)
                    
                    print(f"   ✅ Saved: {filepath}")
                else:
                    print(f"   ❌ Failed to download image {idx}")
                    
            except Exception as e:
                print(f"   ❌ Error generating image {idx}: {e}")
    
    print("\n" + "=" * 60)
    print(f"✅ All images generated in '{output_dir}/' directory")

if __name__ == "__main__":
    # Check for API token
    if not os.environ.get("REPLICATE_API_TOKEN"):
        print("❌ Error: REPLICATE_API_TOKEN environment variable not set")
        print("Please set it with: export REPLICATE_API_TOKEN='your-token-here'")
        exit(1)
    
    print("\n🏢 Glass Image Generator for glassy.in")
    print("=" * 60)
    print("\nChoose model:")
    print("1. Flux Pro (Best quality, slower, ~$0.05 per image)")
    print("2. SDXL (Good quality, faster, ~$0.002 per image)")
    
    choice = input("\nEnter choice (1 or 2): ").strip()
    
    if choice == "1":
        generate_images_flux_pro()
    elif choice == "2":
        generate_images_sdxl()
    else:
        print("Invalid choice. Using SDXL by default...")
        generate_images_sdxl()
    
    print("\n🎉 Done! Check the output directory for your images.")
