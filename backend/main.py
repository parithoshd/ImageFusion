# main.py
import os
import io
import uuid
import base64
import tempfile
from pathlib import Path
from typing import List
import traceback
import httpx
from fastapi import FastAPI, HTTPException # type: ignore
from fastapi.middleware.cors import CORSMiddleware # type: ignore
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import openai
from dotenv import load_dotenv
from transformers import CLIPProcessor, CLIPModel
import torch
import certifi
import httpx
from PIL import Image

env_path = Path(__file__).parent / ".env"
load_dotenv(dotenv_path=env_path)
openai.api_key = os.getenv("OPENAI_API_KEY")
print("🔑 Loaded API Key starts with:", openai.api_key[:8] + "..." if openai.api_key else "❌ Not Loaded")



# Create FastAPI app
app = FastAPI()

@app.on_event("startup")
async def startup_event():
    print("⚡ Loading CLIP model once during startup...")
    app.state.clip_model = CLIPModel.from_pretrained("openai/clip-vit-base-patch32")
    app.state.clip_processor = CLIPProcessor.from_pretrained("openai/clip-vit-base-patch32")
    print("✅ CLIP model ready.")

# Allow frontend to access backend (CORS)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, lock this to frontend domain
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Create static folder to save generated images
output_dir = Path("static")
output_dir.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=output_dir), name="static")

# Define input model
class GenerateRequest(BaseModel):
    prompt: str
    refs: List[str]  # Image URLs or data URLs


def summarize_prompt(merged_prompt):
    try:
        response = openai.chat.completions.create(
            model="gpt-4o",  # or gpt-3.5-turbo
            messages=[
                {"role": "system", "content": "Summarize the following content into approximately 50 words, preserving all important visual elements. The generated summary will be used as input to a CLIP model, which allows only 77 tokens, so prioritize conciseness while retaining key details. Avoid verbose expressions and focus on clear, visual descriptions."},
                {"role": "user", "content": merged_prompt}
            ],
            temperature=0.5,
            max_tokens=300
        )
        summary = response.choices[0].message.content
        return summary
    except Exception as e:
        print(f"Error during summarization: {e}")
        return merged_prompt

@app.post("/generate")
async def generate(body: GenerateRequest):
    try:
        print("\n📥 Received prompt:", body.prompt)
        print("🖼 Received image refs:", body.refs)

        # Download reference images
        temp_dir = Path(tempfile.mkdtemp())
        image_paths = []

        async with httpx.AsyncClient(verify=certifi.where(), follow_redirects=True) as client:
            for ref in body.refs:
                out_path = temp_dir / f"{uuid.uuid4().hex}.png"
                print(f"➡️ Downloading: {ref}")
                if ref.startswith("http"):
                    r = await client.get(ref)
                    r.raise_for_status()
                    out_path.write_bytes(r.content)
                elif ref.startswith("data:image"):
                    _, b64 = ref.split(",", 1)
                    out_path.write_bytes(base64.b64decode(b64))
                else:
                    raise HTTPException(status_code=400, detail="Invalid image source.")
                image_paths.append(out_path)
                print(f"✅ Saved to: {out_path}")

        print("✅ All images downloaded successfully.")

        # Prepare all images as base64 first
        images_base64_list = []
        for path in image_paths:
            print(f"📦 Loading image: {path}")
            with open(path, "rb") as f:
                img_b64 = base64.b64encode(f.read()).decode()
                images_base64_list.append(img_b64)

        print("✅ All images loaded successfully.")

        # Compose a single summarization prompt
        # summarization_prompt = (
        #     "These images represent different visual elements to be combined into a single composite image. "
        #     "For each image, briefly summarize the key visual features, if it is a person, skin tone, gender and physical attributes to be emphasized for description (under 20 words per image), "
        #     "identify recognizable real or fictional characters by name if visible, and then merge all descriptions "
        #     "with the following main instruction: "
        #     f"\"{body.prompt.strip()}\" "
        #     "Ensure the final prompt respects this main instruction while blending all elements seamlessly into one coherent image description for dall-e-3."
        # )

        summarization_prompt = (
    "For each image: "
    "If it contains a person,you have to mention the ethnicity or skin tone, then describe the person's visible characteristics (e.g., hair color, gender, ethnicity) in about 30 words, ignoring the background. "
    "If it contains only a background, describe the scene. "
    "If it contains only an object, describe the object's visual details. "
    "Do not infer or imagine missing details. Only describe what is explicitly visible."

    "Then, combine the descriptions of all images into the following user instruction for the prompt: "
    f"\"{body.prompt.strip()}\" "
    "Create a summarized prompt that will be used as input to DALL-E 3, so prioritize clarity, key details, and visual faithfulness."
    "The combined prompt must create a single continuous scene, not separate sections. "
        )
        print(summarization_prompt)

        print("📝 Sending batch summarization request to GPT-4o...")

        # Send one API call
        resp = openai.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "user",
                    "content": [
                        *[
                            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img_b64}"}}
                            for img_b64 in images_base64_list
                        ],
                        {"type": "text", "text": summarization_prompt}
                    ]
                }
            ]
        )

        # Get final merged prompt ready for DALL-E
        merged_prompt = resp.choices[0].message.content.strip()

        print("✅ Final merged prompt ready!")

        

        # Generate image with DALL·E
        prompt=merged_prompt + "Strictly avoid introducing extra characters, unrelated objects, or changing the original elements.Depict all individuals together naturally, interacting in the same scene, avoiding separate frames or isolated placement.Capture the scene in highly detailed photorealistic style, with natural human features, realistic lighting, and cinematic atmosphere, as if taken by a professional camera. "
        print("📝 Final merged prompt to DALL·E:\n", prompt)
        print("🎨 Calling DALL·E 3 to generate composite image...")
        result = openai.images.generate(
            model="dall-e-3",
            prompt=prompt,
            n=1,
            size="1024x1024",
            response_format="b64_json",
        )

        image_data = base64.b64decode(result.data[0].b64_json)
        output_filename = f"{uuid.uuid4().hex}.png"
        final_path = Path("static") / output_filename
        final_path.write_bytes(image_data)

        print(f"✅ Composite image saved at: static/{output_filename}")

        print("📝 Summarizing prompt using OpenAI...")
        # summarized_prompt = summarize_prompt(merged_prompt)
        # print(summarized_prompt)
        # Encode prompt and image
        summarization_prompt = (
            "Summarize only the visual elements visible in these images in under 50 words. Do not infer or guess missing details. Only describe visible features. The generated summary will be used as input to a CLIP model, which allows only 77 tokens, so prioritize conciseness while retaining key details. Avoid verbose expressions and focus on clear, visual descriptions."
        )
        print(summarization_prompt)

        print("📝 Sending batch summarization request to GPT-4o...")

        # Send one API call
        resp = openai.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "user",
                    "content": [
                        *[
                            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img_b64}"}}
                            for img_b64 in images_base64_list
                        ],
                        {"type": "text", "text": summarization_prompt}
                    ]
                }
            ]
        )

        # Get final merged prompt ready for DALL-E
        summarized_prompt = resp.choices[0].message.content.strip()
        print("🔍 Calculating CLIP IRSS score...")
        print(summarized_prompt)
        clip_model = app.state.clip_model
        clip_processor = app.state.clip_processor
        image = Image.open(final_path).convert("RGB")

        # Process inputs correctly
        inputs = clip_processor(
            text=[summarized_prompt],
            images=image,
            return_tensors="pt",
            padding=True,
            truncation=True,
            max_length=77
        )

        with torch.no_grad():
            outputs = clip_model(**inputs)
            image_embeds = outputs.image_embeds
            text_embeds = outputs.text_embeds

        # Normalize embeddings (VERY IMPORTANT)
        image_embeds = image_embeds / image_embeds.norm(p=2, dim=-1, keepdim=True)
        text_embeds = text_embeds / text_embeds.norm(p=2, dim=-1, keepdim=True)

        # Calculate cosine similarity
        irss_score = (image_embeds @ text_embeds.T).item()

        print(f"📈 Corrected CLIP IRSS Score: {irss_score:.4f}")


        return {
            "file_path": f"/static/{output_filename}",
            "prompt": merged_prompt,
            "clip_irss": irss_score
        }

    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))