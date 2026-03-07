# ============================================================
# DocuMind - Module 5 (Enhanced): RAG with Anti-Hallucination
# 
# This version adds production-grade guardrails:
# 1. Relevance threshold - filter out weak matches
# 2. Strict system prompt - only answer from documents
# 3. Low temperature - deterministic responses
# 4. Confidence scoring - Claude rates its own confidence
# 5. Response validation - check answers are grounded
# ============================================================

# --- Framework ---
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from datetime import datetime

# --- Environment & AI ---
from dotenv import load_dotenv
import anthropic

# --- PDF Processing ---
import fitz

# --- Vector Database & Embeddings ---
import chromadb
from sentence_transformers import SentenceTransformer

# --- File system ---
import os
import uuid

# --- New: Regular expressions for parsing confidence scores ---
# re is a built-in Python module for pattern matching in text
# We'll use it to find the confidence score in Claude's response
import re

# Load environment variables
load_dotenv()

# ------------------------------------------------------------
# Configuration
# ------------------------------------------------------------
UPLOAD_DIR = "./uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

# NEW: Anti-hallucination settings
# These are tunable parameters you can adjust based on
# how strict you want the system to be

# Maximum distance for a chunk to be considered relevant
# Lower = stricter (only very similar matches)
# Higher = looser (more matches, but potentially less relevant)
# 0.7 is a good starting point for most use cases
RELEVANCE_THRESHOLD = 0.7

# Temperature for Claude's responses
# 0.0 = completely deterministic (same question = same answer)
# 0.1 = very low creativity (good for factual Q&A)
# 1.0 = full creativity (good for brainstorming, bad for facts)
CLAUDE_TEMPERATURE = 0.1

# Minimum confidence score to return an answer without warning
# Claude will rate its confidence 1-5
# Below this threshold, we add a warning to the response
CONFIDENCE_THRESHOLD = 3

# ------------------------------------------------------------
# Initialize embedding model and ChromaDB
# ------------------------------------------------------------
embedding_model = SentenceTransformer("all-MiniLM-L6-v2")

chroma_client = chromadb.PersistentClient(path="./chroma_data")
collection = chroma_client.get_or_create_collection(
    name="documents",
    metadata={"hnsw:space": "cosine"}
)

# ------------------------------------------------------------
# Pydantic Models
# ------------------------------------------------------------

class Question(BaseModel):
    """What the user sends TO us"""
    text: str
    document_id: str | None = None

class Answer(BaseModel):
    """Claude's response - now with confidence and warnings!"""
    question: str
    answer: str
    model: str
    sources: list[dict] | None = None
    confidence: int | None = None          # NEW: 1-5 confidence score
    warning: str | None = None             # NEW: warning if low confidence
    timestamp: str

class DocumentInfo(BaseModel):
    """Metadata about an uploaded document"""
    id: str
    filename: str
    pages: int
    chunks: int
    timestamp: str

class Chunk(BaseModel):
    """A piece of a document"""
    text: str
    page: int
    chunk_index: int
    document_id: str

# ------------------------------------------------------------
# Document metadata storage
# ------------------------------------------------------------
documents = {}

# ------------------------------------------------------------
# PDF Processing Functions
# ------------------------------------------------------------

def extract_text_from_pdf(file_path: str) -> list[dict]:
    """Read a PDF and extract text from each page."""
    doc = fitz.open(file_path)
    pages = []
    for page_num, page in enumerate(doc, start=1):
        text = page.get_text()
        if text.strip():
            pages.append({"page": page_num, "text": text.strip()})
    doc.close()
    return pages


def chunk_text(pages: list[dict], document_id: str,
               chunk_size: int = 500, overlap: int = 100) -> list[Chunk]:
    """Split extracted pages into smaller, overlapping chunks."""
    all_chunks = []
    chunk_index = 0
    for page_data in pages:
        text = page_data["text"]
        page_num = page_data["page"]
        start = 0
        while start < len(text):
            end = start + chunk_size
            chunk_text_content = text[start:end]
            if chunk_text_content.strip():
                all_chunks.append(Chunk(
                    text=chunk_text_content,
                    page=page_num,
                    chunk_index=chunk_index,
                    document_id=document_id
                ))
                chunk_index += 1
            start += chunk_size - overlap
    return all_chunks


# ------------------------------------------------------------
# Embedding and Storage Functions
# ------------------------------------------------------------

def store_chunks_in_chroma(chunks: list[Chunk], document_id: str):
    """Convert chunks to vectors and store them in ChromaDB."""
    if not chunks:
        return
    
    ids = [f"{document_id}_chunk_{c.chunk_index}" for c in chunks]
    texts = [c.text for c in chunks]
    metadatas = [
        {
            "document_id": c.document_id,
            "page": c.page,
            "chunk_index": c.chunk_index
        }
        for c in chunks
    ]
    embeddings = embedding_model.encode(texts).tolist()
    
    collection.add(
        ids=ids,
        documents=texts,
        metadatas=metadatas,
        embeddings=embeddings
    )


def search_chunks(query: str, top_k: int = 3, 
                  max_distance: float = RELEVANCE_THRESHOLD) -> list[dict]:
    """Search for relevant chunks with relevance filtering.
    
    NEW: max_distance parameter filters out weak matches.
    
    Without filtering (old behavior):
      Query: "What's for dinner?" against a security document
      → Returns 3 chunks with distances 0.85, 0.90, 0.92
      → These are barely relevant but would be sent to Claude
      → Claude might hallucinate an answer
    
    With filtering (new behavior):
      Same query, same document
      → All 3 chunks have distance > 0.7 (our threshold)
      → All get filtered out
      → Empty results = "no relevant documents found"
      → No hallucination risk
    
    Args:
        query: the user's question
        top_k: maximum number of results to return
        max_distance: only return chunks closer than this
                      (lower distance = more relevant)
    """
    query_embedding = embedding_model.encode(query).tolist()
    
    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=top_k
    )
    
    matches = []
    if results["documents"][0]:
        for doc, metadata, distance in zip(
            results["documents"][0],
            results["metadatas"][0],
            results["distances"][0]
        ):
            # NEW: Only keep chunks that are genuinely relevant
            # Skip anything with a distance greater than our threshold
            if distance <= max_distance:
                matches.append({
                    "text": doc,
                    "page": metadata["page"],
                    "document_id": metadata["document_id"],
                    "distance": round(distance, 4)  # Round for cleaner output
                })
    
    return matches


# ------------------------------------------------------------
# NEW: Anti-Hallucination Functions
# ------------------------------------------------------------

def parse_confidence(response_text: str) -> tuple[str, int | None]:
    """Extract the confidence score from Claude's response.
    
    We ask Claude to end its response with "Confidence: X/5".
    This function finds that pattern and separates it from
    the actual answer.
    
    Args:
        response_text: Claude's full response
        
    Returns:
        A tuple of (answer_without_confidence, confidence_score)
        tuple is like a list but immutable (can't be changed)
    
    re.search() looks for a pattern in a string:
        r'Confidence:\s*(\d)/5'
        - r'...' = raw string (backslashes aren't escape characters)
        - Confidence: = literal text to find
        - \s* = zero or more whitespace characters
        - (\d) = capture a single digit (the score)
        - /5 = literal text "/5"
    
    Example:
        Input:  "Here is the answer... Confidence: 4/5"
        Output: ("Here is the answer...", 4)
    """
    # Search for the confidence pattern anywhere in the text
    # re.IGNORECASE makes it case-insensitive (confidence, Confidence, CONFIDENCE)
    match = re.search(r'[Cc]onfidence:\s*(\d)/5', response_text)
    
    if match:
        # match.group(1) gets what's inside the parentheses (\d)
        # int() converts the string "4" to the number 4
        confidence = int(match.group(1))
        
        # Remove the confidence line from the answer
        # re.sub replaces the pattern with empty string
        # .strip() cleans up any extra whitespace
        clean_answer = re.sub(
            r'\n*[Cc]onfidence:\s*\d/5\s*$',  # Pattern at end of text
            '',                                  # Replace with nothing
            response_text
        ).strip()
        
        return clean_answer, confidence
    
    # If no confidence score found, return the original text
    return response_text, None


def validate_response(answer: str, sources: list[dict]) -> str | None:
    """Check if the answer seems grounded in the sources.
    
    This is a simple validation — not foolproof, but catches
    obvious cases where Claude ignores the sources.
    
    Returns a warning message if there are concerns,
    or None if everything looks fine.
    
    In a production system, you could use a second LLM call
    to verify the answer is grounded — called "LLM-as-judge".
    """
    # If we have sources but the answer doesn't mention them
    if sources and len(sources) > 0:
        answer_lower = answer.lower()
        
        # Check if the answer mentions it's using general knowledge
        # when it should be using documents
        general_knowledge_phrases = [
            "general knowledge",
            "based on my training",
            "i don't have specific",
            "without access to",
            "i cannot find"
        ]
        
        # Count how many general knowledge phrases appear
        general_count = sum(
            1 for phrase in general_knowledge_phrases
            if phrase in answer_lower
        )
        
        # If multiple general knowledge phrases appear despite
        # having source documents, something might be wrong
        if general_count >= 2:
            return ("Warning: The answer may not be fully grounded "
                    "in the provided documents. The AI appeared to "
                    "rely on general knowledge despite document "
                    "excerpts being available.")
    
    # No concerns found
    return None


# ------------------------------------------------------------
# Create the FastAPI app
# ------------------------------------------------------------
app = FastAPI(
    title="DocuMind",
    description="AI-Powered Document Q&A with RAG and MCP",
    version="0.5.1"
)

# --- CORS Middleware ---
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:4200"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Create the Anthropic client
client = anthropic.Anthropic()

# ------------------------------------------------------------
# GET endpoints
# ------------------------------------------------------------

@app.get("/")
def home():
    """Serve Angular frontend if available, otherwise return API info"""
    if os.path.exists("static/index.html"):
        return FileResponse("static/index.html")
    return {"message": "Welcome to DocuMind! RAG pipeline with anti-hallucination guardrails."}

@app.get("/api/health")
def health_check():
    """Health check with vector DB stats and config info"""
    return {
        "status": "healthy",
        "service": "DocuMind",
        "documents_loaded": len(documents),
        "total_chunks_in_vector_db": collection.count(),
        "config": {
            "relevance_threshold": RELEVANCE_THRESHOLD,
            "temperature": CLAUDE_TEMPERATURE,
            "confidence_threshold": CONFIDENCE_THRESHOLD
        },
        "timestamp": datetime.now().isoformat()
    }

@app.get("/api/documents")
def list_documents():
    """List all uploaded documents."""
    return list(documents.values())

# ------------------------------------------------------------
# POST endpoints
# ------------------------------------------------------------

@app.post("/api/upload", response_model=DocumentInfo)
async def upload_document(file: UploadFile = File(...)):
    """Upload a PDF - extracts text, chunks it, and stores vectors."""
    
    if not file.filename.endswith(".pdf"):
        raise HTTPException(
            status_code=400,
            detail="Only PDF files are supported."
        )
    
    doc_id = str(uuid.uuid4())
    file_path = f"{UPLOAD_DIR}/{doc_id}-{file.filename}"
    with open(file_path, "wb") as buffer:
        content = await file.read()
        buffer.write(content)
    
    pages = extract_text_from_pdf(file_path)
    doc_chunks = chunk_text(pages, doc_id)
    store_chunks_in_chroma(doc_chunks, doc_id)
    
    doc_info = DocumentInfo(
        id=doc_id,
        filename=file.filename,
        pages=len(pages),
        chunks=len(doc_chunks),
        timestamp=datetime.now().isoformat()
    )
    documents[doc_id] = doc_info
    
    return doc_info


@app.post("/api/search")
def search_documents(question: Question):
    """Search for relevant document chunks by meaning."""
    results = search_chunks(question.text)
    return {
        "query": question.text,
        "results": results,
        "count": len(results),
        "threshold": RELEVANCE_THRESHOLD
    }


@app.post("/api/ask", response_model=Answer)
def ask_question(question: Question):
    """Ask a question with full RAG and anti-hallucination guardrails.
    
    The enhanced pipeline:
    1. RETRIEVE: Search ChromaDB with relevance filtering
    2. AUGMENT: Build a strict prompt with confidence scoring
    3. GENERATE: Claude answers with low temperature
    4. VALIDATE: Parse confidence and check grounding
    5. RETURN: Include confidence score and any warnings
    """
    
    # --- Step 1: RETRIEVE with relevance filtering ---
    # Only chunks below RELEVANCE_THRESHOLD are returned
    # Weak matches are filtered out completely
    relevant_chunks = search_chunks(question.text, top_k=3)
    
    # --- Step 2: AUGMENT with strict prompt ---
    if relevant_chunks:
        context_parts = []
        for i, chunk in enumerate(relevant_chunks, start=1):
            context_parts.append(
                f"Source {i} (Page {chunk['page']}):\n{chunk['text']}"
            )
        context = "\n\n".join(context_parts)
        
        # ENHANCED PROMPT with strict grounding instructions
        # and confidence scoring requirement
        user_message = f"""Answer the question based ONLY on the document excerpts below.

RULES:
- Use ONLY information found in the excerpts
- If the excerpts don't contain enough information to answer, say "The uploaded documents do not contain enough information to answer this question."
- Do NOT supplement with general knowledge unless the excerpts are insufficient
- Cite which Source number(s) you used for each part of your answer
- Be concise and accurate

DOCUMENT EXCERPTS:
{context}

QUESTION: {question.text}

After your answer, on a new line, rate your confidence:
Confidence: X/5
(5 = answer directly found in excerpts, 3 = partially supported, 1 = not supported)"""
    
    else:
        # No relevant documents found after filtering
        # Be transparent about it
        user_message = f"""No relevant documents were found for this question 
(all matches were below the relevance threshold of {RELEVANCE_THRESHOLD}).

Please respond with:
"I could not find relevant information in the uploaded documents to answer this question. 
Please try rephrasing your question or upload documents related to this topic."

Do not answer from general knowledge.

QUESTION: {question.text}

Confidence: 1/5"""
    
    # --- Step 3: GENERATE with low temperature ---
    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=1024,
        
        # LOW TEMPERATURE = less creative, more factual
        # This reduces the chance of Claude "making things up"
        temperature=CLAUDE_TEMPERATURE,
        
        # STRICT SYSTEM PROMPT
        system="""You are DocuMind, a precise document Q&A assistant.
Your primary job is to answer questions based ONLY on provided document excerpts.
Never invent information. Never guess. If the documents don't contain the answer, say so.
Always cite your sources by Source number.
Always end your response with a confidence rating.""",
        
        messages=[
            {
                "role": "user",
                "content": user_message
            }
        ]
    )
    
    claude_response = message.content[0].text
    
    # --- Step 4: VALIDATE the response ---
    
    # Parse out the confidence score
    # clean_answer = the answer without the "Confidence: X/5" line
    # confidence = the number (1-5) or None if not found
    clean_answer, confidence = parse_confidence(claude_response)
    
    # Check if the answer is grounded in the sources
    warning = validate_response(clean_answer, relevant_chunks)
    
    # Add extra warning if confidence is below threshold
    if confidence is not None and confidence < CONFIDENCE_THRESHOLD:
        low_conf_warning = (
            f"Low confidence ({confidence}/5): This answer may not be "
            f"fully supported by the uploaded documents."
        )
        # Combine with any existing validation warning
        if warning:
            warning = f"{warning} {low_conf_warning}"
        else:
            warning = low_conf_warning
    
    # --- Step 5: RETURN with all metadata ---
    return Answer(
        question=question.text,
        answer=clean_answer,
        model=message.model,
        sources=relevant_chunks if relevant_chunks else None,
        confidence=confidence,
        warning=warning,
        timestamp=datetime.now().isoformat()
    )


@app.delete("/api/documents/{doc_id}")
def delete_document(doc_id: str):
    """Delete a document and its vectors from ChromaDB."""
    if doc_id not in documents:
        raise HTTPException(
            status_code=404,
            detail=f"Document {doc_id} not found"
        )
    
    doc_info = documents[doc_id]
    
    try:
        chunk_ids = [
            f"{doc_id}_chunk_{i}"
            for i in range(doc_info.chunks)
        ]
        collection.delete(ids=chunk_ids)
    except Exception as e:
        print(f"Warning: Error deleting vectors: {e}")
    
    del documents[doc_id]
    
    return {"message": f"Document {doc_id} deleted successfully"}

# ------------------------------------------------------------
# Document Viewing Endpoints
# ------------------------------------------------------------

@app.get("/api/documents/{doc_id}/download")
def download_document(doc_id: str):
    """Download the original PDF file.
    
    This lets the frontend display or download the PDF.
    
    New import: FileResponse
    We already imported this at the bottom of the file for
    serving Angular static files. It sends a file directly
    to the browser instead of JSON.
    
    The 'media_type' tells the browser what kind of file it is.
    'application/pdf' means the browser knows to handle it as a PDF.
    
    'filename' sets the name when the user downloads it.
    """
    # Check the document exists in our metadata
    if doc_id not in documents:
        raise HTTPException(
            status_code=404,
            detail=f"Document {doc_id} not found"
        )
    
    doc_info = documents[doc_id]
    
    # Build the file path — same pattern we used during upload
    # We need to find the file on disk
    # os.listdir() lists all files in a directory
    # We search for a file that starts with the doc_id
    upload_files = os.listdir(UPLOAD_DIR)
    
    # next() with a generator finds the first matching item
    # It's like a for loop that stops at the first match
    # The None at the end is the default if nothing matches
    matching_file = next(
        (f for f in upload_files if f.startswith(doc_id)),
        None
    )
    
    if not matching_file:
        raise HTTPException(
            status_code=404,
            detail=f"PDF file for document {doc_id} not found on disk"
        )
    
    file_path = f"{UPLOAD_DIR}/{matching_file}"
    
    # FileResponse sends the actual file to the browser
    return FileResponse(
        path=file_path,
        media_type="application/pdf",
        filename=doc_info.filename
    )


@app.get("/api/documents/{doc_id}/pages/{page_num}")
def get_page_image(doc_id: str, page_num: int):
    """Convert a specific PDF page to an image and return it.
    
    This is used by the frontend to show a visual preview
    of the cited page. When Claude says "Source 1 (Page 3)",
    the user can see exactly what Page 3 looks like.
    
    How it works:
    1. Open the PDF with PyMuPDF
    2. Navigate to the requested page
    3. Render it as a PNG image
    4. Return the image bytes to the browser
    
    New concepts:
    
    'Response' from FastAPI — lets us return raw bytes (an image)
    instead of JSON. We set the media_type to 'image/png' so
    the browser displays it as an image.
    
    'get_pixmap()' — PyMuPDF method that renders a PDF page
    as a pixel map (image). The 'matrix' parameter controls
    the resolution — higher numbers = sharper image but bigger file.
    
    fitz.Matrix(2, 2) — scales the image 2x in both dimensions.
    Default PDF resolution is 72 DPI, so 2x gives us 144 DPI
    which looks crisp on screen without being too large.
    """
    # We need Response to return raw image bytes
    from fastapi.responses import Response
    
    # Validate document exists
    if doc_id not in documents:
        raise HTTPException(
            status_code=404,
            detail=f"Document {doc_id} not found"
        )
    
    # Find the PDF file on disk
    upload_files = os.listdir(UPLOAD_DIR)
    matching_file = next(
        (f for f in upload_files if f.startswith(doc_id)),
        None
    )
    
    if not matching_file:
        raise HTTPException(
            status_code=404,
            detail=f"PDF file not found on disk"
        )
    
    file_path = f"{UPLOAD_DIR}/{matching_file}"
    
    # Open the PDF
    doc = fitz.open(file_path)
    
    # Validate page number
    # page_num from the user is 1-based (Page 1, Page 2...)
    # PyMuPDF uses 0-based indexing (page 0, page 1...)
    # So we subtract 1
    if page_num < 1 or page_num > len(doc):
        doc.close()
        raise HTTPException(
            status_code=404,
            detail=f"Page {page_num} not found. Document has {len(doc)} pages."
        )
    
    # Get the page (convert from 1-based to 0-based)
    page = doc[page_num - 1]
    
    # Render the page as an image
    # fitz.Matrix(2, 2) = 2x zoom for better quality
    # Without zoom, text would be blurry on high-res screens
    pixmap = page.get_pixmap(matrix=fitz.Matrix(2, 2))
    
    # Convert to PNG bytes
    # .tobytes("png") converts the pixel data to PNG format
    image_bytes = pixmap.tobytes("png")
    
    # Clean up
    doc.close()
    
    # Return the image with the correct content type
    # The browser sees 'image/png' and displays it as an image
    return Response(
        content=image_bytes,
        media_type="image/png"
    )


@app.get("/api/documents/{doc_id}/chunks")
def get_document_chunks(doc_id: str):
    """Get all chunks for a specific document.
    
    This lets the frontend show exactly which text was
    extracted and how it was chunked. Useful for debugging
    and transparency — the user can see what the AI is
    working with.
    
    We query ChromaDB by filtering on document_id metadata.
    The 'where' parameter acts like a SQL WHERE clause:
    "give me all chunks WHERE document_id equals this value"
    """
    if doc_id not in documents:
        raise HTTPException(
            status_code=404,
            detail=f"Document {doc_id} not found"
        )
    
    # Query ChromaDB for all chunks belonging to this document
    # where={} filters by metadata fields
    results = collection.get(
        where={"document_id": doc_id}
    )
    
    # Package the results
    chunks = []
    if results["documents"]:
        for doc_text, metadata in zip(
            results["documents"],
            results["metadatas"]
        ):
            chunks.append({
                "text": doc_text,
                "page": metadata["page"],
                "chunk_index": metadata["chunk_index"]
            })
    
    # Sort by chunk_index so they're in order
    # sorted() creates a new sorted list
    # key=lambda x: x["chunk_index"] tells it what to sort by
    # lambda is Python's inline function — like a mini def
    chunks = sorted(chunks, key=lambda x: x["chunk_index"])
    
    return {
        "document_id": doc_id,
        "chunks": chunks,
        "count": len(chunks)
    }


# ------------------------------------------------------------
# Serve Angular frontend (production/Docker only)
# ------------------------------------------------------------
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

if os.path.exists("static"):
    app.mount("/static", StaticFiles(directory="static"), name="static")
    
    @app.get("/{path:path}")
    async def serve_frontend(path: str):
        file_path = f"static/{path}"
        if os.path.exists(file_path) and os.path.isfile(file_path):
            return FileResponse(file_path)
        return FileResponse("static/index.html")