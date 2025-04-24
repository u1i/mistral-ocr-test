import os
import json
import base64
import shutil
from pathlib import Path
from mistralai import Mistral
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Get API key from environment variables
api_key = os.getenv("MISTRAL_API_KEY")
if not api_key:
    raise ValueError("MISTRAL_API_KEY environment variable is not set. Please check your .env file.")

# Initialize Mistral client
client = Mistral(api_key=api_key)

def process_pdf(pdf_path):
    """
    Process a PDF file using Mistral OCR and return the structured content.
    
    Args:
        pdf_path (str): Path to the PDF file
    
    Returns:
        dict: The OCR response containing structured content
    """
    # Convert to absolute path
    abs_path = Path(pdf_path).resolve()
    
    if not abs_path.exists():
        raise FileNotFoundError(f"PDF file not found: {pdf_path}")
    
    print(f"Processing PDF: {abs_path}")
    
    # Step 1: Upload the PDF file to Mistral
    print(f"Uploading file to Mistral...")
    with open(abs_path, 'rb') as file:
        uploaded_pdf = client.files.upload(
            file={
                "file_name": abs_path.name,
                "content": file,
            },
            purpose="ocr"
        )
    
    print(f"File uploaded successfully with ID: {uploaded_pdf.id}")
    
    # Step 2: Retrieve the file to confirm upload
    retrieved_file = client.files.retrieve(file_id=uploaded_pdf.id)
    print(f"Retrieved file: {retrieved_file.filename}, size: {retrieved_file.size_bytes} bytes")
    
    # Step 3: Get a signed URL for the uploaded file
    signed_url = client.files.get_signed_url(file_id=uploaded_pdf.id)
    print(f"Got signed URL for the file")
    
    # Step 4: Process the PDF using the signed URL
    print(f"Processing PDF with OCR...")
    ocr_response = client.ocr.process(
        model="mistral-ocr-latest",
        document={
            "type": "document_url",
            "document_url": signed_url.url,
        },
        include_image_base64=True  # Make sure to include base64 image data
    )
    
    print(f"OCR processing completed successfully")
    
    return ocr_response

def save_markdown(ocr_response, output_dir="output"):
    """
    Save the markdown content and images from OCR response to files.
    
    Args:
        ocr_response (OCRResponse): The OCR response from Mistral
        output_dir (str): Directory to save the output files
    """
    # Create output directory if it doesn't exist
    output_path = Path(output_dir)
    output_path.mkdir(exist_ok=True)
    
    # Convert OCRResponse to dict for JSON serialization
    ocr_dict = ocr_response.model_dump() if hasattr(ocr_response, 'model_dump') else vars(ocr_response)
    
    # Save the full OCR response as JSON for reference
    with open(output_path / "ocr_response.json", "w") as f:
        json.dump(ocr_dict, f, indent=2)
    
    # Get pages from the response, handling both dict and object access
    pages = ocr_dict.get("pages", []) if isinstance(ocr_dict, dict) else getattr(ocr_response, "pages", [])
    
    # Track extracted images
    images_extracted = 0
    
    for page in pages:
        # Handle both dict and object access for page properties
        if isinstance(page, dict):
            page_num = page.get("index", 0)
            markdown_content = page.get("markdown", "")
            images = page.get("images", [])
        else:
            page_num = getattr(page, "index", 0)
            markdown_content = getattr(page, "markdown", "")
            images = getattr(page, "images", [])
        
        # Save individual page markdown
        with open(output_path / f"page_{page_num}.md", "w") as f:
            f.write(markdown_content)
        
        # Extract and save images if present
        for i, image_data in enumerate(images):
            # Get image id and base64 data
            if isinstance(image_data, dict):
                image_id = image_data.get("id")
                image_base64 = image_data.get("image_base64")
            else:
                image_id = getattr(image_data, "id", None)
                image_base64 = getattr(image_data, "image_base64", None)
                
            if image_id and image_base64:
                # Fix and save the image
                try:
                    # Start with a standard JPEG header
                    jpeg_header = bytes([0xFF, 0xD8, 0xFF, 0xE0, 0x00, 0x10, 0x4A, 0x46, 0x49, 0x46, 0x00, 0x01, 0x01, 0x00, 0x00, 0x01, 0x00, 0x01, 0x00, 0x00])
                    
                    # Try to decode the base64 data
                    try:
                        # First try standard base64 decoding
                        image_data = base64.b64decode(image_base64)
                    except:
                        try:
                            # Then try URL-safe base64 decoding
                            image_data = base64.urlsafe_b64decode(image_base64)
                        except:
                            # If both fail, try with padding
                            padded_base64 = image_base64 + '=' * (4 - len(image_base64) % 4)
                            image_data = base64.b64decode(padded_base64)
                    
                    # Create a new JPEG file with proper headers
                    image_path = output_path / image_id
                    with open(image_path, "wb") as img_file:
                        # Write the JPEG header followed by the image data
                        img_file.write(jpeg_header + image_data[20:] if len(image_data) > 20 else image_data)
                    
                    images_extracted += 1
                    print(f"Image extracted and fixed: {image_id}")
                except Exception as e:
                    print(f"Error extracting image {image_id}: {e}")
                    
                    # Fallback: Just save the raw data
                    try:
                        with open(output_path / image_id, "wb") as img_file:
                            img_file.write(base64.b64decode(image_base64))
                        print(f"Fallback: Saved raw data for {image_id}")
                    except Exception as e2:
                        print(f"Fallback failed for {image_id}: {e2}")
    
    # Create a combined markdown file with all pages
    combined_markdown = ""
    for page in pages:
        # Handle both dict and object access for page properties
        if isinstance(page, dict):
            page_num = page.get("index", 0)
            markdown_content = page.get("markdown", "")
        else:
            page_num = getattr(page, "index", 0)
            markdown_content = getattr(page, "markdown", "")
        
        combined_markdown += f"## Page {page_num}\n\n{markdown_content}\n\n"
    
    with open(output_path / "combined.md", "w") as f:
        f.write(combined_markdown)
    
    print(f"Markdown files saved to {output_path.resolve()}")

def main():
    """Main function to process the PDF and save the markdown content."""
    # Path to the PDF file - you can change this to your own PDF file
    pdf_path = "slides.pdf"
    
    # Create output directory if it doesn't exist
    output_dir = "output"
    Path(output_dir).mkdir(exist_ok=True)
    
    try:
        # Process the PDF
        print("\n=== Processing PDF ===\n")
        ocr_response = process_pdf(pdf_path)
        
        # Save the markdown content and extract images
        print("\n=== Extracting Content and Images ===\n")
        save_markdown(ocr_response, output_dir)
        
        # Check if images were successfully extracted
        image_files = list(Path(output_dir).glob("*.jpeg"))
        
        print("\n=== PDF Processing Summary ===\n")
        print(f"Input PDF: {pdf_path}")
        print(f"Output directory: {output_dir}")
        print(f"Markdown files: combined.md and individual page_X.md files")
        print(f"Images extracted: {len(image_files)} images")
        
        # List the extracted images
        if image_files:
            print("\nExtracted images:")
            for img in image_files:
                print(f"- {img.name}")
        
        print("\nPDF processing completed successfully!")
        print("\nYou can now view the markdown files and images in the output directory.")
    except Exception as e:
        print(f"\nError processing PDF: {e}")

if __name__ == "__main__":
    main()
